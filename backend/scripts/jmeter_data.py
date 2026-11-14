"""
Test data for the JMeter load tests (Lab 2, Part 5).

    python -m scripts.jmeter_data               (from backend/; reads the MongoDB at MONGO_URL, writes ../jmeter/data/)

JMeter reads its inputs from CSV files. This script reads the SEEDED database and writes:

  students.csv            every seeded student: email, password, role          (all seeded accounts use Password123!)
  apply_pool.csv          (student, open job) pairs that have NOT applied yet   -> the runner hands each run its own slice
  event_pool.csv          (student, upcoming event) pairs the student may register for and has not yet
  assistant_messages.csv  50 questions for the assistant
  resume.pdf              a tiny valid PDF used as the resume in the apply test

Why pools and slices: an application is unique per (student, job) and a registration per (student, event), so a pair can be
used ONCE; using it again answers 409. The runner takes a fresh, never-used slice of the pool for every run.
The pools are shuffled with SEED 6 (the pair's seed) so a run is repeatable.
"""
import csv
import random
import sys
from datetime import date
from pathlib import Path

from app import mongo
from app.config import SEED

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "jmeter" / "data"
PASSWORD = "Password123!"
MAX_POOL = 6000

QUESTIONS = [
    "Find a data internship", "Find internships in Sunnyvale", "Which upcoming events are open to Computer Science students?",
    "What are my job preferences?", "Find remote analyst jobs", "Show jobs that match my skills Python and SQL",
    "Find an internship in Mountain View paying at least 25 dollars an hour", "Are there any career fairs next month?",
    "Find a cloud internship", "Find a backend engineer internship in San Jose", "Show me part-time jobs in San Jose",
    "Find on-campus jobs", "Which events are in San Jose?", "Find a machine learning internship", "Show full-time jobs that pay well",
    "Find a software engineer internship", "Are there workshops this month?", "Find jobs at companies in Sunnyvale",
    "Show internships with a deadline this month", "Find a research assistant position",
]

# The smallest valid PDF: one empty page. The API only checks that the file starts with %PDF and is under 5 MB.
TINY_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF\n")


def write_csv(path: Path, header, rows) -> int:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)      # JMeter's CSV reader is set to quoted data
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    db = mongo.get_database()
    rng = random.Random(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    students = mongo.find(db, "students", sort=[("_id", 1)])
    if not students:
        print("The database has no students. Seed it first: python -m seed.generate_seed --reset")
        return 2
    write_csv(DATA_DIR / "students.csv", ["email", "password", "role"], [[s.email, PASSWORD, "student"] for s in students])

    applied = {(a["student_id"], a["job_id"]) for a in db.applications.find({}, {"student_id": 1, "job_id": 1})}
    open_jobs = [j["_id"] for j in db.jobs.find({"deadline": {"$gte": date.today().isoformat()}}, {"_id": 1})]
    apply_pairs = [[s.email, PASSWORD, "student", job] for s in students for job in open_jobs if (s.id, job) not in applied]
    rng.shuffle(apply_pairs)

    registered = {(r["student_id"], r["event_id"]) for r in db.event_registrations.find({}, {"student_id": 1, "event_id": 1})}
    now = date.today().isoformat()
    events = [e for e in db.events.find({}) if str(e["event_datetime"])[:10] >= now]
    event_pairs = []
    for s in students:
        for e in events:
            majors = [m.lower() for m in e.get("eligible_majors") or []]
            eligible = "all" in majors or (s.get("major") or "").lower() in majors
            if eligible and (s.id, e["_id"]) not in registered:
                event_pairs.append([s.email, PASSWORD, "student", e["_id"]])
    rng.shuffle(event_pairs)

    counts = {
        "students.csv": len(students),
        "apply_pool.csv": write_csv(DATA_DIR / "apply_pool.csv", ["email", "password", "role", "job_id"], apply_pairs[:MAX_POOL]),
        "event_pool.csv": write_csv(DATA_DIR / "event_pool.csv", ["email", "password", "role", "event_id"], event_pairs[:MAX_POOL]),
        "assistant_messages.csv": write_csv(DATA_DIR / "assistant_messages.csv", ["message"], [[q] for q in (QUESTIONS * 3)[:50]]),
    }
    (DATA_DIR / "resume.pdf").write_bytes(TINY_PDF)
    for name, count in counts.items():
        print(f"{name}: {count} rows")
    print(f"resume.pdf: {len(TINY_PDF)} bytes\nWritten to {DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
