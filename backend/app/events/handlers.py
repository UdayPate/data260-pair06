"""
What the workers DO with each event: one handler per event type. A handler gets the database and the parsed envelope,
does its database writes, and returns "processed" or "duplicate". Every handler is IDEMPOTENT: if the same event (or the
same business fact) arrives twice, the second time changes nothing and returns "duplicate". That matters because Kafka
delivers at least once: a worker killed after its database write but before it committed the offset sees the message again.

A handler raises PermanentError for a message that can never succeed (a student that does not exist, a missing field);
the worker then sends it to the dead-letter topic instead of retrying. Any other exception is treated as temporary
(for example MongoDB being restarted) and the worker retries a few times first.
"""
import logging
from datetime import datetime
from typing import Callable, Dict

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import documents, mongo
from ..services.activity_log import log_activity
from ..services.notifications import notify
from . import topics
from .envelope import Envelope
from .errors import PermanentError

logger = logging.getLogger("handshake.worker")
PROCESSED, DUPLICATE = "processed", "duplicate"


def _need(payload: dict, name: str, kind: type):
    value = payload.get(name)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise PermanentError(f"payload.{name} is missing or is not {kind.__name__}")
    return value


def _when(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise PermanentError(f"payload.applied_at is not an ISO time: {text!r}") from None


# ---------------------------------------------------------------- application.created
def _drop_unused_resume(db: Database, existing, resume_id: ObjectId) -> None:
    """A second, different event for the same student and job (a double click) stored its own copy of the PDF.
    The application that already exists keeps its file; the extra copy is deleted. A redelivery of the SAME event has the
    same file id as the existing application and deletes nothing."""
    if existing is not None and existing.resume_file_id != resume_id:
        mongo.bucket(db, "resumes").delete(resume_id)


def handle_application_created(db: Database, env: Envelope) -> str:
    """The student applied: write the application. Natural key = (student_id, job_id), which also has a unique index."""
    p = env.payload
    student_id, job_id = _need(p, "student_id", int), _need(p, "job_id", int)
    resume_text, applied_at = _need(p, "resume_file_id", str), _when(_need(p, "applied_at", str))
    try:
        resume_id = ObjectId(resume_text)
    except (InvalidId, TypeError):
        raise PermanentError(f"payload.resume_file_id is not a file id: {resume_text!r}") from None
    if mongo.get(db, "students", student_id) is None:
        raise PermanentError(f"student {student_id} does not exist")
    if mongo.get(db, "jobs", job_id) is None:
        raise PermanentError(f"job {job_id} does not exist")
    if not mongo.bucket(db, "resumes").exists(resume_id):
        raise PermanentError("the resume file is not in the database")

    existing = mongo.find_one(db, "applications", {"student_id": student_id, "job_id": job_id})
    if existing is not None:
        _drop_unused_resume(db, existing, resume_id)
        return DUPLICATE                                   # this event, or an earlier one, already created it
    try:
        application = mongo.insert(db, "applications", documents.application(
            student_id=student_id, job_id=job_id, resume_file_id=resume_id, applied_at=applied_at,
            source_event_id=env.event_id, trace_id=env.trace_id))
    except DuplicateKeyError:                              # two workers at the same instant: the unique index decided
        _drop_unused_resume(db, mongo.find_one(db, "applications", {"student_id": student_id, "job_id": job_id}), resume_id)
        return DUPLICATE
    log_activity(db, "student", student_id, "application_created", "application", application.id,
                 {"job_id": job_id, "trace_id": env.trace_id}, event_id=env.event_id)
    return PROCESSED


# ---------------------------------------------------------------- application.updated
def handle_application_updated(db: Database, env: Envelope) -> str:
    """Reserved flow: an application's data changed (today only the resume file can). No API produces it yet."""
    p = env.payload
    application_id, changes = _need(p, "application_id", int), _need(p, "changes", dict)
    if mongo.get(db, "applications", application_id) is None:
        raise PermanentError(f"application {application_id} does not exist")
    unknown = set(changes) - {"resume_file_id"}
    if unknown:
        raise PermanentError(f"changes may only contain resume_file_id, not {sorted(unknown)}")
    update = {}
    if "resume_file_id" in changes:
        try:
            update["resume_file_id"] = ObjectId(changes["resume_file_id"])
        except (InvalidId, TypeError):
            raise PermanentError("changes.resume_file_id is not a file id") from None
    mongo.update(db, "applications", application_id, {**update, "updated_at": _when(env.timestamp.replace("Z", ""))})
    return PROCESSED                                       # setting the same values again changes nothing: idempotent


# ---------------------------------------------------------------- application.status_changed
def handle_application_status_changed(db: Database, env: Envelope) -> str:
    """A company changed an application's status: tell the student. (The status itself was already saved by the API.)"""
    p = env.payload
    application_id, student_id = _need(p, "application_id", int), _need(p, "student_id", int)
    title, company = _need(p, "job_title", str), _need(p, "company_name", str)
    old, new = _need(p, "old_status", str), _need(p, "new_status", str)
    created = notify(db, user_id=student_id, kind="application_status", title=f"Application update: {title}",
                     body=f"{company} changed the status of your application from {old} to {new}.",
                     ref_type="application", ref_id=application_id, event_id=env.event_id, trace_id=env.trace_id)
    return PROCESSED if created else DUPLICATE


# ---------------------------------------------------------------- event.registration_created
def handle_registration_created(db: Database, env: Envelope) -> str:
    """A student registered for an event: confirm it with a notification."""
    p = env.payload
    student_id, event_id = _need(p, "student_id", int), _need(p, "event_id", int)
    name, when = _need(p, "event_name", str), _need(p, "event_datetime", str)
    created = notify(db, user_id=student_id, kind="event_registration", title=f"You are registered: {name}",
                     body=f"Your registration for {name} on {when} is confirmed.",
                     ref_type="event", ref_id=event_id, event_id=env.event_id, trace_id=env.trace_id)
    return PROCESSED if created else DUPLICATE


# ---------------------------------------------------------------- job.created
def preferences_match(pref: dict, job: dict) -> bool:
    """Does a student's saved preferences fit a new job? Empty lists mean "no preference"."""
    categories = pref.get("preferred_categories") or []
    if categories and job["category"] not in categories:
        return False
    cities = [c.lower() for c in pref.get("preferred_cities") or []]
    if cities:
        remote_ok = job["is_remote"] and pref.get("open_to_remote") is not False
        if job["city"].lower() not in cities and not remote_ok:
            return False
    return True


def handle_job_created(db: Database, env: Envelope) -> str:
    """A company posted a job: notify every student whose saved preferences match it."""
    p = env.payload
    job = {"job_id": _need(p, "job_id", int), "title": _need(p, "title", str), "company": _need(p, "company_name", str),
           "category": _need(p, "category", str), "city": _need(p, "city", str), "is_remote": bool(p.get("is_remote"))}
    created = 0
    for pref in db.student_preferences.find({}):
        if preferences_match(pref, job):
            created += notify(db, user_id=pref["student_id"], kind="new_job_match",
                              title=f"New job that fits you: {job['title']}",
                              body=f"{job['company']} posted {job['title']} ({job['category']}, {job['city']}).",
                              ref_type="job", ref_id=job["job_id"], event_id=env.event_id, trace_id=env.trace_id)
    logger.info("event=job.created job_id=%s notifications_created=%s trace_id=%s", job["job_id"], created, env.trace_id)
    return PROCESSED


HANDLERS: Dict[str, Callable[[Database, Envelope], str]] = {
    topics.APPLICATION_CREATED: handle_application_created,
    topics.APPLICATION_UPDATED: handle_application_updated,
    topics.APPLICATION_STATUS_CHANGED: handle_application_status_changed,
    topics.EVENT_REGISTRATION_CREATED: handle_registration_created,
    topics.JOB_CREATED: handle_job_created,
}


def dispatch(db: Database, env: Envelope) -> str:
    handler = HANDLERS.get(env.event_type)
    if handler is None:
        raise PermanentError(f"no handler for event_type {env.event_type!r}")
    return handler(db, env)
