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
from pymongo.database import Database

from .. import documents, mongo
from ..core.deps import Identity, get_identity, get_owned_job, require_company
from ..core.trace import get_trace_id
from ..core.uploads import public_url
from ..enums import JobCategory, PayPeriod
from ..events import topics
from ..events.publisher import Publisher, get_publisher, publish_quietly
from ..mongo import Doc, get_db
from ..schemas.jobs import ApplicationRef, CompanyMini, JobCreate, JobDetail, JobPage, JobUpdate, MyJob, MyJobsPage
from ..services.activity_log import log_activity
from ..services.jobs import (applicant_counts, check_job_rules, search_jobs, summary_fields,
                             to_detail, to_summary, total_pages, with_companies)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _rules_or_422(**kwargs) -> None:
    try:
        check_job_rules(**kwargs)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


# ---------------- company: create / list own / edit ----------------
@router.post("", response_model=JobDetail, status_code=status.HTTP_201_CREATED,
             summary="Post a new job (company only)")
def create_job(body: JobCreate, company: Doc = Depends(require_company), db: Database = Depends(get_db),
               publisher: Publisher = Depends(get_publisher), trace_id: str = Depends(get_trace_id)):
    posting_date = body.posting_date or date.today()
    _rules_or_422(posting_date=posting_date, deadline=body.deadline, salary_min=body.salary_min,
                  salary_max=body.salary_max, pay_period=body.pay_period, creating=True)
    job = mongo.insert(db, "jobs", documents.job(
        company_id=company.id, title=body.title, description=body.description, category=body.category,
        city=body.city, state=body.state, is_remote=body.is_remote, salary_min=body.salary_min,
        salary_max=body.salary_max, pay_period=body.pay_period, posting_date=posting_date,
        deadline=body.deadline, contact_email=body.contact_email or company.contact_email or company.email,
        skills=list(body.skills),
    ))
    job["company"] = company
    log_activity(db, "company", company.id, "job_created", "job", job.id)
    publish_quietly(publisher, topics.JOB_CREATED, str(job.id), {         # a worker notifies the students it fits
        "job_id": job.id, "company_id": company.id, "company_name": company.name, "title": job.title,
        "category": JobCategory(job.category).value, "city": job.city, "is_remote": bool(job.is_remote)}, trace_id)
    return to_detail(job)


@router.get("/mine", response_model=MyJobsPage, summary="My job postings with applicant counts (company only)")
def my_jobs(
    include_expired: bool = Query(True, description="Show postings whose deadline has passed"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    company: Doc = Depends(require_company), db: Database = Depends(get_db),
):
    conditions = {"company_id": company.id}
    if not include_expired:
        conditions["deadline"] = {"$gte": date.today()}
    jobs, total = mongo.page(db, "jobs", conditions, [("posting_date", -1), ("_id", -1)], page, page_size)
    counts = applicant_counts(db, [j.id for j in jobs])
    today = date.today()
    owner = CompanyMini(id=company.id, name=company.name, profile_pic_url=public_url(company.profile_pic_path))
    items = [MyJob(company=owner, applicant_count=counts.get(job.id, 0), **summary_fields(job, today))
             for job in jobs]
    return MyJobsPage(items=items, total=total, page=page, page_size=page_size,
                      total_pages=total_pages(total, page_size))


@router.patch("/{job_id}", response_model=JobDetail, summary="Edit one of my job postings (company only)")
def update_job(body: JobUpdate, job: Doc = Depends(get_owned_job), db: Database = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)

    # Check the rules against the job AS IT WILL BE after this edit (old values + changes).
    merged = {key: data.get(key, job[key])
              for key in ("posting_date", "deadline", "salary_min", "salary_max", "pay_period")}
    _rules_or_422(**merged, creating=False)

    changes = dict(data)
    if "pay_period" in changes or "salary_max" in changes:      # the derived yearly figure needs both values
        changes["pay_period"], changes["salary_max"] = merged["pay_period"], merged["salary_max"]
    changes.update(documents.derived("jobs", changes))           # skills_lower, salary_yearly_max
    mongo.update(db, "jobs", job.id, changes)
    updated = mongo.get(db, "jobs", job.id)
    with_companies(db, [updated])
    log_activity(db, "company", job.company_id, "job_updated", "job", job.id)
    return to_detail(updated)


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
    identity: Identity = Depends(get_identity), db: Database = Depends(get_db),
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
def get_job(job_id: int, identity: Identity = Depends(get_identity), db: Database = Depends(get_db)):
    job = mongo.get(db, "jobs", job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    with_companies(db, [job])
    detail = to_detail(job)
    if identity.role == "student":
        mine = mongo.find_one(db, "applications", {"student_id": identity.user.id, "job_id": job.id})
        if mine is not None:
            detail.my_application = ApplicationRef(id=mine.id, status=mine.status, applied_at=mine.applied_at)
    return detail