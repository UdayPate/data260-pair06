"""
Authentication tests. Run from the backend/ folder:
    python -m pytest -q

The `client` fixture (see conftest.py) uses a throwaway in-memory SQLite database,
NOT your MySQL one, so tests never touch the seeded data.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends

from app.config import JWT_ALGORITHM, JWT_SECRET
from app.core.deps import require_company, require_student
from app.core.security import create_access_token, hash_password, verify_password
from app.core.sessions import create_session
from app.main import app
from app.mongo import Doc


# Two tiny endpoints that exist only in tests, to prove the role guards work.
@app.get("/_test/student-only")
def _student_only(student: Doc = Depends(require_student)):
    return {"id": student.id}


@app.get("/_test/company-only")
def _company_only(company: Doc = Depends(require_company)):
    return {"id": company.id}


STUDENT = {"name": "Ada Lovelace", "email": "Ada@Example.com", "password": "Secret123", "college": "SJSU"}
COMPANY = {"name": "Acme Corp", "email": "hr@acme.com", "password": "Secret123", "location": "San Jose"}


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- password hashing ----------
def test_password_is_hashed_and_verifiable():
    hashed = hash_password("Secret123")
    assert hashed != "Secret123"
    assert hashed.startswith("$2")  # bcrypt marker
    assert verify_password("Secret123", hashed)
    assert not verify_password("secret123", hashed)
    assert not verify_password("x", "not-a-valid-hash")  # never raises


# ---------- signup ----------
def test_student_signup_returns_token_and_no_password(client):
    r = client.post("/auth/student/signup", json=STUDENT)
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "student" and body["name"] == "Ada Lovelace" and body["access_token"]
    assert "password" not in r.text and "hash" not in r.text


def test_company_signup(client):
    r = client.post("/auth/company/signup", json=COMPANY)
    assert r.status_code == 201 and r.json()["role"] == "company"


def test_duplicate_email_is_rejected_case_insensitively(client):
    assert client.post("/auth/student/signup", json=STUDENT).status_code == 201
    again = {**STUDENT, "email": "ADA@example.COM"}
    assert client.post("/auth/student/signup", json=again).status_code == 409


@pytest.mark.parametrize("bad_password", ["short1", "allletters", "12345678", "a1" * 40])
def test_weak_or_too_long_password_rejected(client, bad_password):
    r = client.post("/auth/student/signup", json={**STUDENT, "password": bad_password})
    assert r.status_code == 422


@pytest.mark.parametrize("field,value", [("email", "not-an-email"), ("name", "   "), ("college", "")])
def test_invalid_fields_rejected(client, field, value):
    assert client.post("/auth/student/signup", json={**STUDENT, field: value}).status_code == 422


def test_missing_fields_rejected(client):
    assert client.post("/auth/student/signup", json={"email": "a@b.com"}).status_code == 422


# ---------- login ----------
def test_login_success(client):
    client.post("/auth/student/signup", json=STUDENT)
    r = client.post("/auth/login", json={"email": "ada@example.com", "password": "Secret123", "role": "student"})
    assert r.status_code == 200 and r.json()["access_token"]


def test_login_wrong_password_and_unknown_email_look_identical(client):
    client.post("/auth/student/signup", json=STUDENT)
    wrong_pw = client.post("/auth/login", json={"email": "ada@example.com", "password": "Nope12345", "role": "student"})
    unknown = client.post("/auth/login", json={"email": "ghost@example.com", "password": "Nope12345", "role": "student"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


def test_login_with_wrong_role_fails(client):
    client.post("/auth/student/signup", json=STUDENT)
    r = client.post("/auth/login", json={"email": "ada@example.com", "password": "Secret123", "role": "company"})
    assert r.status_code == 401


# ---------- tokens, /me, logout ----------
def test_me_and_logout_with_valid_token(client):
    token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    me = client.get("/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json() == {"role": "student", "id": 1, "name": "Ada Lovelace", "email": "ada@example.com"}
    assert client.post("/auth/logout", headers=auth_header(token)).status_code == 200


def test_missing_or_garbage_token_is_401(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=auth_header("garbage")).status_code == 401


def _session_id(db):
    """The id of the one session the signup created."""
    return db.sessions.find_one()["_id"]


def test_expired_token_is_401(client, db):
    client.post("/auth/student/signup", json=STUDENT)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({"sub": "1", "role": "student", "jti": _session_id(db), "exp": past},
                         JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert client.get("/auth/me", headers=auth_header(expired)).status_code == 401


def test_token_signed_with_wrong_secret_is_401(client, db):
    client.post("/auth/student/signup", json=STUDENT)
    forged = jwt.encode({"sub": "1", "role": "student", "jti": _session_id(db),
                         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "some-other-secret-that-is-long-enough-123", algorithm=JWT_ALGORITHM)
    assert client.get("/auth/me", headers=auth_header(forged)).status_code == 401


def test_token_for_deleted_account_is_401(client, db):
    # a real session and a correctly signed token, but the account (id 999) does not exist
    token = create_access_token(999, "student", create_session(db, "student", 999))
    r = client.get("/auth/me", headers=auth_header(token))
    assert r.status_code == 401 and "no longer exists" in r.json()["detail"]


# ---------- sessions (Lab 2) ----------
def test_token_without_a_session_is_401(client, db):
    client.post("/auth/student/signup", json=STUDENT)
    no_jti = jwt.encode({"sub": "1", "role": "student", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        JWT_SECRET, algorithm=JWT_ALGORITHM)
    unknown = create_access_token(1, "student", "a-session-that-does-not-exist")
    assert client.get("/auth/me", headers=auth_header(no_jti)).status_code == 401
    assert client.get("/auth/me", headers=auth_header(unknown)).status_code == 401


def test_signup_and_login_each_create_a_session_that_lasts_eight_hours(client, db):
    client.post("/auth/student/signup", json=STUDENT)
    client.post("/auth/login", json={"email": "ada@example.com", "password": "Secret123", "role": "student"})
    sessions = list(db.sessions.find())
    assert len(sessions) == 2
    for s in sessions:
        assert s["role"] == "student" and s["user_id"] == 1
        assert s["expires_at"] - s["created_at"] == timedelta(hours=8)


def test_logout_ends_that_session_only(client, db):
    first = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    second = client.post("/auth/login", json={"email": "ada@example.com", "password": "Secret123",
                                              "role": "student"}).json()["access_token"]
    assert client.get("/auth/me", headers=auth_header(first)).status_code == 200
    assert client.post("/auth/logout", headers=auth_header(first)).status_code == 200
    assert client.get("/auth/me", headers=auth_header(first)).status_code == 401      # the signed-out token is dead...
    assert client.post("/auth/logout", headers=auth_header(first)).status_code == 401
    assert client.get("/auth/me", headers=auth_header(second)).status_code == 200     # ...the other login is not
    assert db.sessions.count_documents({}) == 1


def test_an_expired_session_is_refused_even_before_mongodb_deletes_it(client, db):
    token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    db.sessions.update_one({}, {"$set": {"expires_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)}})
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401      # MongoDB's TTL clock runs only about once a minute


def test_a_session_cannot_be_used_for_the_other_role_or_another_user(client, db):
    s_token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    c_token = client.post("/auth/company/signup", json=COMPANY).json()["access_token"]
    student_session = db.sessions.find_one({"role": "student"})["_id"]
    # a company token that borrows the student's session id, and a student token for someone else's id
    mixed = create_access_token(1, "company", student_session)
    other_user = create_access_token(2, "student", student_session)
    assert client.get("/auth/me", headers=auth_header(mixed)).status_code == 401
    assert client.get("/auth/me", headers=auth_header(other_user)).status_code == 401
    assert client.get("/auth/me", headers=auth_header(s_token)).status_code == 200


def test_sessions_collection_has_the_expiry_index(client, db):
    info = db.sessions.index_information()
    assert info["expires_at_1"]["expireAfterSeconds"] == 0       # MongoDB deletes a session when expires_at passes


def test_signup_login_and_logout_are_written_to_the_activity_log(client, db):
    token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    client.post("/auth/login", json={"email": "ada@example.com", "password": "Secret123", "role": "student"})
    client.post("/auth/logout", headers=auth_header(token))
    actions = [(a["actor_role"], a["actor_id"], a["action"]) for a in db.activity_logs.find().sort("at", 1)]
    assert actions == [("student", 1, "signup"), ("student", 1, "login"), ("student", 1, "logout")]


# ---------- role guards ----------
def test_role_guards(client):
    s_token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    c_token = client.post("/auth/company/signup", json=COMPANY).json()["access_token"]

    assert client.get("/_test/student-only", headers=auth_header(s_token)).status_code == 200
    assert client.get("/_test/student-only", headers=auth_header(c_token)).status_code == 403
    assert client.get("/_test/company-only", headers=auth_header(c_token)).status_code == 200
    assert client.get("/_test/company-only", headers=auth_header(s_token)).status_code == 403
    assert client.get("/_test/student-only").status_code == 401


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "pair": "06"}