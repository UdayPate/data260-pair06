"""
Builders that turn a Student database row into the views other people may see.
Kept here (not in a router) so the applicant screens and the later student directory
build them the same way.
"""
from datetime import date

from ..core.uploads import public_url
from ..models import Student
from ..schemas.profile import ExperienceOut
from ..schemas.student_views import StudentCard, StudentForEmployer


def _card_fields(s: Student) -> dict:
    return dict(
        id=s.id, name=s.name, email=s.email, college=s.college, major=s.major, degree=s.degree,
        graduation_year=s.graduation_year, cgpa=s.cgpa, city=s.city, state=s.state,
        profile_pic_url=public_url(s.profile_pic_path),
        skills=sorted((k.skill for k in s.skills), key=str.lower),
    )


def to_student_card(s: Student) -> StudentCard:
    return StudentCard(**_card_fields(s))


def to_employer_view(s: Student) -> StudentForEmployer:
    experiences = sorted(s.experiences, key=lambda e: e.start_date or date.min, reverse=True)
    return StudentForEmployer(
        **_card_fields(s), country=s.country, career_objective=s.career_objective, phone=s.phone,
        experience=[ExperienceOut.model_validate(e) for e in experiences],
    )