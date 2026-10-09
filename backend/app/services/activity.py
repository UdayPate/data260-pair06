"""
Application activity for the heatmap: how many applications a student sent on each day.

We read the applied_at time of every application in the window and count them by calendar
date in Python. That is easy to follow and behaves the same on MySQL and on the SQLite
database used by the tests (date functions in SQL differ between the two).
"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application
from ..schemas.activity import ActivityDay


def application_activity(db: Session, student_id: int, days: int,
                         today: Optional[date] = None) -> List[ActivityDay]:
    """One {date, count} item per day with at least one application, oldest first.

    The window is the last `days` calendar days, ending today: with days=7 it covers today
    and the 6 days before it. Only the given student's applications are counted.
    """
    today = today or date.today()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min)                 # 00:00 on the first day
    end = datetime.combine(today + timedelta(days=1), time.min)   # up to, not including, tomorrow

    applied_times = db.scalars(
        select(Application.applied_at)
        .where(Application.student_id == student_id,
               Application.applied_at >= start,
               Application.applied_at < end)
    ).all()

    per_day = Counter(applied_at.date() for applied_at in applied_times)
    return [ActivityDay(date=day, count=per_day[day]) for day in sorted(per_day)]
