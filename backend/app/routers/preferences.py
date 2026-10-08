"""
A student's saved job and event preferences (students only, always their OWN).

    GET    /students/me/preferences   read them (saved: false if none are saved yet)
    PUT    /students/me/preferences   save them (replaces the whole set)
    DELETE /students/me/preferences   forget them
"""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.deps import require_student
from ..database import get_db
from ..models import Student
from ..schemas.preferences import PreferencesIn, PreferencesOut
from ..services.preferences import (clear_preferences, get_student_preferences, save_preferences,
                                    to_preferences_out)

router = APIRouter(prefix="/students/me/preferences", tags=["Student preferences"])

@router.get("", response_model=PreferencesOut, summary="My saved job and event preferences")
def read_preferences(student: Student = Depends(require_student), db: Session = Depends(get_db)):
    return to_preferences_out(get_student_preferences(db, student.id))

@router.put("", response_model=PreferencesOut, summary="Save my preferences (replaces any saved ones)")
def write_preferences(body: PreferencesIn, student: Student = Depends(require_student),
                      db: Session = Depends(get_db)):
    try:
        pref = save_preferences(db, student.id, body)
    except IntegrityError:        # two saves at the same instant: the UNIQUE(student) rule caught it
        db.rollback()
        pref = save_preferences(db, student.id, body)
    return to_preferences_out(pref)

@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Forget my saved preferences")
def delete_preferences(student: Student = Depends(require_student), db: Session = Depends(get_db)):
    clear_preferences(db, student.id)          # fine to call when nothing is saved
    return Response(status_code=status.HTTP_204_NO_CONTENT)