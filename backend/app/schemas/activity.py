"""
Schema for the application activity heatmap on the student home page.

GET /students/me/activity returns a list with one item for each day on which the student
applied to at least one job. Days with no applications are left out; the website treats a
missing day as zero.
"""
from datetime import date

from pydantic import BaseModel


class ActivityDay(BaseModel):
    date: date
    count: int   # how many applications were sent on that day (always 1 or more)
