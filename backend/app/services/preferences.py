"""
Saved preferences, kept out of the router so the AI assistant's get_student_preferences
tool (Part B) can use exactly the same code as the website:

    pref = get_student_preferences(db, student_id)       # a row, or None when nothing is saved
    out  = to_preferences_out(pref)                       # out.saved tells you which
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import JobCategory, StudentPreference
from ..schemas.preferences import PreferencesIn, PreferencesOut

_VALID_CATEGORIES = {c.value for c in JobCategory}

def get_student_preferences(db: Session, student_id: int) -> Optional[StudentPreference]:
    return db.scalar(select(StudentPreference).where(StudentPreference.student_id == student_id))

def to_preferences_out(pref: Optional[StudentPreference]) -> PreferencesOut:
    if pref is None:
        return PreferencesOut(saved=False, preferred_categories=[], preferred_cities=[], preferred_roles=[],
                              min_hourly_rate=None, open_to_remote=True, event_interests=[], updated_at=None)
    return PreferencesOut(
        saved=True,
        # defensive: ignore anything in the database that is not a real category
        preferred_categories=[JobCategory(c) for c in (pref.preferred_categories or []) if c in _VALID_CATEGORIES],
        preferred_cities=list(pref.preferred_cities or []),
        preferred_roles=list(pref.preferred_roles or []),
        min_hourly_rate=pref.min_hourly_rate,
        open_to_remote=True if pref.open_to_remote is None else bool(pref.open_to_remote),
        event_interests=list(pref.event_interests or []),
        updated_at=pref.updated_at,
    )

def save_preferences(db: Session, student_id: int, data: PreferencesIn) -> StudentPreference:
    """Create the student's preferences, or replace them if they already exist."""
    pref = get_student_preferences(db, student_id)
    if pref is None:
        pref = StudentPreference(student_id=student_id)
        db.add(pref)
    pref.preferred_categories = [c.value for c in data.preferred_categories]
    pref.preferred_cities = list(data.preferred_cities)
    pref.preferred_roles = list(data.preferred_roles)
    pref.min_hourly_rate = data.min_hourly_rate
    pref.open_to_remote = data.open_to_remote
    pref.event_interests = list(data.event_interests)
    db.commit()
    db.refresh(pref)
    return pref

def clear_preferences(db: Session, student_id: int) -> None:
    pref = get_student_preferences(db, student_id)
    if pref is not None:
        db.delete(pref)
        db.commit()