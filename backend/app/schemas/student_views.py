"""
How a student looks to OTHER people (companies reviewing applicants now, the student
directory in a later step).

Privacy choice: companies see contact details and the career profile, but NOT the date of
birth (it isn't needed to evaluate an application, and showing it invites age bias).
Compare with StudentProfile in profile.py, which is the student's OWN view and does
include the date of birth.
"""
from typing import List, Optional

from pydantic import BaseModel

from .profile import ExperienceOut


class StudentCard(BaseModel):
    """Short version for lists."""
    id: int
    name: str
    email: str
    college: str
    major: Optional[str]
    degree: Optional[str]
    graduation_year: Optional[int]
    cgpa: Optional[float]
    city: Optional[str]
    state: Optional[str]
    profile_pic_url: Optional[str]
    skills: List[str]


class StudentForEmployer(StudentCard):
    """Full version for one student: the card plus the rest of the profile (no date of birth)."""
    country: Optional[str]
    career_objective: Optional[str]
    phone: Optional[str]
    experience: List[ExperienceOut]