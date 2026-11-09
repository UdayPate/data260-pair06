"""
A student's saved job and event preferences (students only, always their OWN).

    GET    /students/me/preferences   read them (saved: false if none are saved yet)
    PUT    /students/me/preferences   save them (replaces the whole set)
    DELETE /students/me/preferences   forget them
"""
from fastapi import APIRouter, Depends, Response, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..core.deps import require_student
from ..mongo import Doc, get_db
from ..schemas.preferences import PreferencesIn, PreferencesOut
from ..services.activity_log import log_activity
from ..services.preferences import (clear_preferences, get_student_preferences, save_preferences,
                                    to_preferences_out)

router = APIRouter(prefix="/students/me/preferences", tags=["Student preferences"])

@router.get("", response_model=PreferencesOut, summary="My saved job and event preferences")
def read_preferences(student: Doc = Depends(require_student), db: Database = Depends(get_db)):
    return to_preferences_out(get_student_preferences(db, student.id))

@router.put("", response_model=PreferencesOut, summary="Save my preferences (replaces any saved ones)")
def write_preferences(body: PreferencesIn, student: Doc = Depends(require_student),
                      db: Database = Depends(get_db)):
    try:
        pref = save_preferences(db, student.id, body)
    except DuplicateKeyError:     # two saves at the same instant: the unique index on student_id caught it
        pref = save_preferences(db, student.id, body)
    log_activity(db, "student", student.id, "preferences_saved")
    return to_preferences_out(pref)

@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Forget my saved preferences")
def delete_preferences(student: Doc = Depends(require_student), db: Database = Depends(get_db)):
    clear_preferences(db, student.id)          # fine to call when nothing is saved
    return Response(status_code=status.HTTP_204_NO_CONTENT)