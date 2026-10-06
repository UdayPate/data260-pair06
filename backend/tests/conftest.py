"""
Shared test setup. pytest loads this file BEFORE the test files.

Two safety rules enforced here:
  1. DATABASE_URL is forced to in-memory SQLite, so tests can never touch your MySQL data.
  2. UPLOAD_DIR is forced to a temporary folder, so tests never write into backend/uploads.
Environment variables set here win over anything in your .env file.
"""
import atexit
import os
import shutil
import tempfile

_TMP_UPLOADS = tempfile.mkdtemp(prefix="handshake_test_uploads_")
os.environ["UPLOAD_DIR"] = _TMP_UPLOADS
os.environ["DATABASE_URL"] = "sqlite://"
atexit.register(shutil.rmtree, _TMP_UPLOADS, ignore_errors=True)

import pytest  # noqa: E402  (must come after the environment is set)
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

STUDENT = {"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123", "college": "SJSU"}
COMPANY = {"name": "Acme Corp", "email": "hr@acme.com", "password": "Secret123", "location": "San Jose"}


@pytest.fixture()
def client():
    """A test client wired to a fresh, empty in-memory database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def student_headers(client):
    """Authorization header for a freshly signed-up student."""
    token = client.post("/auth/student/signup", json=STUDENT).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def company_headers(client):
    """Authorization header for a freshly signed-up company."""
    token = client.post("/auth/company/signup", json=COMPANY).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}