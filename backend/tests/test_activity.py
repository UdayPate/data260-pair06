"""
GET /students/me/activity: applications per day for the home-page heatmap.
Run from backend/:   python -m pytest tests/test_activity.py -q
"""
from datetime import date, datetime, time, timedelta

import pytest

from app import models

TODAY = date.today()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def new_student(client, name, email):
    r = client.post("/auth/student/signup", json={"name": name, "email": email,
                                                  "password": "Secret123", "college": "SJSU"})
    return bearer(r.json()["access_token"]), r.json()["user_id"]


def new_company(client):
    r = client.post("/auth/company/signup", json={"name": "Acme Corp", "email": "hr@acme.com",
                                                  "password": "Secret123", "location": "San Jose"})
    return bearer(r.json()["access_token"])


def post_jobs(client, company_headers, how_many):
    """Create several job postings (one student can apply to each job only once)."""
    ids = []
    for n in range(how_many):
        r = client.post("/jobs", headers=company_headers, json={
            "title": f"Job {n}", "description": "Analyze data and build dashboards.", "category": "internship",
            "city": "San Jose", "salary_min": 20, "salary_max": 30, "pay_period": "hourly",
            "deadline": (TODAY + timedelta(days=30)).isoformat(), "skills": ["Python"]})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


def add_applications(db, student_id, job_ids, applied_at_list):
    """Insert one application per (job, time) pair, straight into the database so the
    test can choose the applied_at time (the API always uses 'now')."""
    for job_id, applied_at in zip(job_ids, applied_at_list):
        db.add(models.Application(student_id=student_id, job_id=job_id, resume_path="resumes/x.pdf",
                                  applied_at=applied_at))
    db.commit()


def at(days_ago, hour=12, minute=0):
    """A time on the day `days_ago` days before today."""
    return datetime.combine(TODAY - timedelta(days=days_ago), time(hour, minute))


@pytest.fixture()
def world(client, db):
    """Ada (the student we log in as), Bob (another student) and 8 job postings."""
    ada, ada_id = new_student(client, "Ada Lovelace", "ada@example.com")
    bob, bob_id = new_student(client, "Bob Builder", "bob@example.com")
    jobs = post_jobs(client, new_company(client), 8)
    return {"ada": ada, "ada_id": ada_id, "bob": bob, "bob_id": bob_id, "jobs": jobs, "db": db}


def activity(client, headers, **params):
    return client.get("/students/me/activity", headers=headers, params=params)


def test_counts_applications_per_day_oldest_first(client, world):
    # 3 applications on one day (different times of day), 1 on another day, 2 on a third
    add_applications(world["db"], world["ada_id"], world["jobs"][:6],
                     [at(10, 0, 5), at(10, 9), at(10, 23, 59), at(3), at(1, 8), at(1, 20)])
    r = activity(client, world["ada"])
    assert r.status_code == 200
    assert r.json() == [
        {"date": (TODAY - timedelta(days=10)).isoformat(), "count": 3},
        {"date": (TODAY - timedelta(days=3)).isoformat(), "count": 1},
        {"date": (TODAY - timedelta(days=1)).isoformat(), "count": 2},
    ]


def test_no_applications_gives_an_empty_list(client, world):
    r = activity(client, world["ada"])
    assert r.status_code == 200 and r.json() == []


def test_only_my_own_applications_are_counted(client, world):
    add_applications(world["db"], world["ada_id"], world["jobs"][:2], [at(2), at(2, 15)])
    add_applications(world["db"], world["bob_id"], world["jobs"][:4], [at(2), at(2, 10), at(2, 11), at(5)])
    assert activity(client, world["ada"]).json() == [{"date": (TODAY - timedelta(days=2)).isoformat(), "count": 2}]
    assert activity(client, world["bob"]).json() == [
        {"date": (TODAY - timedelta(days=5)).isoformat(), "count": 1},
        {"date": (TODAY - timedelta(days=2)).isoformat(), "count": 3},
    ]


def test_days_outside_the_range_are_excluded(client, world):
    # with days=7 the window is today and the 6 days before it
    add_applications(world["db"], world["ada_id"], world["jobs"][:4], [at(0), at(6, 0, 0), at(7, 23, 59), at(30)])
    r = activity(client, world["ada"], days=7)
    assert [item["date"] for item in r.json()] == [(TODAY - timedelta(days=6)).isoformat(), TODAY.isoformat()]
    # the same applications with a longer window
    assert len(activity(client, world["ada"], days=31).json()) == 4
    assert len(activity(client, world["ada"], days=1).json()) == 1   # just today


def test_default_window_is_365_days(client, world):
    add_applications(world["db"], world["ada_id"], world["jobs"][:3], [at(364), at(365), at(400)])
    r = activity(client, world["ada"])
    assert [item["date"] for item in r.json()] == [(TODAY - timedelta(days=364)).isoformat()]
    assert len(activity(client, world["ada"], days=730).json()) == 3


def test_applications_dated_in_the_future_are_not_counted(client, world):
    add_applications(world["db"], world["ada_id"], world["jobs"][:2], [at(0), datetime.combine(TODAY + timedelta(days=1), time(9, 0))])
    assert activity(client, world["ada"]).json() == [{"date": TODAY.isoformat(), "count": 1}]


def test_a_new_application_made_through_the_api_shows_up_today(client, world):
    # apply for real (a PDF upload) and see today's count go up
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    r = client.post(f"/jobs/{world['jobs'][0]}/apply", headers=world["ada"],
                    files={"resume": ("cv.pdf", pdf, "application/pdf")})
    assert r.status_code == 201, r.text
    assert activity(client, world["ada"]).json() == [{"date": TODAY.isoformat(), "count": 1}]


def test_requires_a_login(client):
    assert client.get("/students/me/activity").status_code == 401


def test_a_company_is_refused(client, company_headers):
    assert activity(client, company_headers).status_code == 403


@pytest.mark.parametrize("days", ["0", "-5", "731", "abc", "1.5", ""], ids=["zero", "negative", "too-big", "text", "decimal", "empty"])
def test_bad_days_value_is_422(client, world, days):
    assert activity(client, world["ada"], days=days).status_code == 422


@pytest.mark.parametrize("days", [1, 730], ids=["min", "max"])
def test_days_limits_are_accepted(client, world, days):
    assert activity(client, world["ada"], days=days).status_code == 200
