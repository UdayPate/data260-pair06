"""
Student directory search, kept out of the router so it can be reused (for example by an
assistant tool later).

    students, total = search_students(db, q="ada", major=["Computer Science"], skills=["Python"])
"""
from typing import List, Optional, Sequence, Tuple

from pymongo.database import Database

from .. import mongo
from ..mongo import Doc, contains, equals_ignoring_case


def search_students(
    db: Database, *,
    q: Optional[str] = None,
    college: Optional[str] = None,
    major: Optional[Sequence[str]] = None,
    skills: Optional[Sequence[str]] = None,
    skills_match: str = "any",
    exclude_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Doc], int]:
    """Filter students. Returns (students for this page, total matches), sorted by name.

    Every filter is optional and filters combine with AND.
    q            words that must each appear in the student's name OR college
    college      words that must each appear in the college name
    major        any of these majors, ignoring upper/lower case (OR)
    skills       students with any (default) or all of these skills, ignoring case
    exclude_id   leave this student out (so a student browsing doesn't see themselves)
    """
    conditions: List[dict] = []
    for word in (q or "").split()[:8]:
        conditions.append({"$or": [{"name": contains(word)}, {"college": contains(word)}]})
    for word in (college or "").split()[:8]:
        conditions.append({"college": contains(word)})

    majors = [m.strip() for m in (major or []) if m and m.strip()]
    if majors:
        conditions.append({"$or": [{"major": equals_ignoring_case(m)} for m in majors]})

    wanted = sorted({s.strip().lower() for s in (skills or []) if s and s.strip()})
    if wanted:
        conditions.append({"skills_lower": {"$all" if skills_match == "all" else "$in": wanted}})

    if exclude_id is not None:
        conditions.append({"_id": {"$ne": exclude_id}})

    return mongo.page(db, "students", {"$and": conditions} if conditions else {},
                      [("name_lower", 1), ("_id", 1)], page, page_size)
