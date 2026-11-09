"""
Helpers that put documents straight into the test database, for the cases where the API would refuse
(an already-expired job, a past event, a chosen applied_at time...). Each returns the stored document (a Doc),
so tests can use .id, .name and so on. Every field has a default; pass keyword arguments to change it.
"""
from datetime import date, datetime, timedelta

from app import documents, mongo
from app.enums import JobCategory, PayPeriod

PDF = b"%PDF-1.4\n% a tiny test resume\n"


def make_student(db, **fields):
    n = db.students.count_documents({}) + 1
    fields = {"name": f"Student {n}", "email": f"student{n}@test.edu", "password_hash": "x", "college": "SJSU", **fields}
    return mongo.insert(db, "students", documents.student(**fields))


def make_company(db, **fields):
    n = db.companies.count_documents({}) + 1
    fields = {"name": f"Company {n}", "email": f"company{n}@test.com", "password_hash": "x", "city": "San Jose",
              "state": "CA", **fields}
    return mongo.insert(db, "companies", documents.company(**fields))


def make_job(db, company_id, **fields):
    today = date.today()
    fields = {"title": "Old Role", "description": "A posting that already closed.", "category": JobCategory.internship,
              "city": "San Jose", "is_remote": False, "salary_min": 20, "salary_max": 25,
              "pay_period": PayPeriod.hourly, "posting_date": today - timedelta(days=60),
              "deadline": today - timedelta(days=1), "skills": [], **fields}
    return mongo.insert(db, "jobs", documents.job(company_id=company_id, **fields))


def make_event(db, company_id, **fields):
    fields = {"name": "Old Meetup", "description": "This meetup already happened.", "location": "1 Old Rd",
              "city": "San Jose", "event_datetime": datetime.now() - timedelta(days=3),
              "eligible_majors": ["All"], **fields}
    return mongo.insert(db, "events", documents.event(company_id=company_id, **fields))


def make_application(db, student_id, job_id, **fields):
    return mongo.insert(db, "applications", documents.application(student_id=student_id, job_id=job_id, **fields))


def make_registration(db, student_id, event_id, registered_at=None):
    return mongo.insert(db, "event_registrations", documents.registration(
        student_id=student_id, event_id=event_id, registered_at=registered_at or datetime.now()))


def make_preferences(db, student_id, **fields):
    return mongo.insert(db, "student_preferences", documents.preferences(student_id=student_id, **fields))


def store_resume(db, data=PDF, name="seed_resume.pdf"):
    """Put a resume PDF into GridFS (bucket "resumes") and return its id."""
    return mongo.bucket(db, "resumes").put(data, filename=name, content_type="application/pdf")


def resume_names(db):
    """The names of every resume file stored in GridFS."""
    return {f["filename"] for f in db["resumes.files"].find()}
