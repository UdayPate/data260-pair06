"""
Builders that turn a student document into the views other people may see.
Kept here (not in a router) so the applicant screens and the student directory
build them the same way.
"""
from datetime import date

from ..core.uploads import public_url
from ..mongo import Doc
from ..schemas.profile import ExperienceOut
from ..schemas.student_views import PeerCard, PeerProfile, StudentCard, StudentForEmployer


def _card_fields(s: Doc) -> dict:
    return dict(
        id=s.id, name=s.name, email=s.email, college=s.college, major=s.major, degree=s.degree,
        graduation_year=s.graduation_year, cgpa=s.cgpa, city=s.city, state=s.state,
        profile_pic_url=public_url(s.profile_pic_path),
        skills=sorted(s.skills, key=str.lower),
    )


def to_student_card(s: Doc) -> StudentCard:
    return StudentCard(**_card_fields(s))


def experience_out(s: Doc) -> list:
    """The student's experience entries, most recent start first."""
    experiences = sorted(s.experiences, key=lambda e: e.start_date or date.min, reverse=True)
    return [ExperienceOut.model_validate(e) for e in experiences]


def to_employer_view(s: Doc) -> StudentForEmployer:
    return StudentForEmployer(
        **_card_fields(s), country=s.country, career_objective=s.career_objective, phone=s.phone,
        experience=experience_out(s),
    )


def _peer_fields(s: Doc) -> dict:
    return dict(
        id=s.id, name=s.name, college=s.college, major=s.major, degree=s.degree,
        graduation_year=s.graduation_year, profile_pic_url=public_url(s.profile_pic_path),
        skills=sorted(s.skills, key=str.lower),
    )


def to_peer_card(s: Doc) -> PeerCard:
    return PeerCard(**_peer_fields(s))


def to_peer_profile(s: Doc) -> PeerProfile:
    return PeerProfile(**_peer_fields(s), career_objective=s.career_objective, experience=experience_out(s))
