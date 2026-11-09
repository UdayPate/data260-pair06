"""
Application activity for the heatmap: how many applications a student sent on each day.

We read the applied_at time of every application in the window and count them by calendar
date in Python. That is easy to follow and works the same on real MongoDB and on the in-memory
database used by the tests.
"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from pymongo.database import Database

from ..schemas.activity import ActivityDay


def application_activity(db: Database, student_id: int, days: int,
                         today: Optional[date] = None) -> List[ActivityDay]:
    """One {date, count} item per day with at least one application, oldest first.

    The window is the last `days` calendar days, ending today: with days=7 it covers today
    and the 6 days before it. Only the given student's applications are counted.
    """
    today = today or date.today()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min)                 # 00:00 on the first day
    end = datetime.combine(today + timedelta(days=1), time.min)   # up to, not including, tomorrow

    rows = db.applications.find({"student_id": student_id, "applied_at": {"$gte": start, "$lt": end}},
                                {"applied_at": 1})
    per_day = Counter(row["applied_at"].date() for row in rows)
    return [ActivityDay(date=day, count=per_day[day]) for day in sorted(per_day)]
