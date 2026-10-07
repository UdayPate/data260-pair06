"""
Schemas for student and company profiles.

*Update schemas* (StudentUpdate, CompanyUpdate) are PARTIAL: the client sends only the
fields it wants to change. Fields it leaves out stay as they are.
    - sending  "city": "San Jose"   -> sets the city
    - sending  "city": null  or ""  -> clears the city (optional fields only)
    - sending an unknown field (e.g. "password_hash") -> 422 error. This blocks
      "mass assignment" attacks where someone tries to overwrite fields they shouldn't.
"""
import re
from datetime import date
from typing import Annotated, ClassVar, FrozenSet, List, Optional

from pydantic import (BaseModel, ConfigDict, EmailStr, Field, StringConstraints,
                      ValidationInfo, field_validator, model_validator)

from ..core.uploads import public_url
from ..skills import ALL_SKILLS, MAJORS
from .auth import Name, _validate_email

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]

_CANON_SKILLS = {s.lower(): s for s in ALL_SKILLS}
_CANON_MAJORS = {m.lower(): m for m in MAJORS}
_SKILL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 +#.\-/&()]*$")   # allows C++, C#, Node.js ...
_PHONE_RE = re.compile(r"^[0-9+().\-\s]{7,25}$")
_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


# ---------- reusable checks ----------
def normalize_skills(values: List[str]) -> List[str]:
    """Trim, de-duplicate (ignoring case) and use the shared Title Case spelling when the
    skill is in skills.py (so 'python' and 'PYTHON' both become 'Python')."""
    result, seen = [], set()
    for raw in values:
        skill = " ".join(raw.split())
        if not skill:
            continue
        if len(skill) > 50 or not _SKILL_RE.match(skill):
            raise ValueError(f"Invalid skill: {raw!r}")
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(_CANON_SKILLS.get(key, skill))
    if len(result) > 30:
        raise ValueError("At most 30 skills are allowed")
    return result


def _validate_phone(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    digits = sum(ch.isdigit() for ch in value)
    if not _PHONE_RE.match(value) or not 7 <= digits <= 15:
        raise ValueError("Enter a valid phone number, e.g. (408) 555-0123")
    return value


class PartialUpdate(BaseModel):
    """Base class for update schemas: forbids unknown fields and turns a blank string
    into None for the fields listed in `clearable` (so the form can clear a field)."""
    model_config = ConfigDict(extra="forbid")
    clearable: ClassVar[FrozenSet[str]] = frozenset()
    required: ClassVar[FrozenSet[str]] = frozenset()

    @field_validator("*", mode="before")
    @classmethod
    def _blank_and_null_rules(cls, value, info: ValidationInfo):
        if info.field_name in cls.required and value is None:
            raise ValueError("This field cannot be null")
        if isinstance(value, str) and not value.strip() and info.field_name in cls.clearable:
            return None
        return value


# ---------- student ----------
class ExperienceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    company: Title
    start_date: Optional[date] = None
    end_date: Optional[date] = None   # empty = current role
    description: Optional[Long] = None

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class StudentUpdate(PartialUpdate):
    required = frozenset({"name", "email", "college"})
    clearable = frozenset({"date_of_birth", "city", "state", "country", "career_objective",
                           "degree", "major", "graduation_year", "cgpa", "phone"})

    name: Optional[Name] = None
    email: Optional[EmailStr] = None
    college: Optional[Name] = None
    date_of_birth: Optional[date] = None
    city: Optional[Short] = None
    state: Optional[Short] = None
    country: Optional[Short] = None
    career_objective: Optional[Long] = None
    degree: Optional[Short] = None
    major: Optional[Short] = None
    graduation_year: Optional[int] = Field(None, ge=1990, le=2040)
    cgpa: Optional[float] = Field(None, ge=0.0, le=4.0, description="Cumulative GPA on a 4.0 scale")
    phone: Optional[str] = None
    skills: Optional[List[str]] = Field(None, description="Replaces the whole skill list")
    experience: Optional[List[ExperienceIn]] = Field(None, max_length=20,
                                                     description="Replaces the whole experience list")

    _email = field_validator("email")(_validate_email)
    _phone = field_validator("phone")(_validate_phone)

    @field_validator("date_of_birth")
    @classmethod
    def _check_dob(cls, v):
        if v is None:
            return v
        today = date.today()
        if v < date(1900, 1, 1):
            raise ValueError("Date of birth is too far in the past")
        if (today - v).days < 16 * 365:
            raise ValueError("You must be at least 16 years old")
        return v

    @field_validator("major")
    @classmethod
    def _canonical_major(cls, v):
        return _CANON_MAJORS.get(v.lower(), v) if v else v

    @field_validator("cgpa")
    @classmethod
    def _round_cgpa(cls, v):
        return round(v, 2) if v is not None else v

    @field_validator("skills")
    @classmethod
    def _check_skills(cls, v):
        return normalize_skills(v) if v is not None else v


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    company: str
    start_date: Optional[date]
    end_date: Optional[date]
    description: Optional[str]


class StudentProfile(BaseModel):
    id: int
    name: str
    email: str
    college: str
    date_of_birth: Optional[date]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    career_objective: Optional[str]
    degree: Optional[str]
    major: Optional[str]
    graduation_year: Optional[int]
    cgpa: Optional[float]
    phone: Optional[str]
    profile_pic_url: Optional[str]
    skills: List[str]
    experience: List[ExperienceOut]


# ---------- company ----------
class CompanyUpdate(PartialUpdate):
    required = frozenset({"name", "email", "location"})
    clearable = frozenset({"state", "industry", "description", "contact_email",
                           "contact_phone", "website"})

    name: Optional[Name] = None
    email: Optional[EmailStr] = Field(None, description="Login email")
    location: Optional[Name] = Field(None, description="City, e.g. San Jose")
    state: Optional[Short] = None
    industry: Optional[Short] = None
    description: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)]] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    website: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]] = None

    _email = field_validator("email")(_validate_email)
    _contact_email = field_validator("contact_email")(
        lambda v: _validate_email(v) if v is not None else v)
    _phone = field_validator("contact_phone")(_validate_phone)

    @field_validator("website")
    @classmethod
    def _check_website(cls, v):
        if v is not None and not _URL_RE.match(v):
            raise ValueError("Website must start with http:// or https://")
        return v


class CompanyProfile(BaseModel):
    id: int
    name: str
    email: str
    location: str
    state: Optional[str]
    industry: Optional[str]
    description: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    website: Optional[str]
    profile_pic_url: Optional[str]


class CompanyPublic(BaseModel):
    """What OTHER people may see about a company (no login email)."""
    id: int
    name: str
    location: str
    state: Optional[str]
    industry: Optional[str]
    description: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    website: Optional[str]
    profile_pic_url: Optional[str]

    @classmethod
    def from_company(cls, c) -> "CompanyPublic":
        return cls(id=c.id, name=c.name, location=c.city, state=c.state, industry=c.industry,
                   description=c.description, contact_email=c.contact_email,
                   contact_phone=c.contact_phone, website=c.website,
                   profile_pic_url=public_url(c.profile_pic_path))


class PictureResponse(BaseModel):
    profile_pic_url: str