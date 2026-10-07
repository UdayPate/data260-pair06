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

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from ..core.uploads import public_url
from ..models import Application, Company, Job, JobCategory, JobSkill, PayPeriod
from ..schemas.jobs import CompanyMini, JobDetail, JobSummary
from ..schemas.profile import CompanyPublic

HOURS_PER_YEAR = 2080            # 40 hours x 52 weeks, used to compare hourly and yearly pay
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
def format_salary(job: Job) -> str:
    unit = "hr" if job.pay_period == PayPeriod.hourly else "yr"
    if job.salary_min is None and job.salary_max is None:
        return "Not listed"
    low, high = job.salary_min if job.salary_min is not None else job.salary_max, \
        job.salary_max if job.salary_max is not None else job.salary_min
    return f"${low:,}/{unit}" if low == high else f"${low:,}–${high:,}/{unit}"


def summary_fields(job: Job, today: date) -> dict:
    return dict(
        id=job.id, title=job.title, city=job.city, state=job.state, is_remote=job.is_remote,
        category=job.category, salary_min=job.salary_min, salary_max=job.salary_max,
        pay_period=job.pay_period, salary_display=format_salary(job),
        posting_date=job.posting_date, deadline=job.deadline, is_expired=job.deadline < today,
        skills=sorted((s.skill for s in job.skills), key=str.lower),
    )


def to_summary(job: Job, today: Optional[date] = None) -> JobSummary:
    today = today or date.today()
    company = CompanyMini(id=job.company.id, name=job.company.name,
                          profile_pic_url=public_url(job.company.profile_pic_path))
    return JobSummary(company=company, **summary_fields(job, today))


def to_detail(job: Job, today: Optional[date] = None) -> JobDetail:
    today = today or date.today()
    return JobDetail(
        company=CompanyPublic.from_company(job.company), description=job.description,
        contact_email=job.contact_email,
        posted_days_ago=max((today - job.posting_date).days, 0),
        **summary_fields(job, today),
    )


def applicant_counts(db: Session, job_ids: Sequence[int]) -> Dict[int, int]:
    """{job_id: number of applications} for the given jobs (jobs with none are absent)."""
    if not job_ids:
        return {}
    rows = db.execute(select(Application.job_id, func.count(Application.id))
                      .where(Application.job_id.in_(job_ids)).group_by(Application.job_id)).all()
    return {job_id: count for job_id, count in rows}


# ---------------- search ----------------
def _yearly_max():
    """The job's top pay converted to a yearly figure (so hourly and yearly jobs compare)."""
    return case((Job.pay_period == PayPeriod.hourly, Job.salary_max * HOURS_PER_YEAR), else_=Job.salary_max)


def _hourly_max():
    return case((Job.pay_period == PayPeriod.hourly, Job.salary_max),
                else_=Job.salary_max / float(HOURS_PER_YEAR))


def search_jobs(
    db: Session, *,
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
) -> Tuple[List[Job], int]:
    """Filter jobs. Returns (jobs for this page, total number of matches).

    Every filter is optional and filters combine with AND.
    q               words that must each appear in the job title OR the company name
    category        any of these categories (OR)
    city            any of these cities, case-insensitive (OR)
    min_salary      the job's top pay must be at least this, measured in `salary_unit`
    skills          jobs requiring any (default) or all of these skills, case-insensitive
    include_expired False hides jobs whose deadline has passed
    """
    today = today or date.today()
    conditions = []

    for word in (q or "").split()[:8]:
        conditions.append(or_(Job.title.icontains(word, autoescape=True),     # autoescape: a typed "%"
                              Company.name.icontains(word, autoescape=True)))  # is literal, not a wildcard
    if category:
        conditions.append(Job.category.in_(list(category)))
    cities = [c.strip().lower() for c in (city or []) if c and c.strip()]
    if cities:
        conditions.append(func.lower(Job.city).in_(cities))
    if is_remote is not None:
        conditions.append(Job.is_remote == is_remote)
    if min_salary is not None:
        if salary_unit is None:
            raise ValueError("salary_unit (hourly or yearly) is required when min_salary is used")
        top_pay = _hourly_max() if PayPeriod(salary_unit) == PayPeriod.hourly else _yearly_max()
        conditions.append(top_pay >= min_salary)

    wanted = sorted({s.strip().lower() for s in (skills or []) if s and s.strip()})
    if wanted:
        matching = select(JobSkill.job_id).where(func.lower(JobSkill.skill).in_(wanted))
        if skills_match == "all":
            matching = matching.group_by(JobSkill.job_id).having(
                func.count(func.distinct(func.lower(JobSkill.skill))) == len(wanted))
        conditions.append(Job.id.in_(matching))

    if deadline_before is not None:
        conditions.append(Job.deadline <= deadline_before)
    if deadline_after is not None:
        conditions.append(Job.deadline >= deadline_after)
    if not include_expired:
        conditions.append(Job.deadline >= today)

    base = select(Job.id).join(Job.company).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    order = {
        "newest": (Job.posting_date.desc(), Job.id.desc()),
        "deadline": (Job.deadline.asc(), Job.id.asc()),
        "salary": (_yearly_max().desc(), Job.id.asc()),
    }[sort]
    stmt = (select(Job).join(Job.company).where(*conditions)
            .options(contains_eager(Job.company), selectinload(Job.skills))
            .order_by(*order).limit(page_size).offset((page - 1) * page_size))
    return list(db.scalars(stmt).all()), total


def total_pages(total: int, page_size: int) -> int:
    return max((total + page_size - 1) // page_size, 1)