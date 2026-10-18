"""
The five tools the assistant may use, and the code that runs them.

Each tool has two parts:
  1. a JSON schema (TOOL_SCHEMAS) that is sent to the model, so it knows the tool exists,
     when to use it, and which typed arguments it takes;
  2. a Python function that does the work by calling the SAME service functions the website
     uses (services/jobs.py, services/events.py, services/preferences.py), so the assistant
     and the website can never disagree about what exists.

Rules every tool follows:
  * it always returns a string (the model only reads text);
  * it never raises: any problem becomes a string that starts with "Error:".

execute_tool(name, arguments, ctx) is the single entry point the agent loop calls.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import CITY_SET
from ..models import Event, Job, JobCategory, PayPeriod, SavedItem, SavedItemType, Student
from ..services import events as event_service
from ..services import jobs as job_service
from ..services import preferences as preference_service

MAX_RESULTS = 10   # never hand the model more than this many rows (keeps prompts short)


@dataclass
class ToolContext:
    """Everything a tool needs: the database session and WHO is asking.
    The student always comes from the login token, never from the model."""
    db: Session
    student: Student
    today: date = field(default_factory=date.today)


# ---------------------------------------------------------------------------
# 1. JSON schemas (what the model sees)
# ---------------------------------------------------------------------------
CATEGORIES = [c.value for c in JobCategory]   # full_time, part_time, on_campus, internship

TOOL_SCHEMAS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_student_preferences",
            "description": (
                "Return the logged-in student's saved job and event preferences (preferred categories, "
                "cities, roles, minimum hourly pay, remote, event interests) plus their profile city, "
                "major and skills. Use this FIRST whenever the student says 'my city', 'for me', "
                "'my preferences', 'my major' or otherwise relies on what they saved. Takes no arguments."),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": (
                "Search open job postings. Use whenever the student asks for jobs or internships. "
                "All filters are optional and combine with AND. Returns id, title, company, location, "
                "category, salary and deadline for each match, or a plain message when nothing matches. "
                "Never describe a job that this tool did not return."),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Words that must appear in the job title, e.g. 'data science'"},
                    "company": {"type": "string", "description": "Words that must appear in the company name"},
                    "category": {"type": "string", "enum": CATEGORIES, "description": "Job category"},
                    "city": {"type": "string", "description": f"City name, one of {', '.join(CITY_SET)}"},
                    "remote": {"type": "boolean", "description": "true = only remote jobs, false = only on-site jobs; leave out for both"},
                    "min_hourly_pay": {"type": "number", "description": "Lowest acceptable top pay in US dollars per hour (yearly salaries are converted)"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "Skills; jobs that require ANY of them match, e.g. ['Python', 'SQL']"},
                    "deadline_before": {"type": "string", "description": "Only jobs whose application deadline is on or before this date, YYYY-MM-DD"},
                    "sort": {"type": "string", "enum": ["newest", "deadline", "salary"], "description": "Order of results; 'salary' puts the highest paying first"},
                    "limit": {"type": "integer", "description": f"How many results to return, 1 to {MAX_RESULTS} (default 5)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": (
                "Return the full details of ONE job by its id: description, skills, salary, deadline, "
                "contact, the company's profile, and the company's other recent postings. Use after "
                "search_jobs when the student wants more about a specific job."),
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "integer", "description": "The job id shown by search_jobs"}},
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": (
                "Find UPCOMING career events (fairs, workshops, tech talks, info sessions), earliest first. "
                "Use whenever the student asks about events. Filters are optional and combine with AND. "
                "Use date_from/date_to for phrases like 'next month', and major or eligible_for_me for "
                "eligibility."),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Words that must appear in the event name, e.g. 'career fair'"},
                    "city": {"type": "string", "description": f"City name, one of {', '.join(CITY_SET)}"},
                    "date_from": {"type": "string", "description": "Earliest event date, YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "Latest event date, YYYY-MM-DD"},
                    "major": {"type": "string", "description": "Only events open to this major, e.g. 'Computer Science'"},
                    "eligible_for_me": {"type": "boolean", "description": "true = only events the logged-in student's own major may register for"},
                    "limit": {"type": "integer", "description": f"How many results to return, 1 to {MAX_RESULTS} (default 5)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_job_or_event",
            "description": (
                "Save a job or an event to the student's saved list. This CHANGES data, so only use it "
                "when the student explicitly asks to save something. The student is asked to confirm "
                "before anything is saved."),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "enum": ["job", "event"], "description": "What to save"},
                    "item_id": {"type": "integer", "description": "The id of the job or event"},
                },
                "required": ["item_type", "item_id"],
            },
        },
    },
]

SCHEMAS_BY_NAME = {s["function"]["name"]: s["function"]["parameters"] for s in TOOL_SCHEMAS}
GATED_TOOLS = {"save_job_or_event"}   # state-changing tools that must pass confirm_action()


# ---------------------------------------------------------------------------
# 2. Argument checking: turn what the model sent into clean Python values
# ---------------------------------------------------------------------------
class ArgumentError(ValueError):
    """The model sent arguments that do not fit the tool's schema."""


def _coerce(name: str, value: Any, spec: dict) -> Any:
    """Check one argument against its schema. Small, obvious fixes are allowed
    (the number 12 sent as the text "12"); anything else is an ArgumentError."""
    kind = spec.get("type")
    if kind == "string":
        if not isinstance(value, str):
            raise ArgumentError(f"'{name}' must be text")
        value = value.strip()
        if "enum" in spec and value not in spec["enum"]:
            raise ArgumentError(f"'{name}' must be one of {spec['enum']}, not {value!r}")
        return value
    if kind == "integer":
        if isinstance(value, bool):
            raise ArgumentError(f"'{name}' must be a whole number")
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if not isinstance(value, int):
            raise ArgumentError(f"'{name}' must be a whole number, not {value!r}")
        return value
    if kind == "number":
        if isinstance(value, bool):
            raise ArgumentError(f"'{name}' must be a number")
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ArgumentError(f"'{name}' must be a number, not {value!r}")
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ArgumentError(f"'{name}' must be true or false, not {value!r}")
    if kind == "array":
        if isinstance(value, str):      # a single skill sent as text instead of a list
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ArgumentError(f"'{name}' must be a list of text values")
        return [v.strip() for v in value if v.strip()]
    return value


def check_arguments(tool_name: str, arguments: dict) -> dict:
    """Validate all arguments for one tool. Raises ArgumentError with a precise message."""
    schema = SCHEMAS_BY_NAME[tool_name]
    allowed = schema["properties"]
    if not isinstance(arguments, dict):
        raise ArgumentError("arguments must be a JSON object")
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise ArgumentError(f"unknown argument(s) {unknown}; allowed: {sorted(allowed) or 'none'}")
    clean = {}
    for key, value in arguments.items():
        if value is None or value == "" or value == []:   # "not given"
            continue
        clean[key] = _coerce(key, value, allowed[key])
    missing = [k for k in schema.get("required", []) if k not in clean]
    if missing:
        raise ArgumentError(f"missing required argument(s) {missing}")
    return clean


def _parse_date(name: str, text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ArgumentError(f"'{name}' must be a date written as YYYY-MM-DD, not {text!r}")


def _limit(value: Optional[int]) -> int:
    return max(1, min(value or 5, MAX_RESULTS))


# ---------------------------------------------------------------------------
# 3. The tool functions (each returns a string)
# ---------------------------------------------------------------------------
def get_student_preferences(ctx: ToolContext) -> str:
    s = ctx.student
    skills = ", ".join(sorted((k.skill for k in s.skills), key=str.lower)) or "none listed"
    profile = (f"Profile: city {s.city or 'not set'}, major {s.major or 'not set'}, "
               f"college {s.college}, skills: {skills}.")
    prefs = preference_service.to_preferences_out(
        preference_service.get_student_preferences(ctx.db, s.id))
    if not prefs.saved:
        return f"This student has NOT saved any job or event preferences.\n{profile}"

    def show(values):
        return ", ".join(str(getattr(v, "value", v)) for v in values) or "none"

    return "\n".join([
        "Saved preferences:",
        f"- preferred job categories: {show(prefs.preferred_categories)}",
        f"- preferred cities: {show(prefs.preferred_cities)}",
        f"- preferred roles: {show(prefs.preferred_roles)}",
        f"- minimum pay: {'$' + str(prefs.min_hourly_rate) + '/hr' if prefs.min_hourly_rate else 'none'}",
        f"- remote work: {'allowed but NOT required (do not filter by remote unless the student asks)' if prefs.open_to_remote else 'not wanted'}",
        f"- event interests: {show(prefs.event_interests)}",
        profile,
    ])


# Words that describe the category or location, not the title. "remote data science
# internship" should search titles for "data science", and use filters for the rest.
_NOT_TITLE_WORDS = {"intern", "interns", "internship", "internships", "job", "jobs", "position",
                    "positions", "role", "roles", "remote", "opening", "openings", "opportunity",
                    "opportunities", "full-time", "part-time", "on-campus", "fulltime", "parttime"}


def _job_line(job: Job) -> str:
    where = f"Remote (company in {job.city}, {job.state})" if job.is_remote else f"{job.city}, {job.state}"
    skills = ", ".join(sorted((k.skill for k in job.skills), key=str.lower))
    return (f"- id {job.id} | {job.title} | {job.company.name} | {where} | {job.category.value} | "
            f"{job_service.format_salary(job)} | deadline {job.deadline.isoformat()} | skills: {skills}")


def search_jobs(ctx: ToolContext, title: str = "", company: str = "", category: Optional[str] = None,
                city: Optional[str] = None, remote: Optional[bool] = None,
                min_hourly_pay: Optional[float] = None, skills: Optional[List[str]] = None,
                deadline_before: Optional[str] = None, sort: str = "newest",
                limit: Optional[int] = None) -> str:
    # A city of "remote" really means the remote filter.
    if city and city.strip().lower() == "remote":
        city, remote = None, True
    title_words = [w for w in title.split() if w.lower() not in _NOT_TITLE_WORDS]
    query = " ".join(title_words + company.split())
    jobs, total = job_service.search_jobs(
        ctx.db, q=query or None,
        category=[JobCategory(category)] if category else None,
        city=[city] if city else None,
        is_remote=remote,
        min_salary=int(min_hourly_pay) if min_hourly_pay else None,
        salary_unit=PayPeriod.hourly if min_hourly_pay else None,
        skills=skills or None,
        deadline_before=_parse_date("deadline_before", deadline_before),
        sort=sort, page_size=_limit(limit), today=ctx.today,
    )
    if not jobs:
        return "No jobs match these filters. No such job exists in the database."
    header = f"Found {total} matching open job(s); showing {len(jobs)} (sorted by {sort}):"
    return "\n".join([header] + [_job_line(j) for j in jobs])


def get_job_details(ctx: ToolContext, job_id: int) -> str:
    job = ctx.db.get(Job, job_id)
    if job is None:
        return f"Error: there is no job with id {job_id}."
    c = job.company
    where = "Remote" if job.is_remote else f"{job.city}, {job.state}"
    skills = ", ".join(sorted((k.skill for k in job.skills), key=str.lower))
    status = "CLOSED (deadline passed)" if job.deadline < ctx.today else "open"
    recent = ctx.db.scalars(select(Job).where(Job.company_id == c.id, Job.id != job.id)
                            .order_by(Job.posting_date.desc(), Job.id.desc()).limit(3)).all()
    recent_lines = [f"  - id {r.id} | {r.title} | posted {r.posting_date.isoformat()}" for r in recent] or ["  - none"]
    return "\n".join([
        f"Job id {job.id}: {job.title}",
        f"Company: {c.name} ({c.industry or 'industry not listed'}), based in {c.city}",
        f"Location: {where} | Category: {job.category.value} | Pay: {job_service.format_salary(job)}",
        f"Posted {job.posting_date.isoformat()} ({max((ctx.today - job.posting_date).days, 0)} days ago) | "
        f"Deadline {job.deadline.isoformat()} ({status})",
        f"Skills: {skills}",
        f"Contact: {job.contact_email or c.contact_email or 'not listed'}",
        f"Job description: {job.description}",
        f"About the company: {c.description or 'no description'} Website: {c.website or 'not listed'}",
        "Other recent postings by this company:",
        *recent_lines,
    ])


def _event_line(event: Event, student_major: Optional[str], show_student: bool) -> str:
    majors = sorted((m.major for m in event.eligible_majors), key=str.lower)
    line = (f"- id {event.id} | {event.name} | {event.event_datetime:%Y-%m-%d %H:%M} | "
            f"{event.location}, {event.city} | host: {event.company.name} | open to: {', '.join(majors)}")
    if show_student:   # only when no major was searched for, so it cannot contradict the search
        eligible = event_service.is_eligible(majors, student_major)
        line += f" | the logged-in student ({student_major}) is {'eligible' if eligible else 'NOT eligible'}"
    return line


def search_events(ctx: ToolContext, name: str = "", city: Optional[str] = None,
                  date_from: Optional[str] = None, date_to: Optional[str] = None,
                  major: Optional[str] = None, eligible_for_me: Optional[bool] = None,
                  limit: Optional[int] = None) -> str:
    start, end = _parse_date("date_from", date_from), _parse_date("date_to", date_to)
    if start and end and end < start:
        return "Error: date_to is before date_from."
    if eligible_for_me and not major:
        major = ctx.student.major
    events, total = event_service.search_events(
        ctx.db, q=name or None, city=[city] if city else None, date_from=start, date_to=end,
        major=major, page_size=_limit(limit))
    if not events:
        return "No upcoming events match these filters."
    header = f"Found {total} upcoming event(s); showing {len(events)}, earliest first:"
    return "\n".join([header] + [_event_line(e, ctx.student.major, show_student=not major) for e in events])


def find_save_target(ctx: ToolContext, item_type: str, item_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Before asking the student to confirm, check the save makes sense.
    Returns (label, None) when it does, or (None, error message) when it does not."""
    model = Job if item_type == "job" else Event
    item = ctx.db.get(model, item_id)
    if item is None:
        return None, f"Error: there is no {item_type} with id {item_id}. Nothing was saved."
    already = ctx.db.scalar(select(SavedItem).where(
        SavedItem.student_id == ctx.student.id, SavedItem.item_type == SavedItemType(item_type),
        SavedItem.item_id == item_id))
    label = f"{item_type} {item_id} ({item.title if item_type == 'job' else item.name})"
    if already is not None:
        return None, f"The {label} is already in the student's saved list. Nothing changed."
    return label, None


def save_job_or_event(ctx: ToolContext, item_type: str, item_id: int) -> str:
    """Does the actual save. The agent loop only calls this AFTER confirm_action() said yes."""
    label, problem = find_save_target(ctx, item_type, item_id)
    if problem:
        return problem
    try:
        ctx.db.add(SavedItem(student_id=ctx.student.id, item_type=SavedItemType(item_type), item_id=item_id))
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        return f"The {label} is already in the student's saved list. Nothing changed."
    return f"Saved: the {label} is now in the student's saved list."


TOOL_FUNCTIONS: Dict[str, Callable[..., str]] = {
    "get_student_preferences": get_student_preferences,
    "search_jobs": search_jobs,
    "get_job_details": get_job_details,
    "search_events": search_events,
    "save_job_or_event": save_job_or_event,
}


def execute_tool(name: str, arguments: dict, ctx: ToolContext) -> str:
    """Run one tool and ALWAYS return a string. This is what keeps the loop from crashing."""
    if name not in TOOL_FUNCTIONS:
        return f"Error: unknown tool '{name}'. Available tools: {', '.join(TOOL_FUNCTIONS)}."
    try:
        clean = check_arguments(name, arguments)
        return TOOL_FUNCTIONS[name](ctx, **clean)
    except ArgumentError as exc:
        return f"Error: invalid arguments for {name}: {exc}."
    except Exception as exc:  # a bug or a database problem must not crash the chat
        try:
            ctx.db.rollback()
        except Exception:
            pass
        return f"Error: {name} failed ({type(exc).__name__}). Please try different arguments."
