"""
Activity log (Lab 2): one document in `activity_logs` for each important thing a user does.

    {_id, at: <UTC time>, actor_role: "student", actor_id: 12, action: "application_created",
     ref_type: "job", ref_id: 7, detail: {...}}

Actions written today: signup, login, logout, profile_updated, preferences_saved, job_created, job_updated,
application_created, application_status_changed, event_created, event_updated, event_registered,
event_unregistered, item_saved. Writing a log entry must never break the request that caused it, so a database
problem here is logged and ignored.
"""
import logging
from typing import Optional

from pymongo.database import Database
from pymongo.errors import PyMongoError

from ..core.sessions import utc_now

logger = logging.getLogger("handshake")


def log_activity(db: Database, role: str, user_id: int, action: str, ref_type: Optional[str] = None,
                 ref_id: Optional[int] = None, detail: Optional[dict] = None) -> None:
    try:
        db.activity_logs.insert_one({
            "at": utc_now(), "actor_role": role, "actor_id": user_id, "action": action,
            "ref_type": ref_type, "ref_id": ref_id, "detail": detail or {},
        })
    except PyMongoError as exc:
        logger.warning("Could not write the activity log (%s): %s", action, exc)
