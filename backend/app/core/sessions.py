"""
Login sessions (Lab 2). One document in the `sessions` collection per login:

    {_id: "<random id>", user_id: 12, role: "student", created_at: ..., expires_at: ...}

* The JWT carries the session id. get_identity (core/deps.py) accepts a token only while its session exists.
* Signing out deletes the session, so the token stops working at once (in Lab 1 a signed-out token stayed valid
  until it expired).
* `expires_at` has a TTL index (see mongo.INDEXES): MongoDB deletes the document itself after it expires.
  MongoDB checks about once a minute, so we ALSO compare expires_at with the clock on every request.
* Times are stored in UTC, because that is what MongoDB's TTL clock uses.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.database import Database

from .. import config


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)       # MongoDB treats a naive datetime as UTC


def create_session(db: Database, role: str, user_id: int) -> str:
    """Start a session for a login or signup and return its id."""
    now = utc_now()
    session_id = uuid.uuid4().hex
    db.sessions.insert_one({
        "_id": session_id, "role": role, "user_id": user_id,
        "created_at": now, "expires_at": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    })
    return session_id


def find_valid_session(db: Database, session_id: Optional[str]) -> Optional[dict]:
    """The session if it exists and has not expired, else None."""
    if not session_id:
        return None
    session = db.sessions.find_one({"_id": session_id})
    if session is None or session["expires_at"] <= utc_now():
        return None
    return session


def end_session(db: Database, session_id: str) -> None:
    db.sessions.delete_one({"_id": session_id})
