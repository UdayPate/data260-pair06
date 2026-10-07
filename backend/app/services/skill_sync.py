"""
One helper used by BOTH students and jobs to replace a list of skills.

Why not "delete everything, insert everything"? The skill tables have a UNIQUE rule
(owner, skill). If a skill stays in the list, deleting and re-inserting it in the same
save would clash with that rule. So we compare old and new (ignoring upper/lower case)
and change only what differs.
"""
from typing import Any, Callable, List


def sync_skills(rows: List[Any], new_skills: List[str], make_row: Callable[[str], Any]) -> None:
    """Make `rows` (e.g. student.skills or job.skills) match `new_skills`.

    rows      - the SQLAlchemy relationship list (changes are saved on commit)
    new_skills- already cleaned skill names, e.g. ["Python", "SQL"]
    make_row  - builds a new row, e.g. lambda text: JobSkill(skill=text)
    """
    existing = {row.skill.lower(): row for row in rows}
    wanted = {skill.lower(): skill for skill in new_skills}

    for key, row in list(existing.items()):
        if key not in wanted:
            rows.remove(row)                 # delete-orphan removes it from MySQL
        elif row.skill != wanted[key]:
            row.skill = wanted[key]          # same skill, spelling/casing fixed

    for key, text in wanted.items():
        if key not in existing:
            rows.append(make_row(text))