"""
Applications, resume privacy, applicant review and status changes.
Run from backend/:   python -m pytest -q
"""
import os
from datetime import date, datetime, timedelta
from urllib.parse import unquote

import pytest

from app import config, models

TODAY = date.today()
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def new_company(client, name, email):
    r = client.post("/auth/company/signup", json={"name": name, "email": email,
                                                  "password": "Secret123", "location": "San Jose"})
    return bearer(r.json()["access_token"]), r.json()["user_id"]


def new_student(client, name, email):
    r = client.post("/auth/student/signup", json={"name": name, "email": email,
                                                  "password": "Secret123", "college": "SJSU"})
    return bearer(r.json()["access_token"]), r.json()["user_id"]


def post_job(client, headers, title="Data Analyst", deadline_days=30):
    r = client.post("/jobs", headers=headers, json={
        "title": title, "description": "Analyze data and build dashboards.", "category": "internship",
        "city": "San Jose", "salary_min": 20, "salary_max": 30, "pay_period": "hourly",
        "deadline": (TODAY + timedelta(days=deadline_days)).isoformat(), "skills": ["Python"]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def apply(client, job_id, headers, content=PDF, name="cv.pdf", field="resume"):
    return client.post(f"/jobs/{job_id}/apply", headers=headers, files={field: (name, content, "application/pdf")})


def resumes_on_disk():
    folder = os.path.join(config.UPLOAD_DIR, "resumes")
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


@pytest.fixture()
def world(client, db, student_headers):
    """Ada (student_headers) and Bob are students. Acme and Globex are companies.
    Acme owns two open jobs and one expired job; Globex owns one open job."""
    acme, acme_id = new_company(client, "Acme Corp", "hr@acme.com")
    globex, globex_id = new_company(client, "Globex Inc", "hr@globex.com")
    bob, bob_id = new_student(client, "Bob Builder", "bob@example.com")
    ids = {"job1": post_job(client, acme, "Data Analyst"), "job2": post_job(client, acme, "Software Engineer"),
           "globex_job": post_job(client, globex, "Marketing Associate")}
    expired = models.Job(company_id=acme_id, title="Old Role", description="A posting that already closed.",
                         category=models.JobCategory.internship, city="San Jose", is_remote=False,
                         salary_min=20, salary_max=25, pay_period=models.PayPeriod.hourly,
                         posting_date=TODAY - timedelta(days=60), deadline=TODAY - timedelta(days=1))
    db.add(expired)
    db.commit()
    ids["expired"] = expired.id
    return {"ada": student_headers, "bob": bob, "acme": acme, "globex": globex, "ids": ids,
            "acme_id": acme_id, "bob_id": bob_id}


# ===================================================================== apply
def test_student_applies_with_pdf(client, world):
    before = resumes_on_disk()
    r = apply(client, world["ids"]["job1"], world["ada"])
    assert r.status_code == 201
    app = r.json()
    assert app["status"] == "Pending" and app["job"]["title"] == "Data Analyst"
    assert app["job"]["company_name"] == "Acme Corp" and app["job"]["is_expired"] is False
    assert app["resume_url"] == f"/applications/{app['id']}/resume"
    assert "resume_path" not in app and "uploads" not in str(app)          # no file paths leak
    new_files = resumes_on_disk() - before
    assert len(new_files) == 1 and next(iter(new_files)).endswith(".pdf")  # server-chosen filename


def test_apply_requires_student_login(client, world):
    jid = world["ids"]["job1"]
    assert apply(client, jid, {}).status_code == 401
    assert apply(client, jid, world["acme"]).status_code == 403


def test_apply_to_missing_or_expired_job(client, world):
    before = resumes_on_disk()
    assert apply(client, 99999, world["ada"]).status_code == 404
    expired = apply(client, world["ids"]["expired"], world["ada"])
    assert expired.status_code == 409 and "deadline" in expired.json()["detail"]
    assert resumes_on_disk() == before            # nothing was stored for refused applications


def test_cannot_apply_twice_but_can_apply_to_other_jobs(client, world):
    assert apply(client, world["ids"]["job1"], world["ada"]).status_code == 201
    before = resumes_on_disk()
    again = apply(client, world["ids"]["job1"], world["ada"])
    assert again.status_code == 409 and "already applied" in again.json()["detail"]
    assert resumes_on_disk() == before            # the refused upload left no file behind
    assert apply(client, world["ids"]["job2"], world["ada"]).status_code == 201
    assert apply(client, world["ids"]["job1"], world["bob"]).status_code == 201   # another student: fine


@pytest.mark.parametrize("content,name,expected", [
    (b"just some text", "resume.pdf", 415),
    (b"\x89PNG\r\n\x1a\n" + b"0" * 50, "resume.pdf", 415),
    (b"<html><script>1</script></html>", "resume.pdf", 415),
    (b"   %PDF-1.4 starts with spaces", "resume.pdf", 415),
    (b"hello\n%PDF-1.4 signature not at the start", "resume.pdf", 415),
    (b"", "resume.pdf", 400),
], ids=["text", "png-named-pdf", "html", "leading-spaces", "signature-later", "empty"])
def test_non_pdf_uploads_rejected(client, world, content, name, expected):
    before = resumes_on_disk()
    assert apply(client, world["ids"]["job1"], world["ada"], content=content, name=name).status_code == expected
    assert resumes_on_disk() == before
    assert client.get("/applications/mine", headers=world["ada"]).json()["total"] == 0


def test_resume_over_5mb_rejected(client, world):
    big = PDF + b"0" * (5 * 1024 * 1024)
    assert apply(client, world["ids"]["job1"], world["ada"], content=big).status_code == 413
    just_ok = (PDF + b"0" * (5 * 1024 * 1024 - len(PDF) - 10))
    assert apply(client, world["ids"]["job1"], world["ada"], content=just_ok).status_code == 201


def test_resume_must_be_sent_in_the_resume_field(client, world):
    assert apply(client, world["ids"]["job1"], world["ada"], field="file").status_code == 422
    assert client.post(f"/jobs/{world['ids']['job1']}/apply", headers=world["ada"]).status_code == 422


def test_filename_from_user_is_ignored(client, world):
    r = apply(client, world["ids"]["job1"], world["ada"], name="../../evil.pdf")
    assert r.status_code == 201
    assert not any("evil" in f for f in resumes_on_disk())


def test_job_details_show_my_application_only_to_the_applicant(client, world):
    jid = world["ids"]["job1"]
    assert client.get(f"/jobs/{jid}", headers=world["ada"]).json()["my_application"] is None
    applied = apply(client, jid, world["ada"]).json()
    mine = client.get(f"/jobs/{jid}", headers=world["ada"]).json()["my_application"]
    assert mine["id"] == applied["id"] and mine["status"] == "Pending"
    assert client.get(f"/jobs/{jid}", headers=world["bob"]).json()["my_application"] is None
    assert client.get(f"/jobs/{jid}", headers=world["acme"]).json()["my_application"] is None


# ===================================================================== student: my applications
def test_my_applications_lists_only_mine_newest_first(client, world):
    apply(client, world["ids"]["job1"], world["ada"])
    apply(client, world["ids"]["job2"], world["ada"])
    apply(client, world["ids"]["globex_job"], world["bob"])
    body = client.get("/applications/mine", headers=world["ada"]).json()
    assert body["total"] == 2
    assert [a["job"]["title"] for a in body["items"]] == ["Software Engineer", "Data Analyst"]
    assert client.get("/applications/mine", headers=world["bob"]).json()["total"] == 1


def test_my_applications_filter_by_status_and_page(client, world):
    a1 = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    a2 = apply(client, world["ids"]["job2"], world["ada"]).json()["id"]
    client.patch(f"/applications/{a1}/status", headers=world["acme"], json={"status": "Reviewed"})
    client.patch(f"/applications/{a2}/status", headers=world["acme"], json={"status": "Declined"})

    def ids(**params):
        return [a["id"] for a in client.get("/applications/mine", params=params, headers=world["ada"]).json()["items"]]
    assert ids(status="Reviewed") == [a1] and ids(status="Declined") == [a2] and ids(status="Pending") == []
    assert len(ids()) == 2
    page = client.get("/applications/mine", params={"page_size": 1}, headers=world["ada"]).json()
    assert page["total"] == 2 and page["total_pages"] == 2 and len(page["items"]) == 1


@pytest.mark.parametrize("params", [{"status": "Accepted"}, {"status": "pending"}, {"page": 0}, {"page_size": 101}],
                         ids=["unknown-status", "wrong-case", "page-0", "page-size-101"])
def test_my_applications_bad_params(client, world, params):
    assert client.get("/applications/mine", params=params, headers=world["ada"]).status_code == 422


def test_my_applications_requires_student(client, world):
    assert client.get("/applications/mine").status_code == 401
    assert client.get("/applications/mine", headers=world["acme"]).status_code == 403


# ===================================================================== company: applicants
def test_company_lists_applicants_for_its_job(client, world):
    client.patch("/students/me", headers=world["ada"], json={"major": "Data Science", "skills": ["Python", "SQL"]})
    apply(client, world["ids"]["job1"], world["ada"])
    apply(client, world["ids"]["job1"], world["bob"])
    apply(client, world["ids"]["job2"], world["bob"])
    r = client.get(f"/jobs/{world['ids']['job1']}/applications", headers=world["acme"])
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and {a["student"]["name"] for a in body["items"]} == {"Ada Lovelace", "Bob Builder"}
    ada = next(a for a in body["items"] if a["student"]["name"] == "Ada Lovelace")
    assert ada["student"]["email"] == "ada@example.com" and ada["student"]["skills"] == ["Python", "SQL"]
    assert ada["student"]["major"] == "Data Science" and ada["status"] == "Pending"
    assert not {"password_hash", "date_of_birth", "experience"} & set(ada["student"])   # card only, no DOB
    assert "password" not in r.text and "hash" not in r.text


def test_applicants_filter_by_status(client, world):
    a = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    apply(client, world["ids"]["job1"], world["bob"])
    client.patch(f"/applications/{a}/status", headers=world["acme"], json={"status": "Reviewed"})
    url = f"/jobs/{world['ids']['job1']}/applications"
    assert client.get(url, params={"status": "Reviewed"}, headers=world["acme"]).json()["total"] == 1
    assert client.get(url, params={"status": "Pending"}, headers=world["acme"]).json()["total"] == 1
    assert client.get(url, params={"status": "Declined"}, headers=world["acme"]).json()["total"] == 0
    assert client.get(url, params={"status": "Hired"}, headers=world["acme"]).status_code == 422


def test_applicants_list_is_private_to_the_job_owner(client, world):
    apply(client, world["ids"]["job1"], world["ada"])
    url = f"/jobs/{world['ids']['job1']}/applications"
    assert client.get(url, headers=world["globex"]).status_code == 403        # another company
    assert client.get(url, headers=world["ada"]).status_code == 403           # a student
    assert client.get(url).status_code == 401
    assert client.get("/jobs/99999/applications", headers=world["acme"]).status_code == 404


def test_jobs_mine_counts_applicants(client, world):
    apply(client, world["ids"]["job1"], world["ada"])
    apply(client, world["ids"]["job1"], world["bob"])
    counts = {j["title"]: j["applicant_count"] for j in client.get("/jobs/mine", headers=world["acme"]).json()["items"]}
    assert counts["Data Analyst"] == 2 and counts["Software Engineer"] == 0


def test_applicant_detail_has_full_profile_without_date_of_birth(client, world):
    client.patch("/students/me", headers=world["ada"], json={
        "date_of_birth": "2001-04-02", "phone": "(408) 555-0123", "city": "San Jose", "cgpa": 3.9,
        "career_objective": "Data engineering.", "skills": ["Python"],
        "experience": [{"title": "Intern", "company": "Everlaw", "start_date": "2025-06-01"}]})
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    r = client.get(f"/applications/{app_id}", headers=world["acme"])
    assert r.status_code == 200
    body = r.json()
    s = body["student"]
    assert s["phone"] == "(408) 555-0123" and s["career_objective"] == "Data engineering." and s["cgpa"] == 3.9
    assert s["experience"][0]["company"] == "Everlaw" and s["skills"] == ["Python"]
    assert "date_of_birth" not in s and "2001" not in r.text and "password" not in r.text
    assert body["job"]["title"] == "Data Analyst" and body["resume_url"] == f"/applications/{app_id}/resume"


def test_applicant_detail_privacy(client, world):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    assert client.get(f"/applications/{app_id}", headers=world["globex"]).status_code == 404   # other company
    assert client.get(f"/applications/{app_id}", headers=world["ada"]).status_code == 403      # students use /mine
    assert client.get(f"/applications/{app_id}").status_code == 401
    assert client.get("/applications/99999", headers=world["acme"]).status_code == 404


# ===================================================================== status changes
def test_company_can_set_any_of_the_three_statuses(client, world):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    for new_status in ["Reviewed", "Declined", "Pending", "Reviewed"]:
        r = client.patch(f"/applications/{app_id}/status", headers=world["acme"], json={"status": new_status})
        assert r.status_code == 200 and r.json()["status"] == new_status
    mine = client.get("/applications/mine", headers=world["ada"]).json()["items"][0]
    assert mine["status"] == "Reviewed"                                   # the student sees it


@pytest.mark.parametrize("payload", [
    {"status": "Accepted"}, {"status": "reviewed"}, {"status": ""}, {"status": None}, {},
    {"status": "Reviewed", "student_id": 5}, {"status": 1},
], ids=["accepted", "lowercase", "blank", "null", "missing", "extra-field", "number"])
def test_invalid_status_rejected(client, world, payload):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    assert client.patch(f"/applications/{app_id}/status", headers=world["acme"], json=payload).status_code == 422
    assert client.get("/applications/mine", headers=world["ada"]).json()["items"][0]["status"] == "Pending"


def test_only_the_owning_company_can_change_status(client, world):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    body = {"status": "Declined"}
    assert client.patch(f"/applications/{app_id}/status", headers=world["globex"], json=body).status_code == 404
    assert client.patch(f"/applications/{app_id}/status", headers=world["ada"], json=body).status_code == 403
    assert client.patch(f"/applications/{app_id}/status", json=body).status_code == 401
    assert client.patch("/applications/99999/status", headers=world["acme"], json=body).status_code == 404
    assert client.get("/applications/mine", headers=world["ada"]).json()["items"][0]["status"] == "Pending"


# ===================================================================== resume privacy
def test_student_and_owning_company_can_read_the_resume(client, world):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    for who in ("ada", "acme"):
        r = client.get(f"/applications/{app_id}/resume", headers=world[who])
        assert r.status_code == 200, who
        assert r.content == PDF and r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("inline")
        assert "Resume - Ada Lovelace.pdf" in unquote(r.headers["content-disposition"])   # browsers decode %20
        assert r.headers["x-content-type-options"] == "nosniff" and "no-store" in r.headers["cache-control"]


def test_everyone_else_gets_404_for_a_resume(client, world):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    url = f"/applications/{app_id}/resume"
    assert client.get(url, headers=world["bob"]).status_code == 404       # another student
    assert client.get(url, headers=world["globex"]).status_code == 404    # a company that doesn't own the job
    assert client.get(url).status_code == 401                              # not logged in
    assert client.get("/applications/99999/resume", headers=world["ada"]).status_code == 404
    # same answer as for a non-existent application: the API doesn't reveal that it exists
    assert client.get(url, headers=world["bob"]).json() == client.get("/applications/99999/resume", headers=world["bob"]).json()


def test_resume_files_are_not_served_as_static_files(client, world):
    apply(client, world["ids"]["job1"], world["ada"])
    name = next(iter(resumes_on_disk()))
    for path in (f"/media/resumes/{name}", f"/uploads/resumes/{name}", f"/media/profile_pics/../resumes/{name}"):
        assert client.get(path).status_code in (400, 404), path


def test_missing_file_is_404(client, world):
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    # delete every stored resume file from disk, as if someone removed it by hand
    for name in list(resumes_on_disk()):
        os.remove(os.path.join(config.UPLOAD_DIR, "resumes", name))
    r = client.get(f"/applications/{app_id}/resume", headers=world["ada"])
    assert r.status_code == 404 and "file not found" in r.json()["detail"].lower()


@pytest.mark.parametrize("bad_path", ["../../etc/passwd", "resumes/../../secret.txt", "/etc/passwd",
                                      "profile_pics/x.png", "..", ""],
                         ids=["dotdot", "dotdot-inside", "absolute", "wrong-folder", "parent", "blank"])
def test_tampered_database_path_cannot_expose_other_files(client, db, world, bad_path):
    # Even if a bad value somehow got into the database, the endpoint must not serve it.
    secret = os.path.join(config.UPLOAD_DIR, "secret.txt")
    with open(secret, "w") as f:
        f.write("top secret")
    os.makedirs(os.path.join(config.UPLOAD_DIR, "profile_pics"), exist_ok=True)
    with open(os.path.join(config.UPLOAD_DIR, "profile_pics", "x.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    app_id = apply(client, world["ids"]["job1"], world["ada"]).json()["id"]
    row = db.get(models.Application, app_id)
    row.resume_path = bad_path
    db.commit()
    r = client.get(f"/applications/{app_id}/resume", headers=world["ada"])
    assert r.status_code == 404 and b"top secret" not in r.content


def test_shared_seed_style_resume_is_served(client, db, world):
    # The seed script points many applications at one placeholder file, "resumes/seed_resume.pdf".
    folder = os.path.join(config.UPLOAD_DIR, "resumes")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "seed_resume.pdf"), "wb") as f:
        f.write(PDF)
    ada_id = client.get("/students/me", headers=world["ada"]).json()["id"]
    seeded = models.Application(student_id=ada_id, job_id=world["ids"]["job1"], resume_path="resumes/seed_resume.pdf",
                                status=models.ApplicationStatus.pending, applied_at=datetime.now())
    db.add(seeded)
    db.commit()
    for who in ("ada", "acme"):
        r = client.get(f"/applications/{seeded.id}/resume", headers=world[who])
        assert r.status_code == 200 and r.content == PDF