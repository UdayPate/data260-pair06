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
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, selectinload

from ..core.deps import Identity, get_identity, require_company, require_student
from ..database import get_db
from ..models import Company, Event, EventEligibleMajor, EventRegistration, Student
from ..schemas.events import (EventCreate, EventDetail, EventPage, EventUpdate, RegisteredStudent,
                              RegistrationOut, RegistrationsPage)
from ..services.events import (check_event_datetime, registered_event_ids, registration_block,
                               registration_counts, search_events, student_registered_events,
                               to_event_detail, to_event_summary)
from ..services.jobs import total_pages
from ..services.skill_sync import sync_values
from ..services.students import to_student_card

router = APIRouter(prefix="/events", tags=["Events"])


def _datetime_rule_or_422(value: datetime) -> None:
    try:
        check_event_datetime(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def get_owned_event(event_id: int, company: Company = Depends(require_company),
                    db: Session = Depends(get_db)) -> Event:
    """The event in the URL, but ONLY if it belongs to the logged-in company."""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if event.company_id != company.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only manage your own events")
    return event


def _page(events, total, page, page_size, db, student: Optional[Student] = None) -> EventPage:
    now = datetime.now()
    ids = [e.id for e in events]
    counts = registration_counts(db, ids)
    registered = registered_event_ids(db, student.id, ids) if student is not None else None
    return EventPage(items=[to_event_summary(e, counts, now, student, registered) for e in events],
                     total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size))


# ---------------- company ----------------
@router.post("", response_model=EventDetail, status_code=status.HTTP_201_CREATED,
             summary="Post a new event (company only)")
def create_event(body: EventCreate, company: Company = Depends(require_company), db: Session = Depends(get_db)):
    _datetime_rule_or_422(body.event_datetime)
    event = Event(company_id=company.id, name=body.name, description=body.description,
                  event_datetime=body.event_datetime, location=body.location, city=body.city)
    event.eligible_majors = [EventEligibleMajor(major=m) for m in body.eligible_majors]
    db.add(event)
    db.commit()
    db.refresh(event)
    return to_event_detail(event, db)


@router.get("/mine", response_model=EventPage, summary="My events with registration counts (company only)")
def my_events(
    include_past: bool = Query(True, description="Also show events that already happened"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    company: Company = Depends(require_company), db: Session = Depends(get_db),
):
    conditions = [Event.company_id == company.id]
    if not include_past:
        conditions.append(Event.event_datetime >= datetime.now())
    total = db.scalar(select(func.count(Event.id)).where(*conditions)) or 0
    events = db.scalars(select(Event).join(Event.company).where(*conditions)
                        .options(contains_eager(Event.company), selectinload(Event.eligible_majors))
                        .order_by(Event.event_datetime.asc(), Event.id.asc())
                        .limit(page_size).offset((page - 1) * page_size)).all()
    return _page(events, total, page, page_size, db)


@router.patch("/{event_id}", response_model=EventDetail, summary="Edit one of my events (company only)")
def update_event(body: EventUpdate, event: Event = Depends(get_owned_event), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    majors = data.pop("eligible_majors", None)
    if "event_datetime" in data:
        _datetime_rule_or_422(data["event_datetime"])
    for field, value in data.items():
        setattr(event, field, value)
    if majors is not None:     # students who already registered stay registered
        sync_values(event.eligible_majors, majors, lambda text: EventEligibleMajor(major=text), "major")
    db.commit()
    db.refresh(event)
    return to_event_detail(event, db)


@router.get("/{event_id}/registrations", response_model=RegistrationsPage,
            summary="Students registered for one of my events (company only)")
def event_registrations(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    event: Event = Depends(get_owned_event), db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(EventRegistration.id))
                      .where(EventRegistration.event_id == event.id)) or 0
    rows = db.scalars(select(EventRegistration).join(EventRegistration.student)
                      .where(EventRegistration.event_id == event.id)
                      .options(contains_eager(EventRegistration.student).selectinload(Student.skills))
                      .order_by(EventRegistration.registered_at.desc(), EventRegistration.id.desc())
                      .limit(page_size).offset((page - 1) * page_size)).all()
    return RegistrationsPage(
        items=[RegisteredStudent(student=to_student_card(r.student), registered_at=r.registered_at) for r in rows],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size))


# ---------------- student ----------------
@router.get("/registered", response_model=EventPage, summary="Events I registered for (student only)")
def my_registered_events(
    include_past: bool = Query(False, description="Also show events that already happened"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    student: Student = Depends(require_student), db: Session = Depends(get_db),
):
    events, total = student_registered_events(db, student.id, include_past=include_past,
                                              page=page, page_size=page_size)
    return _page(events, total, page, page_size, db, student)


@router.post("/{event_id}/register", response_model=RegistrationOut, status_code=status.HTTP_201_CREATED,
             summary="Register for an event (student only, if eligible)")
def register(event_id: int, student: Student = Depends(require_student), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    already = bool(registered_event_ids(db, student.id, [event.id]))
    block = registration_block(event, student, already)
    if block is not None:
        raise HTTPException(block[0], block[1])

    registration = EventRegistration(student_id=student.id, event_id=event.id, registered_at=datetime.now())
    db.add(registration)
    try:
        db.commit()
    except IntegrityError:        # two clicks at once: the UNIQUE (student, event) rule caught it
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already registered for this event")
    db.refresh(registration)
    summary = to_event_summary(event, registration_counts(db, [event.id]), student=student,
                               registered_ids={event.id})
    return RegistrationOut(event=summary, registered_at=registration.registered_at)


@router.delete("/{event_id}/register", status_code=status.HTTP_204_NO_CONTENT,
               summary="Cancel my registration (student only)")
def unregister(event_id: int, student: Student = Depends(require_student), db: Session = Depends(get_db)):
    registration = db.scalar(select(EventRegistration).where(EventRegistration.student_id == student.id,
                                                             EventRegistration.event_id == event_id))
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not registered for this event")
    if registration.event.event_datetime < datetime.now():
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has already taken place")
    db.delete(registration)
    db.commit()
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
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
):
    events, total = search_events(db, q=q, city=city, date_from=date_from, date_to=date_to, major=major,
                                  include_past=include_past, page=page, page_size=page_size)
    student = identity.user if identity.role == "student" else None
    return _page(events, total, page, page_size, db, student)


@router.get("/{event_id}", response_model=EventDetail, summary="Event details with company profile")
def get_event(event_id: int, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    student = identity.user if identity.role == "student" else None
    return to_event_detail(event, db, student=student)