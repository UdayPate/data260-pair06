"""
Job posting, search, details and public company profile tests.
Run from backend/:   python -m pytest -q
"""
from datetime import date, datetime, timedelta

import pytest

from app import models

TODAY = date.today()


def iso(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def new_company(client, name, email, city="San Jose"):
    r = client.post("/auth/company/signup", json={"name": name, "email": email,
                                                  "password": "Secret123", "location": city})
    return bearer(r.json()["access_token"]), r.json()["user_id"]


def job_body(**overrides):
    body = {"title": "Data Analyst", "description": "Analyze data and build dashboards.",
            "category": "internship", "city": "San Jose", "is_remote": False,
            "salary_min": 20, "salary_max": 30, "pay_period": "hourly",
            "deadline": iso(30), "skills": []}
    body.update(overrides)
    return body


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def world(client, db, student_headers):
    """Two companies, five open jobs (posted through the API) and one expired job (inserted
    directly, because the API refuses past deadlines)."""
    acme_h, acme_id = new_company(client, "Acme Corp", "hr@acme.com", "San Jose")
    globex_h, globex_id = new_company(client, "Globex Inc", "hr@globex.com", "Sunnyvale")

    def post(headers, **kw):
        r = client.post("/jobs", json=job_body(**kw), headers=headers)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    ids = {
        "ds_intern": post(acme_h, title="Data Science Intern", category="internship", city="San Jose",
                          is_remote=True, salary_min=30, salary_max=40, skills=["Python", "Machine Learning"],
                          deadline=iso(30)),
        "swe": post(acme_h, title="Software Engineer", category="full_time", city="San Jose",
                    salary_min=120000, salary_max=150000, pay_period="yearly",
                    skills=["Python", "Go", "AWS"], deadline=iso(60)),
        "da_intern": post(globex_h, title="Data Analyst Intern", category="internship", city="Sunnyvale",
                          salary_min=25, salary_max=30, skills=["SQL", "Excel", "Python"], deadline=iso(10)),
        "library": post(globex_h, title="Library Assistant", category="on_campus", city="Mountain View",
                        salary_min=18, salary_max=20, skills=["Customer Service"], deadline=iso(20)),
        "marketing": post(globex_h, title="Marketing Associate", category="part_time", city="Sunnyvale",
                          salary_min=20, salary_max=24, skills=["Marketing", "Communication"], deadline=iso(40)),
    }
    expired = models.Job(company_id=acme_id, title="Old Data Role", description="An old posting that closed.",
                         category=models.JobCategory.internship, city="San Jose", is_remote=False,
                         salary_min=20, salary_max=25, pay_period=models.PayPeriod.hourly,
                         posting_date=TODAY - timedelta(days=60), deadline=TODAY - timedelta(days=1))
    db.add(expired)
    db.commit()
    ids["expired"] = expired.id
    return {"ids": ids, "acme": acme_h, "globex": globex_h, "acme_id": acme_id, "student": student_headers}


def titles(response):
    assert response.status_code == 200, response.text
    return {j["title"] for j in response.json()["items"]}


def search(client, world, **params):
    return client.get("/jobs", params=params, headers=world["student"])


# ------------------------------------------------------------------ create
def test_company_creates_job_with_defaults(client, company_headers):
    r = client.post("/jobs", json=job_body(skills=["python", "PYTHON", "sql"]), headers=company_headers)
    assert r.status_code == 201
    job = r.json()
    assert job["title"] == "Data Analyst" and job["category"] == "internship"
    assert job["posting_date"] == TODAY.isoformat() and job["posted_days_ago"] == 0
    assert job["skills"] == ["Python", "SQL"]
    assert job["contact_email"] == "hr@acme.com"          # defaults to the company's email
    assert job["salary_display"] == "$20–$30/hr" and job["is_expired"] is False
    assert job["company"]["name"] == "Acme Corp" and "email" not in job["company"]


def test_only_companies_can_create_jobs(client, student_headers):
    assert client.post("/jobs", json=job_body()).status_code == 401
    assert client.post("/jobs", json=job_body(), headers=student_headers).status_code == 403


@pytest.mark.parametrize("override", [
    {"salary_min": 50, "salary_max": 40},                       # min above max
    {"deadline": iso(-1)},                                      # already past
    {"deadline": iso(-5), "posting_date": iso(-3)},             # deadline before posting date
    {"posting_date": iso(60)},                                  # posted too far in the future
    {"posting_date": iso(-400), "deadline": iso(1)},            # posted too long ago
    {"deadline": iso(900)},                                     # deadline absurdly far away
    {"salary_max": 5000},                                       # $5000/hr
    {"pay_period": "yearly", "salary_min": 100, "salary_max": 5_000_000},
    {"category": "volunteer"}, {"pay_period": "weekly"},
    {"title": ""}, {"title": "x" * 151}, {"description": "short"}, {"city": "  "},
    {"salary_min": -1}, {"salary_min": "lots"}, {"contact_email": "nope"},
    {"skills": ["<script>"]},
    {"company_id": 99}, {"id": 5},                              # fields the client may not set
])
def test_invalid_job_rejected(client, company_headers, override):
    assert client.post("/jobs", json=job_body(**override), headers=company_headers).status_code == 422


def test_missing_required_fields_rejected(client, company_headers):
    assert client.post("/jobs", json={"title": "Only a title"}, headers=company_headers).status_code == 422


# ------------------------------------------------------------------ my jobs / edit
def test_mine_lists_only_own_jobs_with_applicant_counts(client, db, world):
    ds = world["ids"]["ds_intern"]
    for n in range(3):
        student = models.Student(name=f"S{n}", email=f"s{n}@x.edu", password_hash="x", college="SJSU")
        db.add(student)
        db.flush()
        db.add(models.Application(student_id=student.id, job_id=ds, resume_path="resumes/x.pdf",
                                  applied_at=datetime.now()))
    db.commit()

    r = client.get("/jobs/mine", headers=world["acme"])
    assert r.status_code == 200
    body = r.json()
    assert {j["title"] for j in body["items"]} == {"Data Science Intern", "Software Engineer", "Old Data Role"}
    counts = {j["title"]: j["applicant_count"] for j in body["items"]}
    assert counts == {"Data Science Intern": 3, "Software Engineer": 0, "Old Data Role": 0}
    assert body["total"] == 3
    assert {j["title"] for j in client.get("/jobs/mine", params={"include_expired": False},
                                           headers=world["acme"]).json()["items"]} == {"Data Science Intern", "Software Engineer"}


def test_mine_requires_company(client, student_headers):
    assert client.get("/jobs/mine").status_code == 401
    assert client.get("/jobs/mine", headers=student_headers).status_code == 403


def test_owner_can_edit_job(client, world):
    jid = world["ids"]["swe"]
    r = client.patch(f"/jobs/{jid}", headers=world["acme"], json={
        "title": "Senior Software Engineer", "salary_max": 170000, "skills": ["python", "Rust"],
        "state": "CA", "is_remote": True})
    assert r.status_code == 200
    job = r.json()
    assert job["title"] == "Senior Software Engineer" and job["salary_max"] == 170000
    assert job["skills"] == ["Python", "Rust"] and job["state"] == "CA" and job["is_remote"] is True
    assert job["salary_min"] == 120000                      # untouched fields stay
    # re-sending the same skills must not trip the UNIQUE rule
    assert client.patch(f"/jobs/{jid}", headers=world["acme"], json={"skills": ["Python", "Rust"]}).status_code == 200


def test_edit_can_clear_optional_fields_and_close_a_posting(client, world):
    jid = world["ids"]["swe"]
    client.patch(f"/jobs/{jid}", headers=world["acme"], json={"state": "CA"})
    assert client.patch(f"/jobs/{jid}", headers=world["acme"], json={"state": None}).json()["state"] is None
    # A job posted today cannot get a deadline before today...
    too_early = client.patch(f"/jobs/{jid}", headers=world["acme"], json={"deadline": iso(-1)})
    assert too_early.status_code == 422 and "before posting_date" in too_early.json()["detail"]
    # ...but a job posted earlier can be closed by moving its deadline into the past.
    client.patch(f"/jobs/{jid}", headers=world["acme"], json={"posting_date": iso(-10)})
    closed = client.patch(f"/jobs/{jid}", headers=world["acme"], json={"deadline": iso(-1)})
    assert closed.status_code == 200 and closed.json()["is_expired"] is True


def test_cannot_edit_someone_elses_job_or_a_missing_job(client, world, student_headers):
    jid = world["ids"]["swe"]                               # belongs to Acme
    assert client.patch(f"/jobs/{jid}", headers=world["globex"], json={"title": "Hijacked"}).status_code == 403
    assert client.get(f"/jobs/{jid}", headers=world["student"]).json()["title"] == "Software Engineer"
    assert client.patch("/jobs/99999", headers=world["acme"], json={"title": "X"}).status_code == 404
    assert client.patch(f"/jobs/{jid}", headers=student_headers, json={"title": "X"}).status_code == 403
    assert client.patch(f"/jobs/{jid}", json={"title": "X"}).status_code == 401


@pytest.mark.parametrize("payload", [
    {"salary_max": 100},                    # below the job's existing salary_min of 120000
    {"salary_min": 999999},                 # above existing salary_max
    {"deadline": iso(-400)},                # before the posting date
    {"pay_period": "hourly"},               # 150000/hr is unrealistic
    {"title": None}, {"deadline": None}, {"category": None}, {"is_remote": None},
    {"category": "bogus"}, {"company_id": 2}, {"posting_date": None},
])
def test_invalid_edits_rejected_and_change_nothing(client, world, payload):
    jid = world["ids"]["swe"]
    assert client.patch(f"/jobs/{jid}", headers=world["acme"], json=payload).status_code == 422
    unchanged = client.get(f"/jobs/{jid}", headers=world["acme"]).json()
    assert unchanged["title"] == "Software Engineer" and unchanged["salary_max"] == 150000


# ------------------------------------------------------------------ details
def test_job_details_include_company_profile(client, world):
    r = client.get(f"/jobs/{world['ids']['ds_intern']}", headers=world["student"])
    assert r.status_code == 200
    job = r.json()
    assert job["description"] and job["contact_email"] == "hr@acme.com"
    assert job["skills"] == ["Machine Learning", "Python"]
    assert job["company"]["name"] == "Acme Corp" and job["company"]["location"] == "San Jose"
    assert "email" not in job["company"]                    # login email is never exposed
    assert job["salary_display"] == "$30–$40/hr"


def test_expired_job_still_viewable_and_flagged(client, world):
    job = client.get(f"/jobs/{world['ids']['expired']}", headers=world["student"]).json()
    assert job["is_expired"] is True and job["posted_days_ago"] == 60


def test_yearly_salary_display_and_missing_job(client, world):
    assert client.get(f"/jobs/{world['ids']['swe']}", headers=world["student"]).json()["salary_display"] == "$120,000–$150,000/yr"
    assert client.get("/jobs/99999", headers=world["student"]).status_code == 404
    assert client.get("/jobs/abc", headers=world["student"]).status_code == 422
    assert client.get(f"/jobs/{world['ids']['swe']}").status_code == 401


# ------------------------------------------------------------------ search
def test_search_requires_login(client):
    assert client.get("/jobs").status_code == 401


def test_default_search_hides_expired_and_company_can_search_too(client, world):
    assert titles(search(client, world)) == {"Data Science Intern", "Software Engineer", "Data Analyst Intern",
                                             "Library Assistant", "Marketing Associate"}
    assert client.get("/jobs", headers=world["acme"]).json()["total"] == 5
    assert "Old Data Role" in titles(search(client, world, include_expired=True))


def test_search_by_title_company_and_words(client, world):
    assert titles(search(client, world, q="analyst")) == {"Data Analyst Intern"}
    assert titles(search(client, world, q="GLOBEX")) == {"Data Analyst Intern", "Library Assistant", "Marketing Associate"}
    assert titles(search(client, world, q="acme")) == {"Data Science Intern", "Software Engineer"}
    assert titles(search(client, world, q="data intern")) == {"Data Science Intern", "Data Analyst Intern"}  # every word must match
    assert titles(search(client, world, q="data globex")) == {"Data Analyst Intern"}    # one word in title, one in company
    assert search(client, world, q="nursing").json()["total"] == 0


def test_percent_and_underscore_are_not_wildcards(client, world):
    assert search(client, world, q="%").json()["total"] == 0
    assert search(client, world, q="_").json()["total"] == 0


def test_filter_by_category(client, world):
    assert titles(search(client, world, category="internship")) == {"Data Science Intern", "Data Analyst Intern"}
    both = client.get("/jobs", params=[("category", "full_time"), ("category", "on_campus")], headers=world["student"])
    assert titles(both) == {"Software Engineer", "Library Assistant"}


def test_filter_by_city_ignores_case_and_allows_several(client, world):
    assert titles(search(client, world, city="sunnyvale")) == {"Data Analyst Intern", "Marketing Associate"}
    many = client.get("/jobs", params=[("city", "San Jose"), ("city", "Mountain View")], headers=world["student"])
    assert titles(many) == {"Data Science Intern", "Software Engineer", "Library Assistant"}


def test_filter_by_remote(client, world):
    assert titles(search(client, world, is_remote=True)) == {"Data Science Intern"}
    assert "Data Science Intern" not in titles(search(client, world, is_remote=False))


def test_salary_filter_compares_hourly_and_yearly_fairly(client, world):
    # Top pay >= $28/hr: the $40/hr, $30/hr jobs and the $150k/yr job (about $72/hr)
    assert titles(search(client, world, min_salary=28, salary_unit="hourly")) == \
        {"Data Science Intern", "Data Analyst Intern", "Software Engineer"}
    # Top pay >= $100,000/yr: only the $150k job ($40/hr is only about $83k/yr)
    assert titles(search(client, world, min_salary=100000, salary_unit="yearly")) == {"Software Engineer"}
    assert titles(search(client, world, min_salary=80000, salary_unit="yearly")) == {"Data Science Intern", "Software Engineer"}


def test_min_salary_needs_a_unit(client, world):
    assert search(client, world, min_salary=30).status_code == 422
    assert search(client, world, min_salary=30, salary_unit="weekly").status_code == 422


def test_filter_by_skills_any_and_all(client, world):
    assert titles(search(client, world, skills="python")) == {"Data Science Intern", "Software Engineer", "Data Analyst Intern"}
    two = [("skills", "Python"), ("skills", "sql")]
    assert titles(client.get("/jobs", params=two, headers=world["student"])) == {"Data Science Intern", "Software Engineer", "Data Analyst Intern"}
    assert titles(client.get("/jobs", params=two + [("skills_match", "all")], headers=world["student"])) == {"Data Analyst Intern"}
    assert search(client, world, skills="Welding").json()["total"] == 0
    assert search(client, world, skills_match="some").status_code == 422


def test_filter_by_deadline(client, world):
    assert titles(search(client, world, deadline_before=iso(15))) == {"Data Analyst Intern"}
    assert titles(search(client, world, deadline_after=iso(45))) == {"Software Engineer"}
    assert titles(search(client, world, deadline_after=iso(15), deadline_before=iso(35))) == {"Data Science Intern", "Library Assistant"}


def test_filters_combine_with_and(client, world):
    r = search(client, world, category="internship", city="San Jose", is_remote=True, skills="python",
               min_salary=25, salary_unit="hourly")
    assert titles(r) == {"Data Science Intern"}
    assert search(client, world, category="internship", city="Mountain View").json()["total"] == 0


def test_sorting(client, world):
    def order(**p):
        return [j["title"] for j in search(client, world, **p).json()["items"]]
    assert order(sort="deadline") == ["Data Analyst Intern", "Library Assistant", "Data Science Intern",
                                      "Marketing Associate", "Software Engineer"]
    assert order(sort="salary")[:2] == ["Software Engineer", "Data Science Intern"]   # $150k, then $40/hr (~$83k)


def test_pagination(client, world):
    first = search(client, world, page_size=2, sort="deadline").json()
    assert first["total"] == 5 and first["total_pages"] == 3 and first["page"] == 1
    assert [j["title"] for j in first["items"]] == ["Data Analyst Intern", "Library Assistant"]
    last = search(client, world, page_size=2, page=3, sort="deadline").json()
    assert [j["title"] for j in last["items"]] == ["Software Engineer"]
    assert search(client, world, page_size=2, page=9).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page_size": 0}, {"page_size": 101}, {"category": "bogus"}, {"sort": "random"},
    {"is_remote": "maybe"}, {"min_salary": -5, "salary_unit": "hourly"}, {"deadline_before": "tomorrow"},
    {"q": "x" * 101},
])
def test_bad_search_parameters_rejected(client, world, params):
    assert search(client, world, **params).status_code == 422


def test_search_results_show_summary_fields(client, world):
    job = search(client, world, q="Library").json()["items"][0]
    assert set(job) == {"id", "title", "company", "city", "state", "is_remote", "category", "salary_min",
                        "salary_max", "pay_period", "salary_display", "posting_date", "deadline",
                        "is_expired", "skills"}
    assert job["company"]["name"] == "Globex Inc" and job["category"] == "on_campus"
    assert "description" not in job                          # lists stay light; details have it


# ------------------------------------------------------------------ public company profile
def test_public_company_profile(client, world):
    r = client.get(f"/companies/{world['acme_id']}", headers=world["student"])
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Corp" and "email" not in r.json()
    assert client.get("/companies/99999", headers=world["student"]).status_code == 404
    assert client.get(f"/companies/{world['acme_id']}").status_code == 401


def test_me_route_is_not_swallowed_by_the_id_route(client, world):
    me = client.get("/companies/me", headers=world["acme"])
    assert me.status_code == 200 and me.json()["email"] == "hr@acme.com"
    assert client.get("/companies/me", headers=world["student"]).status_code == 403