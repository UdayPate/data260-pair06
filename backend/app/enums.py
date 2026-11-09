"""
The fixed sets of allowed values (enums) shared by the schemas, services and routers.
They were part of models.py in Lab 1; MongoDB has no table classes, so they live here.
The database stores the plain text value, for example "internship" or "Pending".
"""
import enum


class JobCategory(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    on_campus = "on_campus"
    internship = "internship"


class PayPeriod(str, enum.Enum):
    hourly = "hourly"
    yearly = "yearly"


class ApplicationStatus(str, enum.Enum):
    pending = "Pending"
    reviewed = "Reviewed"
    declined = "Declined"


class SavedItemType(str, enum.Enum):
    job = "job"
    event = "event"
