"""
Shared test setup. pytest loads this file BEFORE the test files.

Safety rule enforced here: the tests never touch a real MongoDB. Each test gets its own in-memory database
(mongomock) with the same indexes as the real one, and MONGO_URL is pointed at an address that cannot work,
so a test that forgot to use the fixture fails at once instead of reaching a real database.
"""
import os

os.environ["MONGO_URL"] = "mongodb://127.0.0.1:1"      # nothing listens on port 1
os.environ["MONGO_TIMEOUT_MS"] = "200"                  # so a test that forgot the fixture fails fast, not after 5 s

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mongomock import gridfs as mongomock_gridfs  # noqa: E402

from app import mongo  # noqa: E402
from app.main import app  # noqa: E402

mongomock_gridfs.enable_gridfs_integration()     # lets gridfs.GridFS work on the in-memory database

STUDENT = {"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123", "college": "SJSU"}
COMPANY = {"name": "Acme Corp", "email": "hr@acme.com", "password": "Secret123", "location": "San Jose"}


@pytest.fixture()
def mongo_db():
    """A fresh, empty in-memory database with the real indexes, plugged in as THE database for this test."""
    database = mongomock.MongoClient()["p06_test"]
    mongo.ensure_indexes(database)
    mongo.use_database(database)
    yield database
    mongo.use_database(None)


@pytest.fixture()
def client(mongo_db):
    """A test client wired to that in-memory database."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(mongo_db):
    """Direct database access for tests that need documents the API would refuse to create
    (e.g. an already-expired job). See tests/factories.py."""
    return mongo_db


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