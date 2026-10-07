"""
Helpers that replace a list of child rows (skills, eligible majors...) without clashing with
UNIQUE rules.

Why not "delete everything, insert everything"? The child tables have a UNIQUE rule
(owner, value). If a value stays in the list, deleting and re-inserting it in the same
save would clash with that rule. So we compare old and new (ignoring upper/lower case)
and change only what differs.
"""
from typing import Any, Callable, List


def sync_values(rows: List[Any], new_values: List[str], make_row: Callable[[str], Any], attr: str) -> None:
    """Make `rows` match `new_values`, comparing the text stored in attribute `attr`.

    rows       - the SQLAlchemy relationship list (changes are saved on commit)
    new_values - already cleaned names, e.g. ["Python", "SQL"]
    make_row   - builds a new row, e.g. lambda text: JobSkill(skill=text)
    attr       - which attribute holds the text: "skill" or "major"
    """
    existing = {getattr(row, attr).lower(): row for row in rows}
    wanted = {value.lower(): value for value in new_values}

    for key, row in list(existing.items()):
        if key not in wanted:
            rows.remove(row)                       # delete-orphan removes it from MySQL
        elif getattr(row, attr) != wanted[key]:
            setattr(row, attr, wanted[key])        # same value, spelling/casing fixed

    for key, text in wanted.items():
        if key not in existing:
            rows.append(make_row(text))


def sync_skills(rows: List[Any], new_skills: List[str], make_row: Callable[[str], Any]) -> None:
    """Replace a student's or job's skill rows."""
    sync_values(rows, new_skills, make_row, "skill")