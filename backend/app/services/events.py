"""
Event business logic, kept OUT of the router so two callers can share it:
    1. the REST endpoint  GET /events        (routers/events.py)
    2. the AI assistant's search_events tool (Part B, written by your partner)

Example for the assistant ("an event for computer science students next month"):
    events, total = search_events(db, major="Computer Science",
                                  date_from=date(2026, 11, 1), date_to=date(2026, 11, 30))
"""
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from ..core.uploads import public_url
from ..models import Event, EventEligibleMajor, EventRegistration, Student
from ..schemas.events import ALL_MAJORS, EventDetail, EventSummary
from ..schemas.jobs import CompanyMini
from ..schemas.profile import CompanyPublic

MAX_FUTURE_DAYS = 730


# ---------------- rules ----------------
def check_event_datetime(value: datetime, now: Optional[datetime] = None) -> None:
    """A new or rescheduled event must be in the future (but not more than 2 years away)."""
    now = now or datetime.now()
    if value <= now:
        raise ValueError("event_datetime must be in the future")
    if value > now + timedelta(days=MAX_FUTURE_DAYS):
        raise ValueError("event_datetime must be within the next 2 years")


def is_eligible(event_majors: Iterable[str], student_major: Optional[str]) -> bool:
    """Open to 'All', or the student's major is on the list (ignoring upper/lower case)."""
    lowered = {m.lower() for m in event_majors}
    if ALL_MAJORS.lower() in lowered:
        return True
    return bool(student_major) and student_major.lower() in lowered


def registration_block(event: Event, student: Student, already_registered: bool,
                       now: Optional[datetime] = None) -> Optional[Tuple[int, str]]:
    """Why this student cannot register, as (HTTP status, message), or None if they can."""
    now = now or datetime.now()
    if event.event_datetime < now:
        return 409, "This event has already taken place"
    if already_registered:
        return 409, "You are already registered for this event"
    majors = [m.major for m in event.eligible_majors]
    if not is_eligible(majors, student.major):
        open_to = ", ".join(sorted(majors, key=str.lower))
        if not student.major:
            return 403, f"This event is open to {open_to} majors. Add your major to your profile to register"
        return 403, f"This event is open to {open_to} majors only (your major: {student.major})"
    return None


# ---------------- lookups ----------------
def registration_counts(db: Session, event_ids: Sequence[int]) -> Dict[int, int]:
    """{event_id: number of registered students} (events with none are absent)."""
    if not event_ids:
        return {}
    rows = db.execute(select(EventRegistration.event_id, func.count(EventRegistration.id))
                      .where(EventRegistration.event_id.in_(event_ids))
                      .group_by(EventRegistration.event_id)).all()
    return {event_id: count for event_id, count in rows}


def registered_event_ids(db: Session, student_id: int, event_ids: Sequence[int]) -> Set[int]:
    """Which of these events has this student registered for?"""
    if not event_ids:
        return set()
    return set(db.scalars(select(EventRegistration.event_id)
                          .where(EventRegistration.student_id == student_id,
                                 EventRegistration.event_id.in_(event_ids))).all())


def _eager():
    return (contains_eager(Event.company), selectinload(Event.eligible_majors))


def search_events(
    db: Session, *,
    q: Optional[str] = None,
    city: Optional[Sequence[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    major: Optional[str] = None,
    include_past: bool = False,
    page: int = 1,
    page_size: int = 20,
    now: Optional[datetime] = None,
) -> Tuple[List[Event], int]:
    """Filter events. Returns (events for this page, total matches), earliest first.

    Every filter is optional and filters combine with AND.
    q            words that must each appear in the event name
    city         any of these cities, case-insensitive
    date_from/to events starting on or after / on or before these dates (whole days)
    major        events a student of this major may register for (open to it, or to All)
    include_past False (default) shows only events that have not started yet
    """
    now = now or datetime.now()
    conditions = []
    for word in (q or "").split()[:8]:
        conditions.append(Event.name.icontains(word, autoescape=True))   # a typed "%" is literal
    cities = [c.strip().lower() for c in (city or []) if c and c.strip()]
    if cities:
        conditions.append(func.lower(Event.city).in_(cities))
    if date_from is not None:
        conditions.append(Event.event_datetime >= datetime.combine(date_from, time.min))
    if date_to is not None:
        conditions.append(Event.event_datetime < datetime.combine(date_to + timedelta(days=1), time.min))
    if major and major.strip():
        open_to = select(EventEligibleMajor.event_id).where(or_(
            func.lower(EventEligibleMajor.major) == ALL_MAJORS.lower(),
            func.lower(EventEligibleMajor.major) == major.strip().lower()))
        conditions.append(Event.id.in_(open_to))
    if not include_past:
        conditions.append(Event.event_datetime >= now)

    total = db.scalar(select(func.count()).select_from(
        select(Event.id).join(Event.company).where(*conditions).subquery())) or 0
    stmt = (select(Event).join(Event.company).where(*conditions).options(*_eager())
            .order_by(Event.event_datetime.asc(), Event.id.asc())
            .limit(page_size).offset((page - 1) * page_size))
    return list(db.scalars(stmt).all()), total


def student_registered_events(db: Session, student_id: int, *, include_past: bool = False,
                              page: int = 1, page_size: int = 20,
                              now: Optional[datetime] = None) -> Tuple[List[Event], int]:
    """Events this student registered for, earliest first."""
    now = now or datetime.now()
    conditions = [EventRegistration.student_id == student_id]
    if not include_past:
        conditions.append(Event.event_datetime >= now)
    total = db.scalar(select(func.count()).select_from(
        select(Event.id).join(EventRegistration, EventRegistration.event_id == Event.id)
        .where(*conditions).subquery())) or 0
    stmt = (select(Event).join(EventRegistration, EventRegistration.event_id == Event.id)
            .join(Event.company).where(*conditions).options(*_eager())
            .order_by(Event.event_datetime.asc(), Event.id.asc())
            .limit(page_size).offset((page - 1) * page_size))
    return list(db.scalars(stmt).all()), total


# ---------------- response builders ----------------
def to_event_summary(event: Event, counts: Dict[int, int], now: Optional[datetime] = None,
                     student: Optional[Student] = None,
                     registered_ids: Optional[Set[int]] = None) -> EventSummary:
    """`student` is given only when a student is looking, which adds the eligible/registered flags."""
    now = now or datetime.now()
    majors = sorted((m.major for m in event.eligible_majors), key=str.lower)
    return EventSummary(
        id=event.id, name=event.name, event_datetime=event.event_datetime, location=event.location,
        city=event.city, eligible_majors=majors, registration_count=counts.get(event.id, 0),
        is_past=event.event_datetime < now,
        company=CompanyMini(id=event.company.id, name=event.company.name,
                            profile_pic_url=public_url(event.company.profile_pic_path)),
        eligible=is_eligible(majors, student.major) if student is not None else None,
        registered=(event.id in (registered_ids or set())) if student is not None else None,
    )


def to_event_detail(event: Event, db: Session, now: Optional[datetime] = None,
                    student: Optional[Student] = None) -> EventDetail:
    now = now or datetime.now()
    counts = registration_counts(db, [event.id])
    registered = registered_event_ids(db, student.id, [event.id]) if student is not None else None
    summary = to_event_summary(event, counts, now, student, registered)
    fields = summary.model_dump(exclude={"company"})
    detail = EventDetail(company=CompanyPublic.from_company(event.company),
                         description=event.description, **fields)
    if student is not None:
        block = registration_block(event, student, event.id in registered, now)
        detail.can_register = block is None
        detail.register_blocked_reason = block[1] if block else None
    return detail