"""
Seed generator for DATA-260 Labs 1 and 2 (Pair 06). Lab 2: it fills MongoDB (database p06_handshake).

Run from the backend/ folder (MONGO_URL says which MongoDB; the default is mongodb://localhost:27017):
    python -m seed.generate_seed --reset

Every random choice goes through rng = random.Random(SEED) or a Faker seeded with SEED,
so running it twice produces identical data (random_state = SEED = 6).

Demo logins (password for ALL seeded accounts: Password123!)
    student: demo.student@sjsu.edu
    company: demo.company@example.com
"""
import argparse
import random
from datetime import datetime, time, timedelta

import bcrypt
from faker import Faker

from app import documents, mongo
from app.config import ANCHOR_DATE, CITY_SET, MONGO_DB_NAME, SEED, STATE
from app.enums import ApplicationStatus, JobCategory, PayPeriod, SavedItemType
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
def placeholder_pdf() -> bytes:
    """A tiny valid one-page PDF, so seeded applications have a resume to preview."""
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
    return bytes(out)


def rand_date_between(start, end):
    days = (end - start).days
    return start + timedelta(days=rng.randint(0, max(days, 0)))


def salary_for(category):
    """Returns (min, max, pay_period). Internship/part-time/on-campus are hourly."""
    if category == JobCategory.full_time:
        low = rng.randrange(70_000, 160_001, 5_000)
        return low, low + rng.randrange(10_000, 40_001, 5_000), PayPeriod.yearly
    ranges = {JobCategory.internship: (20, 55),
              JobCategory.part_time: (17, 35),
              JobCategory.on_campus: (17, 25)}
    lo, hi = ranges[category]
    low = rng.randint(lo, hi)
    return low, low + rng.randint(0, 10), PayPeriod.hourly


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
        company = documents.company(
            name=name, email=email, password_hash=pw_hash, city=city, state=STATE,
            industry="Higher Education" if is_campus else rng.choice(INDUSTRIES),
            description=fake.paragraph(nb_sentences=4),
            contact_email=email, contact_phone=fake.numerify("(408) ###-####"),
            website=f"https://www.{name.split()[0].lower().strip(',')}.example.com",
        )
        company["_id"] = i + 1          # ids count up from 1 in creation order, like the MySQL auto-increment did
        companies.append(company)
    return companies


def make_students(pw_hash):
    """Returns (students, preferences). Skills and experience are stored inside the student document."""
    students, preferences, experience_id = [], [], 0
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
        fields = dict(
            name=name, email=email, password_hash=pw_hash, college=college,
            date_of_birth=fake.date_of_birth(minimum_age=19, maximum_age=30),
            city=city, state=STATE, country="United States",
            career_objective=f"Seeking opportunities in {major.lower()} to grow my skills.",
            degree=rng.choice(DEGREES), major=major,
            graduation_year=rng.choice([2026, 2027, 2028]),
            cgpa=round(rng.uniform(2.5, 4.0), 2),
            phone=fake.numerify("(408) ###-####"),
        )
        fields["skills"] = ["Python", "SQL", "Machine Learning", "Pandas"] if i == 0 else rng.sample(ALL_SKILLS, rng.randint(3, 6))
        experiences = []
        for _ in range(rng.randint(0, 2)):
            start = rand_date_between(ANCHOR_DATE - timedelta(days=1200), ANCHOR_DATE - timedelta(days=200))
            experience_id += 1
            experiences.append(dict(
                id=experience_id,
                title=rng.choice(["Intern", "Teaching Assistant", "Research Assistant", "Sales Associate"]),
                company=fake.company(), start_date=start,
                end_date=start + timedelta(days=rng.randint(60, 365)),
                description=fake.sentence(nb_words=12)))
        fields["experiences"] = experiences
        student = documents.student(**fields)
        student["_id"] = i + 1
        students.append(student)
        # ~80% of students have saved preferences; the rest test the "no preferences" case.
        if i == 0:
            prefs = dict(
                preferred_categories=["internship"], preferred_cities=["San Jose"],
                preferred_roles=["Data Analyst", "Data Science"], min_hourly_rate=25,
                open_to_remote=True, event_interests=["Career Fair", "Tech Talk"])
        elif rng.random() < 0.8:
            prefs = dict(
                preferred_categories=rng.sample([c.value for c in JobCategory], rng.randint(1, 2)),
                preferred_cities=rng.sample(CITY_SET, rng.randint(1, 2)),
                preferred_roles=rng.sample(JOB_FIELDS[rng.choice(list(JOB_FIELDS))]["titles"], 2),
                min_hourly_rate=rng.choice([None, 20, 25, 30]),
                open_to_remote=rng.random() < 0.6,
                event_interests=rng.sample(["Career Fair", "Workshop", "Tech Talk", "Networking", "Hackathon"], 2))
        else:
            continue
        pref = documents.preferences(student_id=student["_id"], **prefs)
        pref["_id"] = len(preferences) + 1
        preferences.append(pref)
    return students, preferences


def make_jobs(companies):
    campus = [c for c in companies if c["name"] in CAMPUS_EMPLOYERS]
    others = [c for c in companies if c["name"] not in CAMPUS_EMPLOYERS]
    cats = [JobCategory.internship, JobCategory.full_time, JobCategory.part_time, JobCategory.on_campus]
    # The first few jobs are fixed "scenarios" so Part B's required tests always have
    # matching data (remote data science internships, internships in each city).
    # (title, remote?, fixed city, skills the job must list)
    ds_skills, da_skills = ["Python", "Machine Learning"], ["SQL", "Python"]
    scenarios = [("Data Science", True, None, ds_skills)] * 3 + [("Data Analyst", False, c, da_skills) for c in CITY_SET]
    jobs = []
    for i in range(N_JOBS):
        category = rng.choices(cats, weights=[40, 25, 20, 15])[0]
        city_fixed = None
        if i < len(scenarios):
            base, is_remote, city_fixed, _ = scenarios[i]
            category, company = JobCategory.internship, rng.choice(others)
            title = f"{base} Intern"
            skill_pool = ["Python", "Machine Learning", "Data Analysis", "SQL", "Statistics", "Pandas"]
        elif category == JobCategory.on_campus:
            company = rng.choice(campus)
            title, skill_pool, is_remote = rng.choice(CAMPUS_TITLES), CAMPUS_SKILLS, False
        else:
            company = rng.choice(others)
            field = JOB_FIELDS[rng.choice(list(JOB_FIELDS))]
            base = rng.choice(field["titles"])
            title = f"{base} Intern" if category == JobCategory.internship else base
            skill_pool, is_remote = field["skills"], rng.random() < 0.15
        skills = rng.sample(skill_pool, rng.randint(2, min(5, len(skill_pool))))
        if i < len(scenarios):  # planted jobs always list the skills the Part B tests search for
            skills = list(dict.fromkeys(scenarios[i][3] + skills))[:5]
        lo, hi, period = salary_for(category)
        posted = ANCHOR_DATE - timedelta(days=rng.randint(1, 60))
        city = city_fixed or rng.choice(CITY_SET)
        where = "Remote" if is_remote else f"{city}, {STATE}"
        span = rng.randint(20, 90)   # (same random draw as before, so the rest of the data is unchanged)
        # Planted scenario jobs stay open until at least January so the Part B tests keep
        # working on grading day. All other jobs close 20-90 days after they were posted.
        deadline = ANCHOR_DATE + timedelta(days=90 + span) if i < len(scenarios) else posted + timedelta(days=span)
        job = documents.job(
            company_id=company["_id"], title=title, category=category, city=city, state=STATE,
            is_remote=is_remote, salary_min=lo, salary_max=hi, pay_period=period,
            posting_date=posted, deadline=deadline,
            contact_email=company["contact_email"],
            description=(f"{company['name']} is hiring a {title} ({where}). "
                         f"Ideal candidates have experience with {', '.join(skills)}. "
                         + fake.paragraph(nb_sentences=3)),
            skills=skills,
        )
        job["_id"] = i + 1
        jobs.append(job)
    return jobs


def make_applications(students, jobs, resume_file_id):
    pairs, apps = set(), []
    statuses = [ApplicationStatus.pending, ApplicationStatus.reviewed, ApplicationStatus.declined]
    while len(apps) < N_APPLICATIONS:
        s, j = rng.choice(students), rng.choice(jobs)
        if (s["_id"], j["_id"]) in pairs:
            continue
        pairs.add((s["_id"], j["_id"]))
        last_day = min(j["deadline"], ANCHOR_DATE)
        day = rand_date_between(j["posting_date"], last_day)
        app = documents.application(
            student_id=s["_id"], job_id=j["_id"], resume_file_id=resume_file_id,   # every seeded resume is the same placeholder PDF
            status=rng.choices(statuses, weights=[50, 30, 20])[0],
            applied_at=datetime.combine(day, time(rng.randint(8, 22), rng.randint(0, 59))))
        app["_id"] = len(apps) + 1
        apps.append(app)
    return apps


def make_events(companies):
    events = []
    for _ in range(N_EVENTS):
        company = rng.choice(companies)
        topic = rng.choice(EVENT_TOPICS)
        name = rng.choice(EVENT_TEMPLATES).format(topic=topic, company=company["name"])
        day = ANCHOR_DATE + timedelta(days=rng.randint(-10, 90))  # mostly upcoming
        city = rng.choice(CITY_SET)
        fields = dict(
            company_id=company["_id"], name=name, city=city,
            event_datetime=datetime.combine(day, time(rng.randint(9, 18), rng.choice([0, 30]))),
            location=f"{fake.street_address()}, {city}, {STATE}",
            description=f"Join {company['name']} for {name}. " + fake.paragraph(nb_sentences=2),
        )
        majors = ["All"] if rng.random() < 0.4 else rng.sample(MAJORS, rng.randint(1, 3))
        ev = documents.event(eligible_majors=majors, **fields)
        ev["_id"] = len(events) + 1
        events.append(ev)
    return events


def make_registrations(students, events):
    pairs, regs, attempts = set(), [], 0
    while len(regs) < N_REGISTRATIONS and attempts < 20_000:
        attempts += 1
        s, e = rng.choice(students), rng.choice(events)
        majors = set(e["eligible_majors"])
        if (s["_id"], e["_id"]) in pairs or ("All" not in majors and s["major"] not in majors):
            continue  # skip duplicates and ineligible students
        pairs.add((s["_id"], e["_id"]))
        reg = documents.registration(
            student_id=s["_id"], event_id=e["_id"],
            registered_at=e["event_datetime"] - timedelta(days=rng.randint(1, 20)))
        reg["_id"] = len(regs) + 1
        regs.append(reg)
    return regs


def make_saved_items(students, jobs, events):
    seen, items = set(), []
    while len(items) < N_SAVED_ITEMS:
        s = rng.choice(students)
        if rng.random() < 0.7:
            key = (s["_id"], SavedItemType.job, rng.choice(jobs)["_id"])
        else:
            key = (s["_id"], SavedItemType.event, rng.choice(events)["_id"])
        if key in seen:
            continue
        seen.add(key)
        item = documents.saved_item(student_id=key[0], item_type=key[1], item_id=key[2])
        item["_id"] = len(items) + 1
        items.append(item)
    return items


# ---------------- main ----------------
def store(db, collection, docs):
    """Insert the documents (they already have their integer _id) and set the id counter so that
    documents created later through the API continue after the last seeded id."""
    if docs:
        db[collection].insert_many([mongo.dump(d) for d in docs])
        db.counters.replace_one({"_id": collection}, {"_id": collection, "seq": len(docs)}, upsert=True)


def main():
    parser = argparse.ArgumentParser(description="Seed the Pair 06 Handshake database (MongoDB)")
    parser.add_argument("--reset", action="store_true", help="empty every collection first")
    args = parser.parse_args()

    db = mongo.get_database()
    if args.reset:
        for name in db.list_collection_names():      # includes the GridFS collections (resumes.files, ...)
            db[name].drop()
    mongo.ensure_indexes(db)

    if db.students.count_documents({}):
        print("Database already has data. Re-run with --reset to start fresh.")
        return

    # bcrypt is slow on purpose, so hash the shared demo password once.
    pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    # One placeholder PDF in GridFS; every seeded application points at it.
    resume_id = mongo.bucket(db, "resumes").put(placeholder_pdf(), filename="seed_resume.pdf",
                                                content_type="application/pdf")

    companies = make_companies(pw_hash)
    students, preferences = make_students(pw_hash)
    jobs = make_jobs(companies)
    events = make_events(companies)
    store(db, "companies", companies)
    store(db, "students", students)
    store(db, "student_preferences", preferences)
    store(db, "jobs", jobs)
    store(db, "events", events)
    store(db, "applications", make_applications(students, jobs, resume_id))
    store(db, "event_registrations", make_registrations(students, events))
    store(db, "saved_items", make_saved_items(students, jobs, events))
    db.counters.replace_one({"_id": "student_experience"},
                            {"_id": "student_experience",
                             "seq": sum(len(s["experiences"]) for s in students)}, upsert=True)

    print(f"Seeded database {MONGO_DB_NAME} with SEED={SEED}, CITY_SET={CITY_SET}")
    for label, collection in [("companies", "companies"), ("students", "students"), ("jobs", "jobs"),
                              ("applications", "applications"), ("events", "events"),
                              ("event_registrations", "event_registrations"),
                              ("student_preferences", "student_preferences"),
                              ("saved_items", "saved_items")]:
        print(f"  {label:<20} {db[collection].count_documents({})}")
    # skills are stored inside the student and job documents, so count them there
    print(f"  {'student_skills':<20} {sum(len(s['skills']) for s in students)}   (inside the student documents)")
    print(f"  {'job_skills':<20} {sum(len(j['skills']) for j in jobs)}   (inside the job documents)")


if __name__ == "__main__":
    main()
