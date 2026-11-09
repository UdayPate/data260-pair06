"""
Notifications (Lab 2): a short message for a user, written by the Kafka workers (a status change, an event registration,
a new job that matches the student's saved preferences). They are stored in the `notifications` collection; showing them
in the website is not part of this lab.

    {_id: "<event_id>:student:12", user_role: "student", user_id: 12, kind: "application_status", title: "...",
     body: "...", ref_type: "application", ref_id: 7, source_event_id: "<event_id>", trace_id: "...",
     created_at: <UTC>, read: false}

The _id is made from the Kafka event_id and the user, so the SAME event can never create the same notification twice:
that is what makes the workers idempotent.
"""
from typing import Optional

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..core.sessions import utc_now


def notify(db: Database, *, user_id: int, kind: str, title: str, body: str, event_id: str, trace_id: str,
           ref_type: Optional[str] = None, ref_id: Optional[int] = None, role: str = "student") -> bool:
    """Create one notification. Returns False when this event already created it (a duplicate delivery)."""
    try:
        db.notifications.insert_one({
            "_id": f"{event_id}:{role}:{user_id}", "user_role": role, "user_id": user_id, "kind": kind,
            "title": title, "body": body, "ref_type": ref_type, "ref_id": ref_id,
            "source_event_id": event_id, "trace_id": trace_id, "created_at": utc_now(), "read": False,
        })
        return True
    except DuplicateKeyError:
        return False
