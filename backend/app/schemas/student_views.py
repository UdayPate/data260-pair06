"""
How a student looks to OTHER people (companies reviewing applicants now, the student
directory in a later step).

Three different views of a student, depending on who is looking:
    StudentProfile   (profile.py)  the student's OWN view: everything, including date of birth
    StudentForEmployer / StudentCard   a COMPANY's view: contact details and the career profile,
                     but NOT the date of birth (not needed to evaluate someone, invites age bias)
    PeerProfile / PeerCard   another STUDENT's view: who they are and what they study, but no
                     email, phone, GPA, date of birth or home city
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


class PeerCard(BaseModel):
    """Short version of a student as another student sees them."""
    id: int
    name: str
    college: str
    major: Optional[str]
    degree: Optional[str]
    graduation_year: Optional[int]
    profile_pic_url: Optional[str]
    skills: List[str]


class PeerProfile(PeerCard):
    career_objective: Optional[str]
    experience: List[ExperienceOut]


class StudentsPage(BaseModel):
    """Directory page as a COMPANY sees it."""
    items: List[StudentCard]
    total: int
    page: int
    page_size: int
    total_pages: int


class PeersPage(BaseModel):
    """Directory page as a STUDENT sees it."""
    items: List[PeerCard]
    total: int
    page: int
    page_size: int
    total_pages: int