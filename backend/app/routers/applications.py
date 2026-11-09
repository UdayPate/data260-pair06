"""
Application endpoints.

Student:  POST /jobs/{job_id}/apply        apply with a PDF resume (202: a Kafka worker saves the application)
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
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import documents, mongo
from ..core.deps import Identity, get_identity, get_owned_job, require_company, require_student
from ..core.trace import get_trace_id
from ..core.uploads import delete_resume, read_resume, save_resume
from ..enums import ApplicationStatus
from ..events import topics
from ..events.errors import PublishError
from ..events.publisher import Publisher, get_publisher, publish_quietly
from ..mongo import Doc, get_db
from ..schemas.applications import (ApplicantDetail, ApplicantsPage, ApplicantSummary, ApplicationAccepted,
                                    MyApplication, MyApplicationsPage, StatusUpdate)
from ..services.activity_log import log_activity
from ..services.applications import (to_applicant_detail, to_applicant_summary, to_my_application,
                                     with_jobs, with_students)
from ..services.jobs import total_pages

router = APIRouter(tags=["Applications"])


# ---------------- student ----------------
@router.post("/jobs/{job_id}/apply", response_model=ApplicationAccepted, status_code=status.HTTP_202_ACCEPTED,
             summary="Apply to a job with a PDF resume (student only). Answers 202: a worker saves the application")
def apply_to_job(
    job_id: int,
    resume: UploadFile = File(..., description="Your resume as a PDF, max 5 MB"),
    student: Doc = Depends(require_student),
    db: Database = Depends(get_db),
    publisher: Publisher = Depends(get_publisher),
    trace_id: str = Depends(get_trace_id),
):
    """Check the request, store the PDF, and put an `application.created` event on Kafka. The Application worker writes
    the application (idempotently) and the API answers 202 Accepted without waiting for it."""
    job = mongo.get(db, "jobs", job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.deadline < date.today():
        raise HTTPException(status.HTTP_409_CONFLICT, "The application deadline for this job has passed")
    if mongo.find_one(db, "applications", {"student_id": student.id, "job_id": job.id}):
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already applied to this job")

    resume_id = save_resume(db, resume, student.id, job.id)     # validates it is a real PDF, stores it in GridFS
    try:
        envelope = publisher.publish(
            topics.APPLICATION_CREATED, key=f"{student.id}:{job.id}", trace_id=trace_id,
            payload={"student_id": student.id, "job_id": job.id, "resume_file_id": str(resume_id),
                     "applied_at": datetime.now().isoformat()})
    except PublishError:
        delete_resume(db, resume_id)                              # nothing was queued: don't keep the file
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Your application could not be queued right now. Please try again in a moment.")
    return ApplicationAccepted(event_id=envelope.event_id, trace_id=envelope.trace_id, job_id=job.id)


@router.get("/applications/mine", response_model=MyApplicationsPage, summary="My applications (student only)")
def my_applications(
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status",
                                                       description="Pending, Reviewed or Declined"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    student: Doc = Depends(require_student), db: Database = Depends(get_db),
):
    conditions = {"student_id": student.id}
    if status_filter is not None:
        conditions["status"] = status_filter
    rows, total = mongo.page(db, "applications", conditions, [("applied_at", -1), ("_id", -1)], page, page_size)
    with_jobs(db, rows)
    today = date.today()
    return MyApplicationsPage(items=[to_my_application(a, today) for a in rows], total=total, page=page,
                              page_size=page_size, total_pages=total_pages(total, page_size))


# ---------------- company ----------------
def _company_application_or_404(db: Database, application_id: int, company: Doc) -> Doc:
    """The application, with .job and .student attached, if it is for one of this company's jobs."""
    application = mongo.get(db, "applications", application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    with_jobs(db, [application])
    if application.job.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    with_students(db, [application])
    return application


@router.get("/jobs/{job_id}/applications", response_model=ApplicantsPage,
            summary="Applicants for one of my job postings (company only)")
def list_applicants(
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status",
                                                       description="Pending, Reviewed or Declined"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    job: Doc = Depends(get_owned_job), db: Database = Depends(get_db),
):
    conditions = {"job_id": job.id}
    if status_filter is not None:
        conditions["status"] = status_filter
    rows, total = mongo.page(db, "applications", conditions, [("applied_at", -1), ("_id", -1)], page, page_size)
    with_students(db, rows)
    return ApplicantsPage(items=[to_applicant_summary(a) for a in rows], total=total, page=page,
                          page_size=page_size, total_pages=total_pages(total, page_size))


@router.get("/applications/{application_id}", response_model=ApplicantDetail,
            summary="One applicant's full profile (company only)")
def get_applicant(application_id: int, company: Doc = Depends(require_company),
                  db: Database = Depends(get_db)):
    return to_applicant_detail(_company_application_or_404(db, application_id, company))


@router.patch("/applications/{application_id}/status", response_model=ApplicantSummary,
              summary="Set an application to Pending, Reviewed or Declined (company only)")
def update_status(application_id: int, body: StatusUpdate, company: Doc = Depends(require_company),
                  db: Database = Depends(get_db), publisher: Publisher = Depends(get_publisher),
                  trace_id: str = Depends(get_trace_id)):
    application = _company_application_or_404(db, application_id, company)
    old_status = ApplicationStatus(application.status).value
    mongo.update(db, "applications", application.id, {"status": body.status, "updated_at": datetime.now()})
    application["status"] = body.status
    log_activity(db, "company", company.id, "application_status_changed", "application", application.id,
                 {"status": body.status.value})
    if body.status.value != old_status:       # tell the student (a worker writes the notification)
        publish_quietly(publisher, topics.APPLICATION_STATUS_CHANGED, str(application.id), {
            "application_id": application.id, "student_id": application.student_id, "job_id": application.job_id,
            "job_title": application.job.title, "company_name": application.job.company.name,
            "old_status": old_status, "new_status": body.status.value}, trace_id)
    return to_applicant_summary(application)


# ---------------- both: the private resume file ----------------
@router.get("/applications/{application_id}/resume", summary="Download or preview the resume PDF")
def get_resume(application_id: int, identity: Identity = Depends(get_identity),
               db: Database = Depends(get_db)):
    application = mongo.get(db, "applications", application_id)
    allowed = False
    if application is not None:
        if identity.role == "student":
            allowed = application.student_id == identity.user.id
        else:
            job = mongo.get(db, "jobs", application.job_id)
            allowed = job is not None and job.company_id == identity.user.id
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    data = read_resume(db, application.resume_file_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume file not found")

    student = mongo.get(db, "students", application.student_id)
    safe_name = re.sub(r"[^A-Za-z0-9 _.-]", "", f"Resume - {student.name}").strip() or "Resume"
    return Response(
        content=data, media_type="application/pdf",
        headers={
            # "inline" shows the PDF in the browser instead of downloading it; the name is URL-encoded (RFC 5987)
            "Content-Disposition": f"inline; filename*=utf-8''{quote(safe_name + '.pdf')}",
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        },
    )
