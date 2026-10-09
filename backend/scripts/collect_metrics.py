"""
Collects the Part A numbers for METRICS.md from YOUR running system.

  1. counts the rows in MySQL and checks them against the handout's minimums
  2. times the main API calls (median, 95th percentile, slowest) against the running server
  3. optionally runs the backend tests and reports how many passed

Start the backend first (uvicorn app.main:app --port 9060), then run from backend/:

    python -m scripts.collect_metrics                 # counts + latency
    python -m scripts.collect_metrics --with-tests    # also runs pytest (takes a few minutes)

It prints a Markdown block and also saves it to docs/part_a_metrics.md. Paste that block into
METRICS.md. It only READS data (it logs in as the demo accounts and calls GET endpoints).
"""
import argparse
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime

import httpx
from sqlalchemy import func, select

from app import models as m
from app.config import BACKEND_PORT, CITY_SET, PAIR_STR, SEED
from app.database import SessionLocal

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
PASSWORD = "Password123!"
REPEATS = 30

# (label, model, minimum required by the handout or None)
TABLES = [
    ("Companies", m.Company, 50), ("Students", m.Student, 200), ("Job postings", m.Job, 300),
    ("Applications", m.Application, 1500), ("Events", m.Event, 100),
    ("Event registrations", m.EventRegistration, None), ("Saved preferences", m.StudentPreference, None),
    ("Saved items", m.SavedItem, None), ("Student skills", m.StudentSkill, None), ("Job skills", m.JobSkill, None),
]


def count_rows():
    with SessionLocal() as db:
        return [(label, db.scalar(select(func.count()).select_from(model)), minimum) for label, model, minimum in TABLES]


def login(client, email, role):
    started = time.perf_counter()
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD, "role": role})
    r.raise_for_status()
    return r.json()["access_token"], (time.perf_counter() - started) * 1000


def time_call(client, path, headers, params=None):
    samples, status = [], None
    for _ in range(REPEATS):
        started = time.perf_counter()
        r = client.get(path, headers=headers, params=params)
        samples.append((time.perf_counter() - started) * 1000)
        status = r.status_code
    samples.sort()
    return status, statistics.median(samples), samples[int(0.95 * (len(samples) - 1))], samples[-1]


def latency_rows(client):
    student, _ = login(client, "demo.student@sjsu.edu", "student")
    company, _ = login(client, "demo.company@example.com", "company")
    sh, ch = {"Authorization": f"Bearer {student}"}, {"Authorization": f"Bearer {company}"}
    first_job = client.get("/jobs/mine", headers=ch).json()["items"]
    my_job = first_job[0]["id"] if first_job else 1
    plan = [
        ("GET /jobs (no filter)", "/jobs", sh, None),
        ("GET /jobs?q=data", "/jobs", sh, {"q": "data"}),
        ("GET /jobs (internship + city + remote)", "/jobs", sh, {"category": "internship", "city": CITY_SET[0], "is_remote": "true"}),
        ("GET /jobs (skills Python + SQL, all)", "/jobs", sh, {"skills": ["Python", "SQL"], "skills_match": "all"}),
        ("GET /jobs/1", "/jobs/1", sh, None),
        ("GET /events", "/events", sh, None),
        ("GET /students?q=a (peer view)", "/students", sh, {"q": "a"}),
        ("GET /applications/mine", "/applications/mine", sh, None),
        ("GET /students/me", "/students/me", sh, None),
        ("GET /students/me/preferences", "/students/me/preferences", sh, None),
        ("GET /meta/options", "/meta/options", sh, None),
        ("GET /jobs/mine (company)", "/jobs/mine", ch, None),
        (f"GET /jobs/{my_job}/applications (company)", f"/jobs/{my_job}/applications", ch, None),
        ("GET /events/mine (company)", "/events/mine", ch, None),
        ("GET /students (company view)", "/students", ch, {"q": "a"}),
    ]
    rows = []
    for label, path, headers, params in plan:
        status, median, p95, worst = time_call(client, path, headers, params)
        rows.append((label, status, median, p95, worst))
    logins = [login(client, "demo.student@sjsu.edu", "student")[1] for _ in range(5)]
    return rows, statistics.median(logins)


def run_tests():
    started = time.perf_counter()
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], capture_output=True, text=True)
    tail = (out.stdout.strip().splitlines() or ["(no output)"])[-1]
    return tail, time.perf_counter() - started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-tests", action="store_true")
    args = ap.parse_args()

    lines = [f"### Part A: platform (collected {datetime.now():%Y-%m-%d %H:%M})", "",
             f"Pair {PAIR_STR}, SEED {SEED}, cities {', '.join(CITY_SET)}, backend port {BACKEND_PORT}.", "",
             "#### Seed data (MySQL row counts)", "", "| Table | Rows | Required | Met |", "|---|---:|---:|:---:|"]
    for label, n, minimum in count_rows():
        lines.append(f"| {label} | {n} | {minimum if minimum else '-'} | {'yes' if minimum is None else ('yes' if n >= minimum else '**NO**')} |")

    try:
        with httpx.Client(base_url=f"http://localhost:{BACKEND_PORT}", timeout=30) as client:
            client.get("/health").raise_for_status()
            rows, login_ms = latency_rows(client)
        lines += ["", f"#### API latency (each call repeated {REPEATS} times, local machine, milliseconds)", "",
                  "| Request | Status | Median | p95 | Slowest |", "|---|:---:|---:|---:|---:|"]
        lines += [f"| {label} | {status} | {median:.1f} | {p95:.1f} | {worst:.1f} |" for label, status, median, p95, worst in rows]
        lines += ["", f"Login (bcrypt, deliberately slow): median {login_ms:.0f} ms over 5 logins."]
    except (httpx.HTTPError, KeyError) as exc:
        lines += ["", f"_Latency not measured: could not use the backend on port {BACKEND_PORT} ({exc}). Start it and run again._"]

    if args.with_tests:
        tail, seconds = run_tests()
        lines += ["", "#### Automated tests", "", f"- Backend: `{tail}` in {seconds:.0f} s",
                  "- Frontend: run `npm test` in frontend/ and paste the last lines here"]

    text = "\n".join(lines) + "\n"
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "part_a_metrics.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
