"""
Student directory: browse, search and open other students' profiles.

    GET /students          search (name or college, major, skills), sorted by name
    GET /students/{id}     one student's profile

What you see depends on WHO you are:
    company  -> contact details and the career profile (no date of birth)
    student  -> a limited "peer" view: name, college, major, skills, objective, experience
                (no email, phone, GPA, date of birth or home city)

IMPORTANT: this router is included in main.py AFTER the student-profile router, because that
router owns "/students/me". If this one came first, FastAPI would try to read the word "me"
as a student id.
"""
from typing import List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import Identity, get_identity
from ..database import get_db
from ..models import Student
from ..schemas.student_views import (PeerProfile, PeersPage, StudentForEmployer, StudentsPage)
from ..services.directory import search_students
from ..services.jobs import total_pages
from ..services.students import (to_employer_view, to_peer_card, to_peer_profile, to_student_card)

router = APIRouter(prefix="/students", tags=["Student directory"])


@router.get("", response_model=Union[StudentsPage, PeersPage],
            summary="Browse and search students (what you see depends on whether you are a company or a student)")
def list_students(
    q: Optional[str] = Query(None, max_length=100, description="Words in the student's name or college"),
    college: Optional[str] = Query(None, max_length=150, description="Words in the college name"),
    major: Optional[List[str]] = Query(None, max_length=10, description="Repeat to allow several"),
    skills: Optional[List[str]] = Query(None, max_length=10, description="Repeat to require several"),
    skills_match: Literal["any", "all"] = Query("any"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
):
    is_company = identity.role == "company"
    students, total = search_students(
        db, q=q, college=college, major=major, skills=skills, skills_match=skills_match,
        exclude_id=None if is_company else identity.user.id,      # a student doesn't see themselves
        page=page, page_size=page_size)
    pages = total_pages(total, page_size)
    if is_company:
        return StudentsPage(items=[to_student_card(s) for s in students], total=total, page=page,
                            page_size=page_size, total_pages=pages)
    return PeersPage(items=[to_peer_card(s) for s in students], total=total, page=page,
                     page_size=page_size, total_pages=pages)


@router.get("/{student_id}", response_model=Union[StudentForEmployer, PeerProfile],
            summary="View one student's profile (company: full profile; student: limited peer profile)")
def get_student(student_id: int, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    if identity.role == "company":
        return to_employer_view(student)
    return to_peer_profile(student)