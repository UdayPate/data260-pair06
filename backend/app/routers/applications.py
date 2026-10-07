"""
Application endpoints.

Student:  POST /jobs/{job_id}/apply        apply with a PDF resume
          GET  /applications/mine          my applications (filter by status)
Company:  GET  /jobs/{job_id}/applications applicants for one of my postings (filter by status)
          GET  /applications/{id}          one applicant: full profile
          PATCH /applications/{id}/status  Pending / Reviewed / Declined
Both:     GET  /applications/{id}/resume   the PDF (the student who sent it, or the company
                                           that owns the job; nobody else)

Why 404 and not 403 for other people's applications: an application is private. Answering
"403 Forbidden" would confirm that application number 57 exists, so strangers get the same
"not found" they would get for a number that doesn't exist.
"""
import re
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, selectinload

from ..core.deps import Identity, get_identity, get_owned_job, require_company, require_student
from ..core.uploads import delete_upload, resume_file_path, save_resume
from ..database import get_db
from ..models import Application, ApplicationStatus, Company, Job, Student
from ..schemas.applications import (ApplicantDetail, ApplicantsPage, ApplicantSummary, MyApplication,
                                    MyApplicationsPage, StatusUpdate)
from ..services.applications import (to_applicant_detail, to_applicant_summary, to_my_application)
from ..services.jobs import total_pages

router = APIRouter(tags=["Applications"])


# ---------------- student ----------------
@router.post("/jobs/{job_id}/apply", response_model=MyApplication, status_code=status.HTTP_201_CREATED,
             summary="Apply to a job with a PDF resume (student only)")
def apply_to_job(
    job_id: int,
    resume: UploadFile = File(..., description="Your resume as a PDF, max 5 MB"),
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.deadline < date.today():
        raise HTTPException(status.HTTP_409_CONFLICT, "The application deadline for this job has passed")
    already = db.scalar(select(Application.id).where(Application.student_id == student.id,
                                                     Application.job_id == job.id))
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already applied to this job")

    resume_path = save_resume(resume, student.id, job.id)     # validates it is a real PDF
    application = Application(student_id=student.id, job_id=job.id, resume_path=resume_path,
                              status=ApplicationStatus.pending, applied_at=datetime.now())
    db.add(application)
    try:
        db.commit()
    except IntegrityError:           # two clicks at once: the UNIQUE (student, job) rule caught it
        db.rollback()
        delete_upload(resume_path)   # don't leave the file behind
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already applied to this job")
    db.refresh(application)
    return to_my_application(application)


@router.get("/applications/mine", response_model=MyApplicationsPage, summary="My applications (student only)")
def my_applications(
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status",
                                                       description="Pending, Reviewed or Declined"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    student: Student = Depends(require_student), db: Session = Depends(get_db),
):
    conditions = [Application.student_id == student.id]
    if status_filter is not None:
        conditions.append(Application.status == status_filter)
    total = db.scalar(select(func.count(Application.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Application).join(Application.job).join(Job.company).where(*conditions)
        .options(contains_eager(Application.job).contains_eager(Job.company))
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .limit(page_size).offset((page - 1) * page_size)
    ).all()
    today = date.today()
    return MyApplicationsPage(items=[to_my_application(a, today) for a in rows], total=total, page=page,
                              page_size=page_size, total_pages=total_pages(total, page_size))


# ---------------- company ----------------
def _company_application_or_404(db: Session, application_id: int, company: Company) -> Application:
    application = db.get(Application, application_id)
    if application is None or application.job.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return application


@router.get("/jobs/{job_id}/applications", response_model=ApplicantsPage,
            summary="Applicants for one of my job postings (company only)")
def list_applicants(
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status",
                                                       description="Pending, Reviewed or Declined"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    job: Job = Depends(get_owned_job), db: Session = Depends(get_db),
):
    conditions = [Application.job_id == job.id]
    if status_filter is not None:
        conditions.append(Application.status == status_filter)
    total = db.scalar(select(func.count(Application.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Application).join(Application.student).where(*conditions)
        .options(contains_eager(Application.student).selectinload(Student.skills))
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .limit(page_size).offset((page - 1) * page_size)
    ).all()
    return ApplicantsPage(items=[to_applicant_summary(a) for a in rows], total=total, page=page,
                          page_size=page_size, total_pages=total_pages(total, page_size))


@router.get("/applications/{application_id}", response_model=ApplicantDetail,
            summary="One applicant's full profile (company only)")
def get_applicant(application_id: int, company: Company = Depends(require_company),
                  db: Session = Depends(get_db)):
    return to_applicant_detail(_company_application_or_404(db, application_id, company))


@router.patch("/applications/{application_id}/status", response_model=ApplicantSummary,
              summary="Set an application to Pending, Reviewed or Declined (company only)")
def update_status(application_id: int, body: StatusUpdate, company: Company = Depends(require_company),
                  db: Session = Depends(get_db)):
    application = _company_application_or_404(db, application_id, company)
    application.status = body.status
    db.commit()
    db.refresh(application)
    return to_applicant_summary(application)


# ---------------- both: the private resume file ----------------
@router.get("/applications/{application_id}/resume", summary="Download or preview the resume PDF")
def get_resume(application_id: int, identity: Identity = Depends(get_identity),
               db: Session = Depends(get_db)):
    application = db.get(Application, application_id)
    allowed = application is not None and (
        (identity.role == "student" and application.student_id == identity.user.id)
        or (identity.role == "company" and application.job.company_id == identity.user.id)
    )
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    path = resume_file_path(application.resume_path)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume file not found")

    safe_name = re.sub(r"[^A-Za-z0-9 _.-]", "", f"Resume - {application.student.name}").strip() or "Resume"
    return FileResponse(
        path, media_type="application/pdf", filename=f"{safe_name}.pdf",
        content_disposition_type="inline",           # show in the browser instead of downloading
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )