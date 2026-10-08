"""
Student preferences: read, save, replace, clear, validation and privacy.
Run from backend/:   python -m pytest -q
"""
import pytest

from app import models
from app.services.preferences import get_student_preferences, to_preferences_out

URL = "/students/me/preferences"

FULL = {
    "preferred_categories": ["internship", "part_time"],
    "preferred_cities": ["San Jose", "Sunnyvale"],
    "preferred_roles": ["Data Analyst", "Data Science"],
    "min_hourly_rate": 25,
    "open_to_remote": False,
    "event_interests": ["Career Fair", "Tech Talk"],
}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ===================================================================== reading
def test_a_new_student_has_no_saved_preferences(client, student_headers):
    r = client.get(URL, headers=student_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is False and body["updated_at"] is None
    assert body["preferred_categories"] == [] and body["preferred_cities"] == []
    assert body["preferred_roles"] == [] and body["event_interests"] == [] and body["min_hourly_rate"] is None


def test_preferences_require_a_student_login(client, company_headers):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json=FULL).status_code == 401
    assert client.delete(URL).status_code == 401
    assert client.get(URL, headers=company_headers).status_code == 403
    assert client.put(URL, json=FULL, headers=company_headers).status_code == 403
    assert client.delete(URL, headers=company_headers).status_code == 403


# ===================================================================== saving
def test_save_then_read_back(client, student_headers):
    r = client.put(URL, json=FULL, headers=student_headers)
    assert r.status_code == 200
    saved = r.json()
    assert saved["saved"] is True and saved["updated_at"]
    again = client.get(URL, headers=student_headers).json()
    for key, value in FULL.items():
        assert again[key] == value, key


def test_saving_replaces_instead_of_merging(client, student_headers):
    client.put(URL, json=FULL, headers=student_headers)
    r = client.put(URL, json={"preferred_cities": ["Mountain View"]}, headers=student_headers)
    body = r.json()
    assert body["preferred_cities"] == ["Mountain View"]
    assert body["preferred_categories"] == [] and body["preferred_roles"] == []        # not carried over
    assert body["min_hourly_rate"] is None and body["open_to_remote"] is True           # back to defaults
    assert client.get(URL, headers=student_headers).json() == body


def test_an_empty_save_counts_as_saved(client, student_headers):
    body = client.put(URL, json={}, headers=student_headers).json()
    assert body["saved"] is True and body["open_to_remote"] is True and body["preferred_cities"] == []


def test_values_are_cleaned_and_use_the_shared_spelling(client, student_headers):
    r = client.put(URL, headers=student_headers, json={
        "preferred_categories": ["internship", "internship", "full_time"],
        "preferred_cities": ["  san   jose ", "SAN JOSE", "mountain view", "Palo Alto"],
        "preferred_roles": ["Data Analyst", "data analyst", " Software  Engineer"],
        "event_interests": ["career fair", "Career Fair", ""],
    })
    body = r.json()
    assert body["preferred_categories"] == ["internship", "full_time"]
    assert body["preferred_cities"] == ["San Jose", "Mountain View", "Palo Alto"]    # known cities get the shared spelling
    assert body["preferred_roles"] == ["Data Analyst", "Software Engineer"]
    assert body["event_interests"] == ["career fair"]


def test_one_row_per_student_no_matter_how_often_you_save(client, db, student_headers):
    for rate in (10, 20, 30):
        client.put(URL, json={"min_hourly_rate": rate}, headers=student_headers)
    assert db.query(models.StudentPreference).count() == 1
    assert client.get(URL, headers=student_headers).json()["min_hourly_rate"] == 30


@pytest.mark.parametrize("payload", [
    {"preferred_categories": ["volunteer"]}, {"preferred_categories": ["Internship"]}, {"preferred_categories": "internship"},
    {"preferred_cities": [f"City{i}" for i in range(11)]}, {"preferred_cities": ["<script>"]}, {"preferred_cities": ["x" * 101]},
    {"preferred_cities": [5]}, {"preferred_cities": "San Jose"},
    {"preferred_roles": ["role; DROP TABLE"]}, {"preferred_roles": [f"Role{i}" for i in range(11)]},
    {"event_interests": ["<b>"]}, {"event_interests": [f"Interest{i}" for i in range(11)]},
    {"min_hourly_rate": -1}, {"min_hourly_rate": 501}, {"min_hourly_rate": "lots"}, {"min_hourly_rate": 12.5},
    {"open_to_remote": "maybe"},
    {"student_id": 2}, {"saved": True}, {"updated_at": "2026-01-01T00:00:00"},       # fields the client may not set
], ids=["bad-category", "wrong-case-category", "category-string", "11-cities", "script-city", "long-city",
        "number-city", "city-string", "sql-role", "11-roles", "html-interest", "11-interests",
        "negative-rate", "rate-501", "rate-text", "rate-fraction", "remote-maybe",
        "student-id", "saved", "updated-at"])
def test_invalid_preferences_rejected_and_nothing_is_saved(client, student_headers, payload):
    assert client.put(URL, json=payload, headers=student_headers).status_code == 422
    assert client.get(URL, headers=student_headers).json()["saved"] is False


def test_rate_limits_are_inclusive(client, student_headers):
    assert client.put(URL, json={"min_hourly_rate": 0}, headers=student_headers).json()["min_hourly_rate"] == 0
    assert client.put(URL, json={"min_hourly_rate": 500}, headers=student_headers).json()["min_hourly_rate"] == 500
    assert client.put(URL, json={"min_hourly_rate": None}, headers=student_headers).json()["min_hourly_rate"] is None


# ===================================================================== clearing
def test_delete_forgets_preferences_and_is_safe_to_repeat(client, student_headers):
    client.put(URL, json=FULL, headers=student_headers)
    assert client.delete(URL, headers=student_headers).status_code == 204
    assert client.get(URL, headers=student_headers).json()["saved"] is False
    assert client.delete(URL, headers=student_headers).status_code == 204         # nothing left: still fine
    assert client.put(URL, json=FULL, headers=student_headers).json()["saved"] is True   # can save again


# ===================================================================== privacy
def test_students_only_ever_see_their_own_preferences(client):
    a = bearer(client.post("/auth/student/signup", json={"name": "Ann", "email": "ann@x.com", "password": "Secret123", "college": "SJSU"}).json()["access_token"])
    b = bearer(client.post("/auth/student/signup", json={"name": "Ben", "email": "ben@x.com", "password": "Secret123", "college": "SJSU"}).json()["access_token"])
    client.put(URL, json={"preferred_cities": ["Sunnyvale"], "min_hourly_rate": 40}, headers=a)
    assert client.get(URL, headers=b).json()["saved"] is False
    client.delete(URL, headers=b)                                                  # Ben clearing his own...
    assert client.get(URL, headers=a).json()["min_hourly_rate"] == 40              # ...does not touch Ann's


# ===================================================================== service used by the assistant
def test_service_functions_match_the_api(client, db, student_headers):
    student_id = client.get("/students/me", headers=student_headers).json()["id"]
    assert get_student_preferences(db, student_id) is None
    assert to_preferences_out(None).saved is False
    client.put(URL, json=FULL, headers=student_headers)
    db.expire_all()
    row = get_student_preferences(db, student_id)
    out = to_preferences_out(row)
    assert out.saved is True and out.preferred_cities == ["San Jose", "Sunnyvale"]
    assert [c.value for c in out.preferred_categories] == ["internship", "part_time"]


def test_rows_written_by_the_seed_script_can_be_read(client, db, student_headers):
    # The seed stores plain JSON lists, and may leave open_to_remote or lists empty.
    student_id = client.get("/students/me", headers=student_headers).json()["id"]
    db.add(models.StudentPreference(student_id=student_id, preferred_categories=["internship", "not-a-category"],
                                    preferred_cities=["San Jose"], preferred_roles=None, min_hourly_rate=25,
                                    open_to_remote=None, event_interests=["Career Fair"]))
    db.commit()
    body = client.get(URL, headers=student_headers).json()
    assert body["saved"] is True and body["preferred_categories"] == ["internship"]      # junk value ignored
    assert body["preferred_roles"] == [] and body["open_to_remote"] is True and body["min_hourly_rate"] == 25


# ===================================================================== form suggestions
def test_meta_options_offer_suggestions_for_the_form(client):
    body = client.get("/meta/options").json()
    assert "Career Fair" in body["event_interest_options"]
    assert "Data Analyst" in body["role_suggestions"] and body["role_suggestions"] == sorted(body["role_suggestions"])
    assert body["cities"] == ["San Jose", "Sunnyvale", "Mountain View"]