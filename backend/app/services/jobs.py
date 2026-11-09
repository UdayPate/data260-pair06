"""
Job business logic, kept OUT of the router so two different callers can share it:
    1. the REST endpoint  GET /jobs      (routers/jobs.py)
    2. the AI assistant's search_jobs tool (Part B, written by your partner)

Because both call search_jobs(), the website and the assistant can never disagree
about what "matching jobs" means.

Example for the assistant:
    jobs, total = search_jobs(db, q="data", category=[JobCategory.internship],
                              city=["San Jose"], is_remote=True, skills=["Python"])
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from pymongo.database import Database

from .. import mongo
from ..core.uploads import public_url
from ..documents import HOURS_PER_YEAR
from ..enums import JobCategory, PayPeriod
from ..mongo import Doc, contains, equals_ignoring_case
from ..schemas.jobs import CompanyMini, JobDetail, JobSummary
from ..schemas.profile import CompanyPublic

HOURLY_CAP = 500                 # sanity limits so typos like $50000/hr are rejected
YEARLY_CAP = 1_000_000
MAX_DEADLINE_SPAN_DAYS = 730
SORTS = ("newest", "deadline", "salary")


# ---------------- rules ----------------
def check_job_rules(*, posting_date: date, deadline: date, salary_min: int, salary_max: int,
                    pay_period, creating: bool = False, today: Optional[date] = None) -> None:
    """Rules that involve SEVERAL fields at once. Raises ValueError with a clear message.
    `creating=True` adds checks that only make sense for a brand-new posting."""
    today = today or date.today()
    if salary_min > salary_max:
        raise ValueError("salary_min cannot be greater than salary_max")
    cap = HOURLY_CAP if PayPeriod(pay_period) == PayPeriod.hourly else YEARLY_CAP
    if salary_max > cap:
        raise ValueError(f"salary_max is unrealistically high for {PayPeriod(pay_period).value} pay (limit {cap:,})")
    if deadline < posting_date:
        raise ValueError("deadline cannot be before posting_date")
    if (deadline - posting_date).days > MAX_DEADLINE_SPAN_DAYS:
        raise ValueError("deadline must be within 2 years of posting_date")
    if creating:
        if deadline < today:
            raise ValueError("deadline must be today or later")
        if not today - timedelta(days=365) <= posting_date <= today + timedelta(days=30):
            raise ValueError("posting_date must be within the last year or the next 30 days")


# ---------------- formatting ----------------
def format_salary(job: Doc) -> str:
    unit = "hr" if job.pay_period == PayPeriod.hourly else "yr"
    if job.salary_min is None and job.salary_max is None:
        return "Not listed"
    low, high = job.salary_min if job.salary_min is not None else job.salary_max, \
        job.salary_max if job.salary_max is not None else job.salary_min
    return f"${low:,}/{unit}" if low == high else f"${low:,}–${high:,}/{unit}"


def summary_fields(job: Doc, today: date) -> dict:
    return dict(
        id=job.id, title=job.title, city=job.city, state=job.state, is_remote=job.is_remote,
        category=job.category, salary_min=job.salary_min, salary_max=job.salary_max,
        pay_period=job.pay_period, salary_display=format_salary(job),
        posting_date=job.posting_date, deadline=job.deadline, is_expired=job.deadline < today,
        skills=sorted(job.skills, key=str.lower),
    )


def to_summary(job: Doc, today: Optional[date] = None) -> JobSummary:
    today = today or date.today()
    company = CompanyMini(id=job.company.id, name=job.company.name,
                          profile_pic_url=public_url(job.company.profile_pic_path))
    return JobSummary(company=company, **summary_fields(job, today))


def to_detail(job: Doc, today: Optional[date] = None) -> JobDetail:
    today = today or date.today()
    return JobDetail(
        company=CompanyPublic.from_company(job.company), description=job.description,
        contact_email=job.contact_email,
        posted_days_ago=max((today - job.posting_date).days, 0),
        **summary_fields(job, today),
    )


def with_companies(db: Database, jobs: Sequence[Doc]) -> Sequence[Doc]:
    """Store each job's company document as job.company (one query for the whole list)."""
    return mongo.attach(db, jobs, "company_id", "companies", "company")


def applicant_counts(db: Database, job_ids: Sequence[int]) -> Dict[int, int]:
    """{job_id: number of applications} for the given jobs (jobs with none are absent)."""
    if not job_ids:
        return {}
    rows = db.applications.aggregate([
        {"$match": {"job_id": {"$in": list(job_ids)}}},
        {"$group": {"_id": "$job_id", "n": {"$sum": 1}}},
    ])
    return {row["_id"]: row["n"] for row in rows}


# ---------------- search ----------------
def search_jobs(
    db: Database, *,
    q: Optional[str] = None,
    category: Optional[Sequence[JobCategory]] = None,
    city: Optional[Sequence[str]] = None,
    is_remote: Optional[bool] = None,
    min_salary: Optional[int] = None,
    salary_unit: Optional[PayPeriod] = None,
    skills: Optional[Sequence[str]] = None,
    skills_match: str = "any",
    deadline_before: Optional[date] = None,
    deadline_after: Optional[date] = None,
    include_expired: bool = False,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 20,
    today: Optional[date] = None,
) -> Tuple[List[Doc], int]:
    """Filter jobs. Returns (jobs for this page, total number of matches). Each job has job.company.

    Every filter is optional and filters combine with AND.
    q               words that must each appear in the job title OR the company name
    category        any of these categories (OR)
    city            any of these cities, case-insensitive (OR)
    min_salary      the job's top pay must be at least this, measured in `salary_unit`
    skills          jobs requiring any (default) or all of these skills, case-insensitive
    include_expired False hides jobs whose deadline has passed
    """
    today = today or date.today()
    conditions: List[dict] = []

    for word in (q or "").split()[:8]:
        # the company name lives in another collection: first find the companies whose name has the word
        company_ids = [c["_id"] for c in db.companies.find({"name": contains(word)}, {"_id": 1})]
        conditions.append({"$or": [{"title": contains(word)}, {"company_id": {"$in": company_ids}}]})
    if category:
        conditions.append({"category": {"$in": [JobCategory(c).value for c in category]}})
    cities = [c.strip() for c in (city or []) if c and c.strip()]
    if cities:
        conditions.append({"$or": [{"city": equals_ignoring_case(c)} for c in cities]})
    if is_remote is not None:
        conditions.append({"is_remote": is_remote})
    if min_salary is not None:
        if salary_unit is None:
            raise ValueError("salary_unit (hourly or yearly) is required when min_salary is used")
        # every job stores its top pay as a yearly number (salary_yearly_max), so compare in yearly terms
        yearly_needed = min_salary * HOURS_PER_YEAR if PayPeriod(salary_unit) == PayPeriod.hourly else min_salary
        conditions.append({"salary_yearly_max": {"$gte": yearly_needed}})

    wanted = sorted({s.strip().lower() for s in (skills or []) if s and s.strip()})
    if wanted:
        conditions.append({"skills_lower": {"$all" if skills_match == "all" else "$in": wanted}})

    if deadline_before is not None:
        conditions.append({"deadline": {"$lte": deadline_before}})
    if deadline_after is not None:
        conditions.append({"deadline": {"$gte": deadline_after}})
    if not include_expired:
        conditions.append({"deadline": {"$gte": today}})

    order = {
        "newest": [("posting_date", -1), ("_id", -1)],
        "deadline": [("deadline", 1), ("_id", 1)],
        "salary": [("salary_yearly_max", -1), ("_id", 1)],
    }[sort]
    jobs, total = mongo.page(db, "jobs", {"$and": conditions} if conditions else {}, order, page, page_size)
    return list(with_companies(db, jobs)), total


def total_pages(total: int, page_size: int) -> int:
    return max((total + page_size - 1) // page_size, 1)