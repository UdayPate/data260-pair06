"""
Builders for application responses. They expect application.job (with job.company) and
application.student to be attached already (mongo.attach), see the helpers below.

Resumes are PRIVATE. The API never hands out a file path; it hands out
"/applications/{id}/resume", an endpoint that checks who is asking before sending the PDF.
"""
from datetime import date
from typing import Optional

from ..mongo import Doc
from ..schemas.applications import ApplicantDetail, ApplicantSummary, JobRef, MyApplication
from .students import to_employer_view, to_student_card


def resume_url(application: Doc) -> str:
    return f"/applications/{application.id}/resume"


def to_job_ref(job: Doc, today: Optional[date] = None) -> JobRef:
    today = today or date.today()
    return JobRef(
        id=job.id, title=job.title, company_id=job.company_id, company_name=job.company.name,
        city=job.city, is_remote=job.is_remote, category=job.category,
        deadline=job.deadline, is_expired=job.deadline < today,
    )


def to_my_application(application: Doc, today: Optional[date] = None) -> MyApplication:
    return MyApplication(
        id=application.id, status=application.status, applied_at=application.applied_at,
        resume_url=resume_url(application), job=to_job_ref(application.job, today),
    )


def to_applicant_summary(application: Doc) -> ApplicantSummary:
    return ApplicantSummary(
        id=application.id, status=application.status, applied_at=application.applied_at,
        resume_url=resume_url(application), student=to_student_card(application.student),
    )


def to_applicant_detail(application: Doc, today: Optional[date] = None) -> ApplicantDetail:
    return ApplicantDetail(
        id=application.id, status=application.status, applied_at=application.applied_at,
        resume_url=resume_url(application), student=to_employer_view(application.student),
        job=to_job_ref(application.job, today),
    )

def with_jobs(db, applications):
    """Attach application.job and application.job.company to every application in the list."""
    from .jobs import with_companies
    from .. import mongo
    mongo.attach(db, applications, "job_id", "jobs", "job")
    with_companies(db, [a.job for a in applications if a.job is not None])
    return applications


def with_students(db, applications):
    """Attach application.student to every application in the list."""
    from .. import mongo
    return mongo.attach(db, applications, "student_id", "students", "student")
