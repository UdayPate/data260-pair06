"""
Event endpoints.

Company:  POST /events                     post an event
          GET  /events/mine                my events (with how many students registered)
          PATCH /events/{id}               edit my event
          GET  /events/{id}/registrations  the students registered for my event
Student:  POST   /events/{id}/register     register (if eligible)
          DELETE /events/{id}/register     cancel my registration
          GET    /events/registered        my registered events
Anyone logged in: GET /events (search, earliest first), GET /events/{id} (details)

Order matters: "/mine" and "/registered" are declared BEFORE "/{event_id}" so FastAPI
doesn't try to read those words as an event id.
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import documents, mongo
from ..core.deps import Identity, get_identity, require_company, require_student
from ..mongo import Doc, get_db
from ..schemas.events import (EventCreate, EventDetail, EventPage, EventUpdate, RegisteredStudent,
                              RegistrationOut, RegistrationsPage)
from ..services.activity_log import log_activity
from ..services.events import (ORDER, check_event_datetime, registered_event_ids, registration_block,
                               registration_counts, search_events, student_registered_events,
                               to_event_detail, to_event_summary, with_companies)
from ..services.jobs import total_pages
from ..services.students import to_student_card

router = APIRouter(prefix="/events", tags=["Events"])


def _datetime_rule_or_422(value: datetime) -> None:
    try:
        check_event_datetime(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def get_owned_event(event_id: int, company: Doc = Depends(require_company),
                    db: Database = Depends(get_db)) -> Doc:
    """The event in the URL (with event.company attached), but ONLY if it belongs to the logged-in company."""
    event = mongo.get(db, "events", event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if event.company_id != company.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only manage your own events")
    with_companies(db, [event])
    return event


def _page(events, total, page, page_size, db, student: Optional[Doc] = None) -> EventPage:
    now = datetime.now()
    ids = [e.id for e in events]
    counts = registration_counts(db, ids)
    registered = registered_event_ids(db, student.id, ids) if student is not None else None
    return EventPage(items=[to_event_summary(e, counts, now, student, registered) for e in events],
                     total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size))


# ---------------- company ----------------
@router.post("", response_model=EventDetail, status_code=status.HTTP_201_CREATED,
             summary="Post a new event (company only)")
def create_event(body: EventCreate, company: Doc = Depends(require_company), db: Database = Depends(get_db)):
    _datetime_rule_or_422(body.event_datetime)
    event = mongo.insert(db, "events", documents.event(
        company_id=company.id, name=body.name, description=body.description,
        event_datetime=body.event_datetime, location=body.location, city=body.city,
        eligible_majors=list(body.eligible_majors)))
    event["company"] = company
    log_activity(db, "company", company.id, "event_created", "event", event.id)
    return to_event_detail(event, db)


@router.get("/mine", response_model=EventPage, summary="My events with registration counts (company only)")
def my_events(
    include_past: bool = Query(True, description="Also show events that already happened"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    company: Doc = Depends(require_company), db: Database = Depends(get_db),
):
    conditions = {"company_id": company.id}
    if not include_past:
        conditions["event_datetime"] = {"$gte": datetime.now()}
    events, total = mongo.page(db, "events", conditions, ORDER, page, page_size)
    with_companies(db, events)
    return _page(events, total, page, page_size, db)


@router.patch("/{event_id}", response_model=EventDetail, summary="Edit one of my events (company only)")
def update_event(body: EventUpdate, event: Doc = Depends(get_owned_event), db: Database = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "event_datetime" in data:
        _datetime_rule_or_422(data["event_datetime"])
    changes = dict(data)       # students who already registered stay registered
    if "eligible_majors" in changes:
        changes["eligible_majors"] = list(changes["eligible_majors"])
    changes.update(documents.derived("events", changes))        # eligible_majors_lower
    mongo.update(db, "events", event.id, changes)
    updated = mongo.get(db, "events", event.id)
    with_companies(db, [updated])
    log_activity(db, "company", event.company_id, "event_updated", "event", event.id)
    return to_event_detail(updated, db)


@router.get("/{event_id}/registrations", response_model=RegistrationsPage,
            summary="Students registered for one of my events (company only)")
def event_registrations(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    event: Doc = Depends(get_owned_event), db: Database = Depends(get_db),
):
    rows, total = mongo.page(db, "event_registrations", {"event_id": event.id},
                             [("registered_at", -1), ("_id", -1)], page, page_size)
    mongo.attach(db, rows, "student_id", "students", "student")
    return RegistrationsPage(
        items=[RegisteredStudent(student=to_student_card(r.student), registered_at=r.registered_at) for r in rows],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size))


# ---------------- student ----------------
@router.get("/registered", response_model=EventPage, summary="Events I registered for (student only)")
def my_registered_events(
    include_past: bool = Query(False, description="Also show events that already happened"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    student: Doc = Depends(require_student), db: Database = Depends(get_db),
):
    events, total = student_registered_events(db, student.id, include_past=include_past,
                                              page=page, page_size=page_size)
    return _page(events, total, page, page_size, db, student)


@router.post("/{event_id}/register", response_model=RegistrationOut, status_code=status.HTTP_201_CREATED,
             summary="Register for an event (student only, if eligible)")
def register(event_id: int, student: Doc = Depends(require_student), db: Database = Depends(get_db)):
    event = mongo.get(db, "events", event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    already = bool(registered_event_ids(db, student.id, [event.id]))
    block = registration_block(event, student, already)
    if block is not None:
        raise HTTPException(block[0], block[1])

    try:
        registration = mongo.insert(db, "event_registrations", documents.registration(
            student_id=student.id, event_id=event.id, registered_at=datetime.now()))
    except DuplicateKeyError:     # two clicks at once: the unique (student, event) index caught it
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already registered for this event")
    with_companies(db, [event])
    log_activity(db, "student", student.id, "event_registered", "event", event.id)
    summary = to_event_summary(event, registration_counts(db, [event.id]), student=student,
                               registered_ids={event.id})
    return RegistrationOut(event=summary, registered_at=registration.registered_at)


@router.delete("/{event_id}/register", status_code=status.HTTP_204_NO_CONTENT,
               summary="Cancel my registration (student only)")
def unregister(event_id: int, student: Doc = Depends(require_student), db: Database = Depends(get_db)):
    registration = mongo.find_one(db, "event_registrations", {"student_id": student.id, "event_id": event_id})
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not registered for this event")
    event = mongo.get(db, "events", event_id)
    if event.event_datetime < datetime.now():
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has already taken place")
    db.event_registrations.delete_one({"_id": registration.id})
    log_activity(db, "student", student.id, "event_unregistered", "event", event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- everyone logged in ----------------
@router.get("", response_model=EventPage, summary="Search upcoming events (earliest first)")
def list_events(
    q: Optional[str] = Query(None, max_length=100, description="Words to find in the event name"),
    city: Optional[List[str]] = Query(None, max_length=10, description="Repeat to allow several"),
    date_from: Optional[date] = Query(None, description="Events on or after this date"),
    date_to: Optional[date] = Query(None, description="Events on or before this date"),
    major: Optional[str] = Query(None, max_length=100,
                                 description="Only events a student of this major may register for"),
    include_past: bool = Query(False, description="Also show events that already happened"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    identity: Identity = Depends(get_identity), db: Database = Depends(get_db),
):
    events, total = search_events(db, q=q, city=city, date_from=date_from, date_to=date_to, major=major,
                                  include_past=include_past, page=page, page_size=page_size)
    student = identity.user if identity.role == "student" else None
    return _page(events, total, page, page_size, db, student)


@router.get("/{event_id}", response_model=EventDetail, summary="Event details with company profile")
def get_event(event_id: int, identity: Identity = Depends(get_identity), db: Database = Depends(get_db)):
    event = mongo.get(db, "events", event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    with_companies(db, [event])
    student = identity.user if identity.role == "student" else None
    return to_event_detail(event, db, student=student)