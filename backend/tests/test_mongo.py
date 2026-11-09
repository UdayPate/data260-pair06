"""
Lab 2, MongoDB migration: the data layer itself (app/mongo.py, app/documents.py, app/core/uploads.py).
These tests use the in-memory MongoDB from conftest.py (the same indexes as the real database).
"""
from datetime import date, datetime, timedelta

import pytest
from pymongo.errors import DuplicateKeyError

from app import documents, mongo
from app.enums import ApplicationStatus, JobCategory, PayPeriod
from tests.factories import (PDF, make_application, make_company, make_event, make_job, make_preferences,
                             make_registration, make_student, store_resume)

STUDENT = {"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123", "college": "SJSU"}
COMPANY = {"name": "Acme Corp", "email": "hr@acme.com", "password": "Secret123", "location": "San Jose"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


# ---------------- integer ids ----------------
def test_ids_count_up_from_one_separately_for_each_collection(db):
    assert [mongo.next_id(db, "students") for _ in range(3)] == [1, 2, 3]
    assert mongo.next_id(db, "jobs") == 1                      # another collection has its own counter
    assert mongo.next_id(db, "students") == 4


def test_a_block_of_ids_can_be_reserved_at_once(db):
    assert mongo.next_id(db, "applications", 5) == 1           # reserves 1..5
    assert mongo.next_id(db, "applications") == 6


def test_insert_gives_the_document_an_integer_id_and_dot_access(db):
    student = make_student(db, name="Ada")
    assert student.id == student["_id"] == 1 and student.name == "Ada"
    assert make_student(db).id == 2
    with pytest.raises(AttributeError):
        student.no_such_field


# ---------------- dates and enums ----------------
def test_dates_are_stored_as_text_and_come_back_as_dates(db):
    company = make_company(db)
    job = make_job(db, company.id, posting_date=date(2026, 10, 5), deadline=date(2026, 11, 20))
    raw = db.jobs.find_one({"_id": job.id})
    assert raw["posting_date"] == "2026-10-05" and raw["deadline"] == "2026-11-20"       # text in MongoDB
    loaded = mongo.get(db, "jobs", job.id)
    assert loaded.posting_date == date(2026, 10, 5) and loaded.deadline == date(2026, 11, 20)
    assert raw["category"] == "internship" and raw["pay_period"] == "hourly"              # enums stored as their text


def test_datetimes_stay_real_dates_and_dump_converts_filters(db):
    moment = datetime(2026, 11, 3, 12, 30)
    event = make_event(db, make_company(db).id, event_datetime=moment)
    assert db.events.find_one({"_id": event.id})["event_datetime"] == moment
    assert mongo.dump({"deadline": {"$gte": date(2026, 1, 2)}, "kind": JobCategory.internship}) == \
        {"deadline": {"$gte": "2026-01-02"}, "kind": "internship"}
    assert mongo.dump(moment) == moment


def test_student_experience_dates_round_trip(db):
    student = make_student(db, experiences=[documents.experience(1, title="TA", company="SJSU",
                                                                  start_date=date(2024, 1, 15))])
    loaded = mongo.get(db, "students", student.id)
    assert loaded.experiences[0].start_date == date(2024, 1, 15) and loaded.experiences[0].end_date is None


# ---------------- the unique rules live in the database ----------------
def test_two_students_cannot_share_an_email_even_without_the_api(db):
    make_student(db, email="same@x.edu")
    with pytest.raises(DuplicateKeyError):
        make_student(db, email="same@x.edu")


def test_two_companies_cannot_share_an_email(db):
    make_company(db, email="same@x.com")
    with pytest.raises(DuplicateKeyError):
        make_company(db, email="same@x.com")


def test_one_application_per_student_and_job(db):
    student, job = make_student(db), make_job(db, make_company(db).id)
    make_application(db, student.id, job.id)
    with pytest.raises(DuplicateKeyError):
        make_application(db, student.id, job.id)
    make_application(db, make_student(db).id, job.id)           # another student may apply to the same job


def test_one_registration_one_saved_item_one_preferences_document(db):
    student, event = make_student(db), make_event(db, make_company(db).id)
    make_registration(db, student.id, event.id)
    with pytest.raises(DuplicateKeyError):
        make_registration(db, student.id, event.id)
    mongo.insert(db, "saved_items", documents.saved_item(student_id=student.id, item_type="job", item_id=5))
    with pytest.raises(DuplicateKeyError):
        mongo.insert(db, "saved_items", documents.saved_item(student_id=student.id, item_type="job", item_id=5))
    make_preferences(db, student.id)
    with pytest.raises(DuplicateKeyError):
        make_preferences(db, student.id)


def test_creating_the_indexes_twice_changes_nothing(db):
    before = {c: set(db[c].index_information()) for c in ("students", "jobs", "sessions", "applications")}
    mongo.ensure_indexes(db)
    mongo.ensure_indexes(db)
    assert before == {c: set(db[c].index_information()) for c in before}
    assert db.sessions.index_information()["expires_at_1"]["expireAfterSeconds"] == 0


# ---------------- document builders ----------------
def test_builders_refuse_missing_and_misspelled_fields():
    with pytest.raises(TypeError, match="missing required field 'email'"):
        documents.student(name="A", password_hash="x", college="C")
    with pytest.raises(TypeError, match="unknown field"):
        documents.student(name="A", email="a@x", password_hash="x", college="C", colege="typo")


def test_builders_fill_every_field_and_the_derived_search_fields():
    s = documents.student(name="Ada LOVELACE", email="a@x", password_hash="x", college="C", skills=["Python", "SQL"])
    assert s["name_lower"] == "ada lovelace" and s["skills_lower"] == ["python", "sql"]
    assert s["cgpa"] is None and s["experiences"] == [] and s["created_at"] is not None
    j = documents.job(company_id=1, title="T", description="D", category=JobCategory.internship, city="San Jose",
                      posting_date=date.today(), deadline=date.today(), pay_period=PayPeriod.hourly,
                      salary_max=40, skills=["Go"])
    assert j["salary_yearly_max"] == 40 * 2080 and j["skills_lower"] == ["go"]
    e = documents.event(company_id=1, name="N", description="D", event_datetime=datetime.now(), location="L",
                        city="C", eligible_majors=["Computer Science", "All"])
    assert e["eligible_majors_lower"] == ["computer science", "all"]


@pytest.mark.parametrize("period, top, expected", [("hourly", 25, 52000), ("yearly", 90000, 90000), ("hourly", None, None)])
def test_yearly_top_pay_lets_hourly_and_yearly_jobs_compare(period, top, expected):
    assert documents.yearly_max(period, top) == expected


def test_derived_fields_follow_a_change():
    assert documents.derived("students", {"name": "Bob Smith"}) == {"name_lower": "bob smith"}
    assert documents.derived("students", {"skills": ["Go", "SQL"]}) == {"skills_lower": ["go", "sql"]}
    assert documents.derived("jobs", {"pay_period": "yearly", "salary_max": 100000}) == {"salary_yearly_max": 100000}
    assert documents.derived("students", {"city": "x"}) == {}


def test_experience_entries_always_have_every_key():
    assert documents.experience(7, title="TA", company="SJSU") == {
        "id": 7, "title": "TA", "company": "SJSU", "start_date": None, "end_date": None, "description": None}


# ---------------- files live in MongoDB (GridFS) ----------------
def test_pictures_are_stored_served_and_replaced_in_gridfs(client, db, student_headers):
    first = client.post("/students/me/profile-picture", files={"file": ("a.png", PNG, "image/png")},
                        headers=student_headers).json()["profile_pic_url"]
    assert db["profile_pics.files"].count_documents({}) == 1 and client.get(first).content == PNG
    assert client.get(first).headers["content-type"] == "image/png"
    second = client.post("/students/me/profile-picture", files={"file": ("b.png", PNG + b"1", "image/png")},
                         headers=student_headers).json()["profile_pic_url"]
    assert db["profile_pics.files"].count_documents({}) == 1          # the old one is gone
    assert client.get(first).status_code == 404 and client.get(second).status_code == 200


def test_a_company_logo_is_served_like_a_student_picture(client, db, company_headers):
    url = client.post("/companies/me/profile-picture", files={"file": ("l.png", PNG, "image/png")},
                      headers=company_headers).json()["profile_pic_url"]
    assert url.startswith("/media/profile_pics/company_1_") and client.get(url).content == PNG


def test_the_picture_route_only_accepts_plain_names(client):
    for name in ("..%2F..%2Fetc%2Fpasswd", "a b.png", "x" * 5):
        assert client.get(f"/media/profile_pics/{name}").status_code == 404


def test_deleting_an_upload_ignores_empty_and_foreign_paths(db):
    from app.core.uploads import delete_upload
    for path in (None, "", "resumes/app_1.pdf", "../x", "profile_pics/missing.png"):
        delete_upload(db, path)                                          # must not raise


def test_resume_pdf_round_trip_and_missing_file(db):
    from app.core.uploads import delete_resume, read_resume
    file_id = store_resume(db, PDF)
    assert read_resume(db, file_id) == PDF
    delete_resume(db, file_id)
    assert read_resume(db, file_id) is None and read_resume(db, None) is None


# ---------------- activity log ----------------
def test_important_actions_are_written_to_the_activity_log(client, db):
    company_token = client.post("/auth/company/signup", json=COMPANY).json()["access_token"]
    student_token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    company, student = ({"Authorization": f"Bearer {t}"} for t in (company_token, student_token))
    deadline = (date.today() + timedelta(days=20)).isoformat()
    job_id = client.post("/jobs", headers=company, json={
        "title": "Data Analyst", "description": "Analyze data and build dashboards.", "category": "internship",
        "city": "San Jose", "salary_min": 20, "salary_max": 30, "pay_period": "hourly", "deadline": deadline,
        "skills": ["Python"]}).json()["id"]
    accepted = client.post(f"/jobs/{job_id}/apply", headers=student, files={"resume": ("cv.pdf", PDF, "application/pdf")})
    assert accepted.status_code == 202                       # the application is saved by the worker (inline in the tests)
    application_id = db.applications.find_one({"job_id": job_id})["_id"]
    client.patch(f"/applications/{application_id}/status", headers=company, json={"status": "Declined"})
    client.put("/students/me/preferences", headers=student, json={"min_hourly_rate": 20})
    client.patch("/students/me", headers=student, json={"city": "San Jose"})
    log = [(a["actor_role"], a["action"], a["ref_type"], a["ref_id"]) for a in db.activity_logs.find().sort("_id", 1)]
    assert ("company", "job_created", "job", job_id) in log
    assert ("student", "application_created", "application", application_id) in log
    assert ("company", "application_status_changed", "application", application_id) in log
    assert ("student", "preferences_saved", None, None) in log and ("student", "profile_updated", None, None) in log
    assert db.activity_logs.find_one({"action": "application_status_changed"})["detail"] == {"status": "Declined"}


def test_event_registration_and_saving_are_logged(client, db):
    company_id = client.post("/auth/company/signup", json=COMPANY).json()["user_id"]
    student = {"Authorization": "Bearer " + client.post("/auth/student/signup", json=STUDENT).json()["access_token"]}
    event = make_event(db, company_id, event_datetime=datetime.now() + timedelta(days=5))
    client.post(f"/events/{event.id}/register", headers=student)
    client.delete(f"/events/{event.id}/register", headers=student)
    actions = [a["action"] for a in db.activity_logs.find({"actor_role": "student"}).sort("_id", 1)]
    assert actions[-2:] == ["event_registered", "event_unregistered"]


def test_a_failing_log_write_never_breaks_the_request(client, db, monkeypatch):
    from pymongo.errors import PyMongoError
    from app.services import activity_log

    class Broken:
        def insert_one(self, *_a, **_k):
            raise PyMongoError("log database down")

    class Wrapper:
        activity_logs = Broken()

    activity_log.log_activity(Wrapper(), "student", 1, "login")            # must only log a warning, not raise
    assert client.post("/auth/student/signup", json=STUDENT).status_code == 201


# ---------------- saved items by the assistant tool ----------------
def test_the_assistant_save_tool_writes_a_saved_item_and_a_log_entry(db):
    from datetime import date as _date
    from app.assistant.tools import ToolContext, execute_tool
    student = make_student(db)
    job = make_job(db, make_company(db).id, deadline=_date.today() + timedelta(days=10), title="Data Role")
    ctx = ToolContext(db=db, student=student)
    assert execute_tool("save_job_or_event", {"item_type": "job", "item_id": job.id}, ctx).startswith("Saved:")
    assert db.saved_items.count_documents({}) == 1
    assert db.activity_logs.find_one({"action": "item_saved"})["ref_id"] == job.id
    assert "already in the student's saved list" in execute_tool("save_job_or_event", {"item_type": "job", "item_id": job.id}, ctx)
    assert db.saved_items.count_documents({}) == 1


# ---------------- start-up order: MongoDB may come up after the service ----------------
def test_indexes_are_created_on_the_first_request_after_mongodb_comes_up(db):
    from pymongo.errors import ServerSelectionTimeoutError

    class FlakyDatabase:
        """Refuses to create indexes (as if MongoDB were still starting), then works."""
        def __init__(self, real):
            self.real, self.down, self.attempts = real, True, 0

        def __getitem__(self, name):
            return _Collection(self, self.real[name])

    class _Collection:
        def __init__(self, owner, real):
            self.owner, self.real = owner, real

        def create_index(self, *args, **kwargs):
            self.owner.attempts += 1
            if self.owner.down:
                raise ServerSelectionTimeoutError("MongoDB is not up yet")
            return self.real.create_index(*args, **kwargs)

    flaky = FlakyDatabase(db)
    mongo.use_database(flaky)
    mongo.ensure_indexes_quietly()                      # start-up: MongoDB is down, the service still starts
    assert flaky.attempts == 1 and mongo._indexes_ready is False
    with pytest.raises(ServerSelectionTimeoutError):
        mongo.get_db()                                  # a request while MongoDB is down fails (the API answers 500)
    flaky.down = False                                  # MongoDB is up now
    assert mongo.get_db() is flaky                      # the first request after that creates the indexes ...
    assert mongo._indexes_ready is True
    attempts = flaky.attempts
    mongo.get_db()
    assert flaky.attempts == attempts                   # ... and only once
    mongo.use_database(db)
