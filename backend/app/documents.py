"""
Builders for new MongoDB documents: one function per collection. They are the single place that says
which fields a document has, so every document of a collection looks the same (see docs/lab2/MONGO_SCHEMA.md).

    student = documents.student(name="Ada", email="ada@x.edu", password_hash=h, college="SJSU")

A few fields exist only to make searching easy and fast. They are always derived from another field here:
    name_lower, skills_lower, eligible_majors_lower   lower-case copies, for case-insensitive search and sorting
    salary_yearly_max                                  the top pay as a yearly number, so hourly and yearly jobs compare
Whenever the field they come from changes, derived() gives the new values to store next to it.
"""
import copy
from datetime import datetime
from typing import Any, Dict, Optional

from .enums import ApplicationStatus, PayPeriod

HOURS_PER_YEAR = 2080            # 40 hours x 52 weeks
REQUIRED = object()              # marks a field the caller must give


def _build(kind: str, spec: Dict[str, Any], given: Dict[str, Any]) -> Dict[str, Any]:
    unknown = set(given) - set(spec)
    if unknown:                  # a misspelled field would otherwise be stored silently
        raise TypeError(f"{kind}: unknown field(s) {sorted(unknown)}")
    doc = {}
    for name, default in spec.items():
        if name in given:
            doc[name] = given[name]
        elif default is REQUIRED:
            raise TypeError(f"{kind}: missing required field '{name}'")
        else:
            doc[name] = copy.deepcopy(default)
    return doc


def yearly_max(pay_period: Any, salary_max: Optional[int]) -> Optional[int]:
    """The job's top pay as a yearly figure: an hourly rate is multiplied by 2080 hours."""
    if salary_max is None:
        return None
    return salary_max * HOURS_PER_YEAR if PayPeriod(pay_period) == PayPeriod.hourly else salary_max


def lowered(values) -> list:
    return [v.lower() for v in values]


def derived(kind: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """The derived fields to store, for the fields in `data` that are being written.
    For jobs, `data` must contain both pay_period and salary_max when either changes."""
    out: Dict[str, Any] = {}
    if kind == "students":
        if "name" in data:
            out["name_lower"] = data["name"].lower()
        if "skills" in data:
            out["skills_lower"] = lowered(data["skills"])
    elif kind == "jobs":
        if "skills" in data:
            out["skills_lower"] = lowered(data["skills"])
        if "pay_period" in data or "salary_max" in data:
            out["salary_yearly_max"] = yearly_max(data["pay_period"], data["salary_max"])
    elif kind == "events":
        if "eligible_majors" in data:
            out["eligible_majors_lower"] = lowered(data["eligible_majors"])
    return out


def student(**fields) -> Dict[str, Any]:
    doc = _build("student", dict(
        name=REQUIRED, email=REQUIRED, password_hash=REQUIRED, college=REQUIRED,
        date_of_birth=None, city=None, state=None, country=None, career_objective=None, degree=None,
        major=None, graduation_year=None, cgpa=None, phone=None, profile_pic_path=None,
        skills=[],            # ["Python", "SQL"]
        experiences=[],       # [{id, title, company, start_date, end_date, description}]
        created_at=None), fields)
    doc.update(derived("students", doc))
    doc["created_at"] = doc["created_at"] or datetime.now()
    return doc


def experience(entry_id: int, **fields) -> Dict[str, Any]:
    """One work-experience entry inside a student document. Every key is always present (None when empty)."""
    entry = _build("experience", dict(title=REQUIRED, company=REQUIRED, start_date=None, end_date=None,
                                      description=None), fields)
    return {"id": entry_id, **entry}


def company(**fields) -> Dict[str, Any]:
    doc = _build("company", dict(
        name=REQUIRED, email=REQUIRED, password_hash=REQUIRED, city=REQUIRED,
        state=None, industry=None, description=None, contact_email=None, contact_phone=None,
        website=None, profile_pic_path=None, created_at=None), fields)
    doc["created_at"] = doc["created_at"] or datetime.now()
    return doc


def job(**fields) -> Dict[str, Any]:
    doc = _build("job", dict(
        company_id=REQUIRED, title=REQUIRED, description=REQUIRED, category=REQUIRED, city=REQUIRED,
        posting_date=REQUIRED, deadline=REQUIRED, pay_period=REQUIRED,
        state=None, is_remote=False, salary_min=None, salary_max=None, contact_email=None,
        skills=[], created_at=None), fields)
    doc.update(derived("jobs", doc))
    doc["created_at"] = doc["created_at"] or datetime.now()
    return doc


def event(**fields) -> Dict[str, Any]:
    doc = _build("event", dict(
        company_id=REQUIRED, name=REQUIRED, description=REQUIRED, event_datetime=REQUIRED,
        location=REQUIRED, city=REQUIRED,
        eligible_majors=[],   # ["Computer Science"] or ["All"]
        created_at=None), fields)
    doc.update(derived("events", doc))
    doc["created_at"] = doc["created_at"] or datetime.now()
    return doc


def application(**fields) -> Dict[str, Any]:
    now = datetime.now()
    doc = _build("application", dict(
        student_id=REQUIRED, job_id=REQUIRED,
        resume_file_id=None,                      # the resume PDF lives in GridFS (bucket "resumes")
        status=ApplicationStatus.pending, applied_at=None, updated_at=None,
        source_event_id=None, trace_id=None),     # the Kafka event that created it, and its trace (None for seeded ones)
        fields)
    doc["applied_at"] = doc["applied_at"] or now
    doc["updated_at"] = doc["updated_at"] or doc["applied_at"]
    return doc


def registration(**fields) -> Dict[str, Any]:
    return _build("registration", dict(student_id=REQUIRED, event_id=REQUIRED, registered_at=datetime.now()), fields)


def saved_item(**fields) -> Dict[str, Any]:
    return _build("saved_item", dict(student_id=REQUIRED, item_type=REQUIRED, item_id=REQUIRED,
                                     saved_at=datetime.now()), fields)


def preferences(**fields) -> Dict[str, Any]:
    return _build("preferences", dict(
        student_id=REQUIRED, preferred_categories=[], preferred_cities=[], preferred_roles=[],
        min_hourly_rate=None, open_to_remote=True, event_interests=[], updated_at=datetime.now()), fields)
