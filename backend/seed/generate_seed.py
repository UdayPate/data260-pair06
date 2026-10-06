"""
Seed generator for DATA-260 Lab 1 (Pair 06).

Run from the backend/ folder:
    python -m seed.generate_seed --reset

Every random choice goes through rng = random.Random(SEED) or a Faker seeded with SEED,
so running it twice produces identical data (random_state = SEED = 6).

Demo logins (password for ALL seeded accounts: Password123!)
    student: demo.student@sjsu.edu
    company: demo.company@example.com
"""
import argparse
import os
import random
from datetime import datetime, time, timedelta

import bcrypt
from faker import Faker
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from app import models as m
from app.config import ANCHOR_DATE, CITY_SET, DATABASE_URL, SEED, STATE, UPLOAD_DIR
from app.database import Base, SessionLocal, engine
from app.skills import (ALL_SKILLS, CAMPUS_SKILLS, CAMPUS_TITLES, COLLEGES, DEGREES,
                        JOB_FIELDS, MAJORS)

# ---- Required minimum counts from the handout ----
N_COMPANIES = 50
N_STUDENTS = 200
N_JOBS = 300
N_APPLICATIONS = 1500
N_EVENTS = 100
# Extra rows so features have something to show
N_REGISTRATIONS = 400
N_SAVED_ITEMS = 150

DEMO_PASSWORD = "Password123!"
CAMPUS_EMPLOYERS = ["San Jose State University", "Santa Clara University", "De Anza College"]
INDUSTRIES = ["Information Technology", "Financial Services", "Healthcare Technology",
              "Retail", "Semiconductors", "Consulting", "Media", "Non-Profit"]
EVENT_TEMPLATES = ["{topic} Career Fair", "Resume Workshop", "Tech Talk: {topic}",
                   "Networking Night", "Info Session: {company}", "Mock Interview Day",
                   "{topic} Hackathon", "Alumni Panel: Careers in {topic}"]
EVENT_TOPICS = ["Data Science", "Software Engineering", "AI", "Product Management",
                "Cloud Computing", "Marketing", "Cybersecurity"]

rng = random.Random(SEED)
fake = Faker("en_US")
fake.seed_instance(SEED)


# ---------------- helpers ----------------
def ensure_database():
    """For MySQL, create the p06_handshake database if it doesn't exist yet."""
    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("mysql"):
        return
    server = create_engine(url._replace(database=None))
    with server.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    server.dispose()


def write_placeholder_pdf(path):
    """Write a tiny valid one-page PDF so seeded applications have a resume to preview."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = b"BT /F1 18 Tf 72 720 Td (Seed placeholder resume - Pair 06) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    with open(path, "wb") as f:
        f.write(bytes(out))


def rand_date_between(start, end):
    days = (end - start).days
    return start + timedelta(days=rng.randint(0, max(days, 0)))


def salary_for(category):
    """Returns (min, max, pay_period). Internship/part-time/on-campus are hourly."""
    if category == m.JobCategory.full_time:
        low = rng.randrange(70_000, 160_001, 5_000)
        return low, low + rng.randrange(10_000, 40_001, 5_000), m.PayPeriod.yearly
    ranges = {m.JobCategory.internship: (20, 55),
              m.JobCategory.part_time: (17, 35),
              m.JobCategory.on_campus: (17, 25)}
    lo, hi = ranges[category]
    low = rng.randint(lo, hi)
    return low, low + rng.randint(0, 10), m.PayPeriod.hourly


# ---------------- generators ----------------
def make_companies(pw_hash):
    companies = []
    for i in range(N_COMPANIES):
        city = CITY_SET[i % len(CITY_SET)]
        if i == 0:
            name, email = "Demo Analytics Co", "demo.company@example.com"
        elif i <= len(CAMPUS_EMPLOYERS):
            name = CAMPUS_EMPLOYERS[i - 1]
            email = f"careers{i}@campus.example.edu"
        else:
            name = fake.company()
            email = f"recruiting{i}@{name.split()[0].lower().strip(',')}.example.com"
        is_campus = name in CAMPUS_EMPLOYERS
        companies.append(m.Company(
            name=name, email=email, password_hash=pw_hash, city=city, state=STATE,
            industry="Higher Education" if is_campus else rng.choice(INDUSTRIES),
            description=fake.paragraph(nb_sentences=4),
            contact_email=email, contact_phone=fake.numerify("(408) ###-####"),
            website=f"https://www.{name.split()[0].lower().strip(',')}.example.com",
        ))
    return companies


def make_students(pw_hash):
    students = []
    for i in range(N_STUDENTS):
        first, last = fake.first_name(), fake.last_name()
        if i == 0:
            name, email = "Demo Student", "demo.student@sjsu.edu"
            college, major, city = "San Jose State University", "Data Science", "San Jose"
        else:
            name = f"{first} {last}"
            email = f"{first.lower()}.{last.lower()}{i}@student.example.edu"
            college = rng.choices(COLLEGES, weights=[50, 10, 10, 10, 10, 10])[0]
            major, city = rng.choice(MAJORS), rng.choice(CITY_SET)
        s = m.Student(
            name=name, email=email, password_hash=pw_hash, college=college,
            date_of_birth=fake.date_of_birth(minimum_age=19, maximum_age=30),
            city=city, state=STATE, country="United States",
            career_objective=f"Seeking opportunities in {major.lower()} to grow my skills.",
            degree=rng.choice(DEGREES), major=major,
            graduation_year=rng.choice([2026, 2027, 2028]),
            cgpa=round(rng.uniform(2.5, 4.0), 2),
            phone=fake.numerify("(408) ###-####"),
        )
        skills = ["Python", "SQL", "Machine Learning", "Pandas"] if i == 0 else rng.sample(ALL_SKILLS, rng.randint(3, 6))
        s.skills = [m.StudentSkill(skill=sk) for sk in skills]
        for _ in range(rng.randint(0, 2)):
            start = rand_date_between(ANCHOR_DATE - timedelta(days=1200), ANCHOR_DATE - timedelta(days=200))
            s.experiences.append(m.StudentExperience(
                title=rng.choice(["Intern", "Teaching Assistant", "Research Assistant", "Sales Associate"]),
                company=fake.company(), start_date=start,
                end_date=start + timedelta(days=rng.randint(60, 365)),
                description=fake.sentence(nb_words=12)))
        # ~80% of students have saved preferences; the rest test the "no preferences" case.
        if i == 0:
            s.preferences = m.StudentPreference(
                preferred_categories=["internship"], preferred_cities=["San Jose"],
                preferred_roles=["Data Analyst", "Data Science"], min_hourly_rate=25,
                open_to_remote=True, event_interests=["Career Fair", "Tech Talk"])
        elif rng.random() < 0.8:
            s.preferences = m.StudentPreference(
                preferred_categories=rng.sample([c.value for c in m.JobCategory], rng.randint(1, 2)),
                preferred_cities=rng.sample(CITY_SET, rng.randint(1, 2)),
                preferred_roles=rng.sample(JOB_FIELDS[rng.choice(list(JOB_FIELDS))]["titles"], 2),
                min_hourly_rate=rng.choice([None, 20, 25, 30]),
                open_to_remote=rng.random() < 0.6,
                event_interests=rng.sample(["Career Fair", "Workshop", "Tech Talk", "Networking", "Hackathon"], 2))
        students.append(s)
    return students


def make_jobs(companies):
    campus = [c for c in companies if c.name in CAMPUS_EMPLOYERS]
    others = [c for c in companies if c.name not in CAMPUS_EMPLOYERS]
    cats = [m.JobCategory.internship, m.JobCategory.full_time, m.JobCategory.part_time, m.JobCategory.on_campus]
    # The first few jobs are fixed "scenarios" so Part B's required tests always have
    # matching data (remote data science internships, internships in each city).
    scenarios = [("Data Science", True, None)] * 3 + [("Data Analyst", False, c) for c in CITY_SET]
    jobs = []
    for i in range(N_JOBS):
        category = rng.choices(cats, weights=[40, 25, 20, 15])[0]
        city_fixed = None
        if i < len(scenarios):
            base, is_remote, city_fixed = scenarios[i]
            category, company = m.JobCategory.internship, rng.choice(others)
            title = f"{base} Intern"
            skill_pool = ["Python", "Machine Learning", "Data Analysis", "SQL", "Statistics", "Pandas"]
        elif category == m.JobCategory.on_campus:
            company = rng.choice(campus)
            title, skill_pool, is_remote = rng.choice(CAMPUS_TITLES), CAMPUS_SKILLS, False
        else:
            company = rng.choice(others)
            field = JOB_FIELDS[rng.choice(list(JOB_FIELDS))]
            base = rng.choice(field["titles"])
            title = f"{base} Intern" if category == m.JobCategory.internship else base
            skill_pool, is_remote = field["skills"], rng.random() < 0.15
        skills = rng.sample(skill_pool, rng.randint(2, min(5, len(skill_pool))))
        lo, hi, period = salary_for(category)
        posted = ANCHOR_DATE - timedelta(days=rng.randint(1, 60))
        city = city_fixed or rng.choice(CITY_SET)
        where = "Remote" if is_remote else f"{city}, {STATE}"
        job = m.Job(
            company=company, title=title, category=category, city=city, state=STATE,
            is_remote=is_remote, salary_min=lo, salary_max=hi, pay_period=period,
            posting_date=posted, deadline=posted + timedelta(days=rng.randint(20, 90)),
            contact_email=company.contact_email,
            description=(f"{company.name} is hiring a {title} ({where}). "
                         f"Ideal candidates have experience with {', '.join(skills)}. "
                         + fake.paragraph(nb_sentences=3)),
        )
        job.skills = [m.JobSkill(skill=sk) for sk in skills]
        jobs.append(job)
    return jobs


def make_applications(students, jobs, resume_path):
    pairs, apps = set(), []
    statuses = [m.ApplicationStatus.pending, m.ApplicationStatus.reviewed, m.ApplicationStatus.declined]
    while len(apps) < N_APPLICATIONS:
        s, j = rng.choice(students), rng.choice(jobs)
        if (s.id, j.id) in pairs:
            continue
        pairs.add((s.id, j.id))
        last_day = min(j.deadline, ANCHOR_DATE)
        day = rand_date_between(j.posting_date, last_day)
        apps.append(m.Application(
            student_id=s.id, job_id=j.id, resume_path=resume_path,
            status=rng.choices(statuses, weights=[50, 30, 20])[0],
            applied_at=datetime.combine(day, time(rng.randint(8, 22), rng.randint(0, 59)))))
    return apps


def make_events(companies):
    events = []
    for _ in range(N_EVENTS):
        company = rng.choice(companies)
        topic = rng.choice(EVENT_TOPICS)
        name = rng.choice(EVENT_TEMPLATES).format(topic=topic, company=company.name)
        day = ANCHOR_DATE + timedelta(days=rng.randint(-10, 90))  # mostly upcoming
        city = rng.choice(CITY_SET)
        ev = m.Event(
            company=company, name=name, city=city,
            event_datetime=datetime.combine(day, time(rng.randint(9, 18), rng.choice([0, 30]))),
            location=f"{fake.street_address()}, {city}, {STATE}",
            description=f"Join {company.name} for {name}. " + fake.paragraph(nb_sentences=2),
        )
        majors = ["All"] if rng.random() < 0.4 else rng.sample(MAJORS, rng.randint(1, 3))
        ev.eligible_majors = [m.EventEligibleMajor(major=mj) for mj in majors]
        events.append(ev)
    return events


def make_registrations(students, events):
    pairs, regs, attempts = set(), [], 0
    while len(regs) < N_REGISTRATIONS and attempts < 20_000:
        attempts += 1
        s, e = rng.choice(students), rng.choice(events)
        majors = {em.major for em in e.eligible_majors}
        if (s.id, e.id) in pairs or ("All" not in majors and s.major not in majors):
            continue  # skip duplicates and ineligible students
        pairs.add((s.id, e.id))
        regs.append(m.EventRegistration(
            student_id=s.id, event_id=e.id,
            registered_at=e.event_datetime - timedelta(days=rng.randint(1, 20))))
    return regs


def make_saved_items(students, jobs, events):
    seen, items = set(), []
    while len(items) < N_SAVED_ITEMS:
        s = rng.choice(students)
        if rng.random() < 0.7:
            key = (s.id, m.SavedItemType.job, rng.choice(jobs).id)
        else:
            key = (s.id, m.SavedItemType.event, rng.choice(events).id)
        if key in seen:
            continue
        seen.add(key)
        items.append(m.SavedItem(student_id=key[0], item_type=key[1], item_id=key[2]))
    return items


# ---------------- main ----------------
def main():
    parser = argparse.ArgumentParser(description="Seed the Pair 06 Handshake database")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()

    ensure_database()
    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        if db.scalar(select(func.count(m.Student.id))):
            print("Database already has data. Re-run with --reset to start fresh.")
            return

        # bcrypt is slow on purpose, so hash the shared demo password once.
        pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
        resume_rel = "resumes/seed_resume.pdf"
        write_placeholder_pdf(os.path.join(UPLOAD_DIR, resume_rel))

        companies = make_companies(pw_hash)
        students = make_students(pw_hash)
        db.add_all(companies + students)
        db.flush()  # assigns ids

        jobs = make_jobs(companies)
        events = make_events(companies)
        db.add_all(jobs + events)
        db.flush()

        db.add_all(make_applications(students, jobs, resume_rel))
        db.add_all(make_registrations(students, events))
        db.add_all(make_saved_items(students, jobs, events))
        db.commit()

        print(f"Seeded database with SEED={SEED}, CITY_SET={CITY_SET}")
        for label, model in [("companies", m.Company), ("students", m.Student), ("jobs", m.Job),
                             ("applications", m.Application), ("events", m.Event),
                             ("event_registrations", m.EventRegistration),
                             ("student_preferences", m.StudentPreference),
                             ("saved_items", m.SavedItem)]:
            print(f"  {label:<20} {db.scalar(select(func.count(model.id)))}")


if __name__ == "__main__":
    main()