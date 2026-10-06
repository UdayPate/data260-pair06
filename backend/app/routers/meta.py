"""
Read-only lists the React forms use for dropdowns (majors, skills, categories...).
Public (no login needed) because it contains no personal data. It reads from the same
skills.py the seed generator and the AI assistant use, so everyone sees one vocabulary.
"""
from fastapi import APIRouter

from ..config import CITY_SET
from ..models import ApplicationStatus, JobCategory
from ..skills import DEGREES, MAJORS, SKILLS_BY_AREA

router = APIRouter(prefix="/meta", tags=["Reference data"])


@router.get("/options", summary="Dropdown options for forms and filters")
def options():
    return {
        "cities": CITY_SET,
        "majors": MAJORS,
        "degrees": DEGREES,
        "skills_by_area": SKILLS_BY_AREA,
        "job_categories": [c.value for c in JobCategory],
        "application_statuses": [s.value for s in ApplicationStatus],
    }