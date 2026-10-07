"""
Schemas for job postings.

JobCreate / JobUpdate   - what a company sends (input rules).
JobSummary / JobDetail  - what the API sends back (JobSummary for lists, JobDetail for one job).
"""
from datetime import date, datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from ..models import ApplicationStatus, JobCategory, PayPeriod
from .auth import Name
from .profile import CompanyPublic, PartialUpdate, Short, Title, normalize_skills

Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)]


def _lower_email(value):
    return value.strip().lower() if value is not None else value


# ---------------- input ----------------
class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unknown fields (e.g. company_id) are refused

    title: Title
    description: Description
    category: JobCategory = Field(description="full_time, part_time, on_campus or internship")
    city: Name = Field(description="Job location, e.g. San Jose")
    state: Optional[Short] = None
    is_remote: bool = False
    salary_min: int = Field(ge=0, description="Lowest pay (per hour or per year, see pay_period)")
    salary_max: int = Field(ge=0)
    pay_period: PayPeriod = Field(description="hourly or yearly")
    posting_date: Optional[date] = Field(None, description="Defaults to today")
    deadline: date = Field(description="Last day to apply")
    contact_email: Optional[EmailStr] = Field(None, description="Defaults to the company's contact email")
    skills: List[str] = Field(default_factory=list)

    _email = field_validator("contact_email")(_lower_email)

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, v):
        return normalize_skills(v)


class JobUpdate(PartialUpdate):
    """Partial update: send only what changes. `skills`, if sent, replaces the whole list."""
    required = frozenset({"title", "description", "category", "city", "is_remote", "salary_min",
                          "salary_max", "pay_period", "posting_date", "deadline"})
    clearable = frozenset({"state", "contact_email"})

    title: Optional[Title] = None
    description: Optional[Description] = None
    category: Optional[JobCategory] = None
    city: Optional[Name] = None
    state: Optional[Short] = None
    is_remote: Optional[bool] = None
    salary_min: Optional[int] = Field(None, ge=0)
    salary_max: Optional[int] = Field(None, ge=0)
    pay_period: Optional[PayPeriod] = None
    posting_date: Optional[date] = None
    deadline: Optional[date] = None
    contact_email: Optional[EmailStr] = None
    skills: Optional[List[str]] = None

    _email = field_validator("contact_email")(_lower_email)

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, v):
        return normalize_skills(v) if v is not None else v


# ---------------- output ----------------
class CompanyMini(BaseModel):
    id: int
    name: str
    profile_pic_url: Optional[str]


class JobSummary(BaseModel):
    id: int
    title: str
    company: CompanyMini
    city: str
    state: Optional[str]
    is_remote: bool
    category: JobCategory
    salary_min: Optional[int]
    salary_max: Optional[int]
    pay_period: PayPeriod
    salary_display: str = Field(description='Human-readable pay, e.g. "$30–$40/hr"')
    posting_date: date
    deadline: date
    is_expired: bool
    skills: List[str]


class ApplicationRef(BaseModel):
    """The logged-in student's own application to this job (if any)."""
    id: int
    status: ApplicationStatus
    applied_at: datetime


class JobDetail(JobSummary):
    company: CompanyPublic                  # full public company profile instead of the mini one
    description: str
    contact_email: Optional[str]
    posted_days_ago: int
    my_application: Optional[ApplicationRef] = Field(
        None, description="Set only when a student who already applied views the job")


class MyJob(JobSummary):
    applicant_count: int


class JobPage(BaseModel):
    items: List[JobSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class MyJobsPage(BaseModel):
    items: List[MyJob]
    total: int
    page: int
    page_size: int
    total_pages: int