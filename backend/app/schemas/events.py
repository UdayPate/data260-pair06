"""
Schemas for events.

Eligibility works by MAJOR: an event lists the majors allowed to register, or the single
value "All". A student may register if the event is open to "All" or to their major.
"""
import re
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ..skills import MAJORS
from .auth import Name
from .jobs import CompanyMini, Description
from .profile import CompanyPublic, PartialUpdate
from .student_views import StudentCard

EventName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

ALL_MAJORS = "All"
_CANON_MAJORS = {m.lower(): m for m in MAJORS}
_MAJOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &()/.\-]*$")


def normalize_majors(values: List[str]) -> List[str]:
    """Trim, de-duplicate (ignoring case) and use the shared spelling from skills.py.
    'All' means open to everyone and replaces any other entries."""
    result, seen = [], set()
    for raw in values:
        major = " ".join(raw.split())
        if not major:
            continue
        if len(major) > 100 or not _MAJOR_RE.match(major):
            raise ValueError(f"Invalid major: {raw!r}")
        key = major.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(ALL_MAJORS if key == "all" else _CANON_MAJORS.get(key, major))
    if not result:
        raise ValueError('Choose at least one eligible major, or "All"')
    if ALL_MAJORS in result:
        return [ALL_MAJORS]
    if len(result) > 10:
        raise ValueError("At most 10 majors are allowed")
    return result


def _to_local_naive(value: datetime) -> datetime:
    """The database stores plain local date-times. If the client sent a time zone
    (e.g. a trailing 'Z'), convert it to the server's local time first."""
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.replace(microsecond=0)


# ---------------- input ----------------
class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: EventName
    description: Description
    event_datetime: datetime = Field(description="Date and time, e.g. 2026-11-05T17:30:00")
    location: Location = Field(description="Venue or address")
    city: Name
    eligible_majors: List[str] = Field(default_factory=lambda: [ALL_MAJORS],
                                       description='Majors allowed to register, or ["All"]')

    @field_validator("event_datetime")
    @classmethod
    def _local(cls, v):
        return _to_local_naive(v)

    @field_validator("eligible_majors")
    @classmethod
    def _majors(cls, v):
        return normalize_majors(v)


class EventUpdate(PartialUpdate):
    """Partial update: send only what changes. `eligible_majors`, if sent, replaces the whole list."""
    required = frozenset({"name", "description", "event_datetime", "location", "city", "eligible_majors"})

    name: Optional[EventName] = None
    description: Optional[Description] = None
    event_datetime: Optional[datetime] = None
    location: Optional[Location] = None
    city: Optional[Name] = None
    eligible_majors: Optional[List[str]] = None

    @field_validator("event_datetime")
    @classmethod
    def _local(cls, v):
        return _to_local_naive(v) if v is not None else v

    @field_validator("eligible_majors")
    @classmethod
    def _majors(cls, v):
        return normalize_majors(v) if v is not None else v


# ---------------- output ----------------
class EventSummary(BaseModel):
    id: int
    name: str
    company: CompanyMini
    event_datetime: datetime
    location: str
    city: str
    eligible_majors: List[str]
    registration_count: int
    is_past: bool
    eligible: Optional[bool] = Field(None, description="Students only: may I register (by major)?")
    registered: Optional[bool] = Field(None, description="Students only: am I registered?")


class EventDetail(EventSummary):
    company: CompanyPublic
    description: str
    can_register: Optional[bool] = Field(None, description="Students only")
    register_blocked_reason: Optional[str] = Field(None, description="Why not, in plain English")


class EventPage(BaseModel):
    items: List[EventSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class RegistrationOut(BaseModel):
    event: EventSummary
    registered_at: datetime


class RegisteredStudent(BaseModel):
    student: StudentCard
    registered_at: datetime


class RegistrationsPage(BaseModel):
    items: List[RegisteredStudent]
    total: int
    page: int
    page_size: int
    total_pages: int