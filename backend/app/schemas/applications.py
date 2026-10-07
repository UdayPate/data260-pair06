"""
Schemas for job applications.

Student side:  MyApplication (+ page)
Company side:  ApplicantSummary (list row) and ApplicantDetail (one applicant)
"""
from datetime import date, datetime
from typing import List

from pydantic import BaseModel, ConfigDict

from ..models import ApplicationStatus, JobCategory
from .student_views import StudentCard, StudentForEmployer


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ApplicationStatus   # exactly: Pending, Reviewed or Declined


class JobRef(BaseModel):
    """A short description of the job an application is for."""
    id: int
    title: str
    company_id: int
    company_name: str
    city: str
    is_remote: bool
    category: JobCategory
    deadline: date
    is_expired: bool


class MyApplication(BaseModel):
    id: int
    status: ApplicationStatus
    applied_at: datetime
    resume_url: str
    job: JobRef


class MyApplicationsPage(BaseModel):
    items: List[MyApplication]
    total: int
    page: int
    page_size: int
    total_pages: int


class ApplicantSummary(BaseModel):
    id: int                       # the application's id
    status: ApplicationStatus
    applied_at: datetime
    resume_url: str
    student: StudentCard


class ApplicantDetail(ApplicantSummary):
    student: StudentForEmployer   # full profile instead of the short card
    job: JobRef


class ApplicantsPage(BaseModel):
    items: List[ApplicantSummary]
    total: int
    page: int
    page_size: int
    total_pages: int