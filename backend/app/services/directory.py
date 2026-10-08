"""
Student directory search, kept out of the router so it can be reused (for example by an
assistant tool later).

    students, total = search_students(db, q="ada", major=["Computer Science"], skills=["Python"])
"""
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import Student, StudentSkill


def search_students(
    db: Session, *,
    q: Optional[str] = None,
    college: Optional[str] = None,
    major: Optional[Sequence[str]] = None,
    skills: Optional[Sequence[str]] = None,
    skills_match: str = "any",
    exclude_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Student], int]:
    """Filter students. Returns (students for this page, total matches), sorted by name.

    Every filter is optional and filters combine with AND.
    q            words that must each appear in the student's name OR college
    college      words that must each appear in the college name
    major        any of these majors, ignoring upper/lower case (OR)
    skills       students with any (default) or all of these skills, ignoring case
    exclude_id   leave this student out (so a student browsing doesn't see themselves)
    """
    conditions = []
    for word in (q or "").split()[:8]:
        conditions.append(or_(Student.name.icontains(word, autoescape=True),       # autoescape: a typed "%"
                              Student.college.icontains(word, autoescape=True)))   # is literal, not a wildcard
    for word in (college or "").split()[:8]:
        conditions.append(Student.college.icontains(word, autoescape=True))

    majors = [m.strip().lower() for m in (major or []) if m and m.strip()]
    if majors:
        conditions.append(func.lower(Student.major).in_(majors))

    wanted = sorted({s.strip().lower() for s in (skills or []) if s and s.strip()})
    if wanted:
        matching = select(StudentSkill.student_id).where(func.lower(StudentSkill.skill).in_(wanted))
        if skills_match == "all":
            matching = matching.group_by(StudentSkill.student_id).having(
                func.count(func.distinct(func.lower(StudentSkill.skill))) == len(wanted))
        conditions.append(Student.id.in_(matching))

    if exclude_id is not None:
        conditions.append(Student.id != exclude_id)

    total = db.scalar(select(func.count(Student.id)).where(*conditions)) or 0
    stmt = (select(Student).where(*conditions).options(selectinload(Student.skills))
            .order_by(func.lower(Student.name).asc(), Student.id.asc())
            .limit(page_size).offset((page - 1) * page_size))
    return list(db.scalars(stmt).all()), total