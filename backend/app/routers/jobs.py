"""
Job endpoints.

Companies: POST /jobs, PATCH /jobs/{id}, GET /jobs/mine
Anyone logged in (student or company): GET /jobs (search), GET /jobs/{id} (details)

Order matters: "/mine" is declared BEFORE "/{job_id}" so FastAPI doesn't try to read the
word "mine" as a job id.
"""
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..core.deps import Identity, get_identity, require_company
from ..core.uploads import public_url
from ..database import get_db
from ..models import Company, Job, JobCategory, JobSkill, PayPeriod
from ..schemas.jobs import CompanyMini, JobCreate, JobDetail, JobPage, JobUpdate, MyJob, MyJobsPage
from ..services.jobs import (applicant_counts, check_job_rules, search_jobs, summary_fields,
                             to_detail, to_summary, total_pages)
from ..services.skill_sync import sync_skills

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _rules_or_422(**kwargs) -> None:
    try:
        check_job_rules(**kwargs)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _owned_job_or_error(db: Session, job_id: int, company: Company) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.company_id != company.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only change your own job postings")
    return job


# ---------------- company: create / list own / edit ----------------
@router.post("", response_model=JobDetail, status_code=status.HTTP_201_CREATED,
             summary="Post a new job (company only)")
def create_job(body: JobCreate, company: Company = Depends(require_company), db: Session = Depends(get_db)):
    posting_date = body.posting_date or date.today()
    _rules_or_422(posting_date=posting_date, deadline=body.deadline, salary_min=body.salary_min,
                  salary_max=body.salary_max, pay_period=body.pay_period, creating=True)
    job = Job(
        company_id=company.id, title=body.title, description=body.description, category=body.category,
        city=body.city, state=body.state, is_remote=body.is_remote, salary_min=body.salary_min,
        salary_max=body.salary_max, pay_period=body.pay_period, posting_date=posting_date,
        deadline=body.deadline, contact_email=body.contact_email or company.contact_email or company.email,
    )
    job.skills = [JobSkill(skill=skill) for skill in body.skills]
    db.add(job)
    db.commit()
    db.refresh(job)
    return to_detail(job)


@router.get("/mine", response_model=MyJobsPage, summary="My job postings with applicant counts (company only)")
def my_jobs(
    include_expired: bool = Query(True, description="Show postings whose deadline has passed"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    company: Company = Depends(require_company), db: Session = Depends(get_db),
):
    conditions = [Job.company_id == company.id]
    if not include_expired:
        conditions.append(Job.deadline >= date.today())
    total = db.scalar(select(func.count(Job.id)).where(*conditions)) or 0
    jobs = db.scalars(select(Job).where(*conditions).options(selectinload(Job.skills))
                      .order_by(Job.posting_date.desc(), Job.id.desc())
                      .limit(page_size).offset((page - 1) * page_size)).all()
    counts = applicant_counts(db, [j.id for j in jobs])
    today = date.today()
    owner = CompanyMini(id=company.id, name=company.name, profile_pic_url=public_url(company.profile_pic_path))
    items = [MyJob(company=owner, applicant_count=counts.get(job.id, 0), **summary_fields(job, today))
             for job in jobs]
    return MyJobsPage(items=items, total=total, page=page, page_size=page_size,
                      total_pages=total_pages(total, page_size))


@router.patch("/{job_id}", response_model=JobDetail, summary="Edit one of my job postings (company only)")
def update_job(job_id: int, body: JobUpdate, company: Company = Depends(require_company),
               db: Session = Depends(get_db)):
    job = _owned_job_or_error(db, job_id, company)
    data = body.model_dump(exclude_unset=True)
    skills = data.pop("skills", None)

    # Check the rules against the job AS IT WILL BE after this edit (old values + changes).
    merged = {key: data.get(key, getattr(job, key))
              for key in ("posting_date", "deadline", "salary_min", "salary_max", "pay_period")}
    _rules_or_422(**merged, creating=False)

    for field, value in data.items():
        setattr(job, field, value)
    if skills is not None:
        sync_skills(job.skills, skills, lambda text: JobSkill(skill=text))
    db.commit()
    db.refresh(job)
    return to_detail(job)


# ---------------- everyone: search / details ----------------
@router.get("", response_model=JobPage, summary="Search and filter jobs")
def list_jobs(
    q: Optional[str] = Query(None, max_length=100, description="Words to find in the job title or company name"),
    category: Optional[List[JobCategory]] = Query(None, description="Repeat to allow several"),
    city: Optional[List[str]] = Query(None, max_length=10, description="Repeat to allow several"),
    is_remote: Optional[bool] = Query(None),
    min_salary: Optional[int] = Query(None, ge=0, description="Needs salary_unit"),
    salary_unit: Optional[PayPeriod] = Query(None, description="hourly or yearly: the unit of min_salary"),
    skills: Optional[List[str]] = Query(None, max_length=10, description="Repeat to require several"),
    skills_match: Literal["any", "all"] = Query("any"),
    deadline_before: Optional[date] = Query(None, description="Closing on or before this date"),
    deadline_after: Optional[date] = Query(None, description="Closing on or after this date"),
    include_expired: bool = Query(False, description="Also show jobs whose deadline has passed"),
    sort: Literal["newest", "deadline", "salary"] = Query("newest"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
):
    try:
        jobs, total = search_jobs(
            db, q=q, category=category, city=city, is_remote=is_remote, min_salary=min_salary,
            salary_unit=salary_unit, skills=skills, skills_match=skills_match,
            deadline_before=deadline_before, deadline_after=deadline_after,
            include_expired=include_expired, sort=sort, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    today = date.today()
    return JobPage(items=[to_summary(j, today) for j in jobs], total=total, page=page,
                   page_size=page_size, total_pages=total_pages(total, page_size))


@router.get("/{job_id}", response_model=JobDetail, summary="Job details with company profile")
def get_job(job_id: int, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return to_detail(job)