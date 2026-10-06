"""
Student profile, company profile, picture upload and reference-data tests.
Run from backend/:   python -m pytest -q
"""
import os
from datetime import date, timedelta

import pytest

from app import config

# Fake image bytes: only the first bytes matter to our "magic byte" check.
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 200


def stored_path(url: str) -> str:
    """Map a '/media/profile_pics/x.png' URL to the file on disk."""
    return os.path.join(config.UPLOAD_DIR, url.removeprefix("/media/"))


# ======================= student: view =======================
def test_new_student_profile_is_mostly_empty(client, student_headers):
    r = client.get("/students/me", headers=student_headers)
    assert r.status_code == 200
    p = r.json()
    assert p["name"] == "Ada Lovelace" and p["email"] == "ada@example.com" and p["college"] == "SJSU"
    assert p["skills"] == [] and p["experience"] == []
    assert p["cgpa"] is None and p["profile_pic_url"] is None
    assert "password" not in r.text and "hash" not in r.text


def test_profile_requires_student_login(client, company_headers):
    assert client.get("/students/me").status_code == 401
    assert client.get("/students/me", headers=company_headers).status_code == 403
    assert client.patch("/students/me", json={"city": "X"}, headers=company_headers).status_code == 403


# ======================= student: update =======================
FULL_UPDATE = {
    "name": "  Ada King  ", "date_of_birth": "2002-05-17", "city": "San Jose", "state": "CA",
    "country": "United States", "career_objective": "Build data platforms.", "college": "San Jose State University",
    "degree": "MS", "major": "data science", "graduation_year": 2027, "cgpa": 3.756,
    "phone": "(408) 555-0123",
}


def test_full_update_persists_and_cleans_values(client, student_headers):
    r = client.patch("/students/me", json=FULL_UPDATE, headers=student_headers)
    assert r.status_code == 200
    p = client.get("/students/me", headers=student_headers).json()
    assert p["name"] == "Ada King"            # trimmed
    assert p["major"] == "Data Science"       # matched to the shared spelling
    assert p["cgpa"] == 3.76                  # rounded to 2 decimals
    assert p["date_of_birth"] == "2002-05-17" and p["graduation_year"] == 2027
    assert p["phone"] == "(408) 555-0123" and p["city"] == "San Jose"


def test_partial_update_leaves_other_fields_alone(client, student_headers):
    client.patch("/students/me", json=FULL_UPDATE, headers=student_headers)
    client.patch("/students/me", json={"city": "Sunnyvale"}, headers=student_headers)
    p = client.get("/students/me", headers=student_headers).json()
    assert p["city"] == "Sunnyvale" and p["degree"] == "MS" and p["cgpa"] == 3.76


def test_optional_fields_can_be_cleared_with_null_or_blank(client, student_headers):
    client.patch("/students/me", json=FULL_UPDATE, headers=student_headers)
    r = client.patch("/students/me", json={"city": None, "phone": "  ", "cgpa": None}, headers=student_headers)
    assert r.status_code == 200
    p = r.json()
    assert p["city"] is None and p["phone"] is None and p["cgpa"] is None


@pytest.mark.parametrize("payload", [
    {"cgpa": 4.5}, {"cgpa": -1}, {"cgpa": "abc"},
    {"graduation_year": 1800}, {"graduation_year": 3000},
    {"date_of_birth": (date.today() + timedelta(days=5)).isoformat()},
    {"date_of_birth": (date.today() - timedelta(days=365 * 10)).isoformat()},   # age 10
    {"date_of_birth": "1800-01-01"},
    {"phone": "call me"}, {"phone": "123"},
    {"email": "not-an-email"},
    {"name": None}, {"name": "   "}, {"college": None}, {"email": None},
    {"city": "x" * 101},
    {"password_hash": "hacked"}, {"id": 99}, {"profile_pic_path": "/etc/passwd"},   # unknown fields refused
])
def test_invalid_updates_are_rejected(client, student_headers, payload):
    assert client.patch("/students/me", json=payload, headers=student_headers).status_code == 422


def test_rejected_update_changes_nothing(client, student_headers):
    client.patch("/students/me", json={"city": "San Jose", "cgpa": 9}, headers=student_headers)
    assert client.get("/students/me", headers=student_headers).json()["city"] is None


# ---------- email changes ----------
def test_email_change_is_normalized_and_usable_for_login(client, student_headers):
    r = client.patch("/students/me", json={"email": "New.Ada@Example.com"}, headers=student_headers)
    assert r.status_code == 200 and r.json()["email"] == "new.ada@example.com"
    login = client.post("/auth/login", json={"email": "new.ada@example.com", "password": "Secret123", "role": "student"})
    assert login.status_code == 200
    # the old token still works because it identifies the account by id, not email
    assert client.get("/students/me", headers=student_headers).status_code == 200


def test_email_change_to_someone_elses_email_is_409(client, student_headers):
    client.post("/auth/student/signup", json={"name": "Bob", "email": "bob@example.com",
                                              "password": "Secret123", "college": "SJSU"})
    r = client.patch("/students/me", json={"email": "BOB@example.com"}, headers=student_headers)
    assert r.status_code == 409


def test_resending_own_email_is_fine(client, student_headers):
    assert client.patch("/students/me", json={"email": "ada@example.com"}, headers=student_headers).status_code == 200


# ---------- skills ----------
def test_skills_are_canonicalized_deduplicated_and_sorted(client, student_headers):
    r = client.patch("/students/me", json={"skills": ["python", "PYTHON", " machine   learning ", "Rust", "c++"]},
                     headers=student_headers)
    assert r.status_code == 200
    assert r.json()["skills"] == ["C++", "Machine Learning", "Python", "Rust"]


def test_skills_are_replaced_not_appended(client, student_headers):
    client.patch("/students/me", json={"skills": ["Python", "SQL", "Rust"]}, headers=student_headers)
    r = client.patch("/students/me", json={"skills": ["python", "Go"]}, headers=student_headers)  # keeps Python, drops SQL/Rust
    assert r.json()["skills"] == ["Go", "Python"]
    # sending the identical list again must not trip the UNIQUE (student, skill) rule
    r = client.patch("/students/me", json={"skills": ["Python", "Go"]}, headers=student_headers)
    assert r.status_code == 200 and r.json()["skills"] == ["Go", "Python"]


def test_empty_skill_list_clears_skills_but_omitting_keeps_them(client, student_headers):
    client.patch("/students/me", json={"skills": ["Python"]}, headers=student_headers)
    assert client.patch("/students/me", json={"city": "San Jose"}, headers=student_headers).json()["skills"] == ["Python"]
    assert client.patch("/students/me", json={"skills": []}, headers=student_headers).json()["skills"] == []


@pytest.mark.parametrize("skills", [["<script>alert(1)</script>"], ["x" * 51], [f"Skill{i}" for i in range(31)], [123]])
def test_bad_skills_rejected(client, student_headers, skills):
    assert client.patch("/students/me", json={"skills": skills}, headers=student_headers).status_code == 422


# ---------- experience ----------
EXP = [
    {"title": "Data Intern", "company": "Everlaw", "start_date": "2025-06-01", "end_date": "2025-08-30",
     "description": "Analyzed go-to-market data."},
    {"title": "TA", "company": "SJSU", "start_date": "2026-01-15", "end_date": None},
]


def test_experience_is_saved_newest_first_and_replaced(client, student_headers):
    r = client.patch("/students/me", json={"experience": EXP}, headers=student_headers)
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()["experience"]]
    assert titles == ["TA", "Data Intern"] and r.json()["experience"][0]["end_date"] is None
    r = client.patch("/students/me", json={"experience": [EXP[0]]}, headers=student_headers)
    assert [e["title"] for e in r.json()["experience"]] == ["Data Intern"]


def test_bad_experience_rejected(client, student_headers):
    backwards = {"title": "X", "company": "Y", "start_date": "2026-01-01", "end_date": "2025-01-01"}
    assert client.patch("/students/me", json={"experience": [backwards]}, headers=student_headers).status_code == 422
    assert client.patch("/students/me", json={"experience": [{"company": "Y"}]}, headers=student_headers).status_code == 422
    too_many = [{"title": "T", "company": "C"}] * 21
    assert client.patch("/students/me", json={"experience": too_many}, headers=student_headers).status_code == 422


# ======================= student: picture =======================
def test_upload_picture_and_serve_it(client, student_headers):
    r = client.post("/students/me/profile-picture", files={"file": ("me.png", PNG, "image/png")}, headers=student_headers)
    assert r.status_code == 200
    url = r.json()["profile_pic_url"]
    assert url.startswith("/media/profile_pics/student_1_") and url.endswith(".png")
    assert client.get("/students/me", headers=student_headers).json()["profile_pic_url"] == url
    assert os.path.exists(stored_path(url))
    served = client.get(url)                       # public: no token needed
    assert served.status_code == 200 and served.content == PNG


def test_new_picture_replaces_and_deletes_the_old_file(client, student_headers):
    first = client.post("/students/me/profile-picture", files={"file": ("a.png", PNG, "image/png")},
                        headers=student_headers).json()["profile_pic_url"]
    second = client.post("/students/me/profile-picture", files={"file": ("b.jpg", JPEG, "image/jpeg")},
                         headers=student_headers).json()["profile_pic_url"]
    assert first != second and second.endswith(".jpg")
    assert not os.path.exists(stored_path(first)) and os.path.exists(stored_path(second))


def test_webp_is_accepted(client, student_headers):
    r = client.post("/students/me/profile-picture", files={"file": ("a.webp", WEBP, "image/webp")}, headers=student_headers)
    assert r.status_code == 200 and r.json()["profile_pic_url"].endswith(".webp")


@pytest.mark.parametrize("name,content,expected", [
    ("evil.png", b"<?php echo 1; ?>", 415),                                    # wrong bytes, fake .png name
    ("notes.txt", b"hello world", 415),
    ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", 415),
    ("empty.png", b"", 400),
    ("huge.png", PNG + b"0" * (2 * 1024 * 1024), 413),
], ids=["php-bytes-named-png", "text-file", "svg-with-script", "empty-file", "over-2mb"])
# ids=[...] gives each case a short name. Without it pytest builds the name from the
# file bytes, and the 2 MB case made a name so long that Windows refused it.
def test_bad_uploads_rejected(client, student_headers, name, content, expected):
    r = client.post("/students/me/profile-picture", files={"file": (name, content, "image/png")}, headers=student_headers)
    assert r.status_code == expected
    assert client.get("/students/me", headers=student_headers).json()["profile_pic_url"] is None


def test_upload_filename_cannot_escape_the_uploads_folder(client, student_headers):
    r = client.post("/students/me/profile-picture", files={"file": ("../../evil.png", PNG, "image/png")}, headers=student_headers)
    assert r.status_code == 200
    assert "evil" not in r.json()["profile_pic_url"]     # our own generated name is used instead


def test_upload_requires_student_login(client, company_headers):
    files = {"file": ("a.png", PNG, "image/png")}
    assert client.post("/students/me/profile-picture", files=files).status_code == 401
    assert client.post("/students/me/profile-picture", files=files, headers=company_headers).status_code == 403


def test_resumes_folder_is_not_publicly_served(client):
    os.makedirs(os.path.join(config.UPLOAD_DIR, "resumes"), exist_ok=True)
    with open(os.path.join(config.UPLOAD_DIR, "resumes", "secret.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 private")
    assert client.get("/media/resumes/secret.pdf").status_code == 404
    assert client.get("/media/profile_pics/../resumes/secret.pdf").status_code in (400, 404)
    assert client.get("/uploads/resumes/secret.pdf").status_code == 404


# ======================= company =======================
def test_new_company_profile(client, company_headers):
    p = client.get("/companies/me", headers=company_headers).json()
    assert p["name"] == "Acme Corp" and p["location"] == "San Jose" and p["email"] == "hr@acme.com"
    assert p["description"] is None and p["profile_pic_url"] is None


def test_company_endpoints_require_company_login(client, student_headers):
    assert client.get("/companies/me").status_code == 401
    assert client.get("/companies/me", headers=student_headers).status_code == 403
    assert client.patch("/companies/me", json={"name": "X"}, headers=student_headers).status_code == 403


def test_company_update(client, company_headers):
    payload = {"name": "Acme Robotics", "location": "Sunnyvale", "state": "CA", "industry": "Robotics",
               "description": "We build robots.", "contact_email": "Careers@Acme.com",
               "contact_phone": "+1 408-555-0100", "website": "https://www.acme.com"}
    r = client.patch("/companies/me", json=payload, headers=company_headers)
    assert r.status_code == 200
    p = client.get("/companies/me", headers=company_headers).json()
    assert p["name"] == "Acme Robotics" and p["location"] == "Sunnyvale"
    assert p["contact_email"] == "careers@acme.com" and p["website"] == "https://www.acme.com"
    # partial update + clearing
    p = client.patch("/companies/me", json={"description": "", "website": None}, headers=company_headers).json()
    assert p["description"] is None and p["website"] is None and p["name"] == "Acme Robotics"


@pytest.mark.parametrize("payload", [
    {"website": "ftp://acme.com"}, {"website": "javascript:alert(1)"}, {"website": "acme.com"},
    {"contact_email": "nope"}, {"contact_phone": "abc"},
    {"name": None}, {"location": None}, {"location": "  "}, {"email": None},
    {"description": "x" * 3001},
    {"password_hash": "x"}, {"city": "should use location"},
])
def test_invalid_company_updates_rejected(client, company_headers, payload):
    assert client.patch("/companies/me", json=payload, headers=company_headers).status_code == 422


def test_company_email_conflict(client, company_headers):
    client.post("/auth/company/signup", json={"name": "Other", "email": "other@corp.com",
                                              "password": "Secret123", "location": "San Jose"})
    assert client.patch("/companies/me", json={"email": "other@corp.com"}, headers=company_headers).status_code == 409


def test_company_logo_upload(client, company_headers):
    r = client.post("/companies/me/profile-picture", files={"file": ("logo.png", PNG, "image/png")}, headers=company_headers)
    assert r.status_code == 200
    url = r.json()["profile_pic_url"]
    assert "company_1_" in url and client.get(url).status_code == 200
    assert client.get("/companies/me", headers=company_headers).json()["profile_pic_url"] == url


# ======================= reference data =======================
def test_meta_options_is_public_and_matches_shared_vocabulary(client):
    r = client.get("/meta/options")
    assert r.status_code == 200
    body = r.json()
    assert body["cities"] == ["San Jose", "Sunnyvale", "Mountain View"]
    assert body["job_categories"] == ["full_time", "part_time", "on_campus", "internship"]
    assert body["application_statuses"] == ["Pending", "Reviewed", "Declined"]
    assert "Data Science" in body["majors"] and "Python" in body["skills_by_area"]["programming"]