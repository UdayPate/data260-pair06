"""
Saved preferences, kept out of the router so the AI assistant's get_student_preferences
tool (Part B) can use exactly the same code as the website:

    pref = get_student_preferences(db, student_id)       # a document, or None when nothing is saved
    out  = to_preferences_out(pref)                       # out.saved tells you which
"""
from datetime import datetime
from typing import Optional

from pymongo.database import Database

from .. import documents, mongo
from ..enums import JobCategory
from ..mongo import Doc
from ..schemas.preferences import PreferencesIn, PreferencesOut

_VALID_CATEGORIES = {c.value for c in JobCategory}


def get_student_preferences(db: Database, student_id: int) -> Optional[Doc]:
    return mongo.find_one(db, "student_preferences", {"student_id": student_id})


def to_preferences_out(pref: Optional[Doc]) -> PreferencesOut:
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


def save_preferences(db: Database, student_id: int, data: PreferencesIn) -> Doc:
    """Create the student's preferences, or replace them if they already exist.
    A second save at the same instant hits the unique index on student_id (DuplicateKeyError); the router retries."""
    fields = dict(
        preferred_categories=[c.value for c in data.preferred_categories],
        preferred_cities=list(data.preferred_cities),
        preferred_roles=list(data.preferred_roles),
        min_hourly_rate=data.min_hourly_rate,
        open_to_remote=data.open_to_remote,
        event_interests=list(data.event_interests),
        updated_at=datetime.now(),
    )
    pref = get_student_preferences(db, student_id)
    if pref is None:
        return mongo.insert(db, "student_preferences", documents.preferences(student_id=student_id, **fields))
    mongo.update(db, "student_preferences", pref.id, fields)
    return mongo.get(db, "student_preferences", pref.id)


def clear_preferences(db: Database, student_id: int) -> None:
    db.student_preferences.delete_one({"student_id": student_id})
