"""
Lab 2, phase 1: the backend is split into six services (Student, Company, Job, Application, Event,
AI Assistant). These tests check the split itself:

  * every endpoint of the single Lab 1 app belongs to exactly ONE service (none lost, none shared);
  * every service answers GET /health and says which service it is;
  * each Dockerfile matches the ports in app/config.py and points at real files;
  * the services share one login system: a token from the Student service works on the others,
    and the role rules (403) still hold when the endpoints live in different services.

They run on in-memory SQLite like all the other tests. No Docker is needed.
"""
import importlib
import itertools
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import PAIR_STR, SERVICE_PORTS
from app.database import get_db
from app.main import app as single_app
from services.common import routes_of

KEYS = list(SERVICE_PORTS)          # student, company, job, application, event, assistant
BACKEND = Path(__file__).resolve().parents[1]
# Every FastAPI app has these; they are not Handshake endpoints.
BUILT_IN = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/health"}
# test_auth.py adds two throw-away routes under /_test/ to the single app while the tests run.
TEST_ONLY_PREFIX = "/_test/"

STUDENT = {"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123", "college": "SJSU"}
COMPANY = {"name": "Acme Corp", "email": "hr@acme.com", "password": "Secret123", "location": "San Jose"}


def service_app(key):
    return importlib.import_module(f"services.{key}.main").app


def endpoints(app):
    """{(METHOD, path)} of the real endpoints of an app."""
    return {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods
            if m not in ("HEAD", "OPTIONS") and r.path not in BUILT_IN and not r.path.startswith(TEST_ONLY_PREFIX)}


# ---------------- the split is complete and has no overlap ----------------
def test_six_services_with_the_pair_ports():
    assert KEYS == ["student", "company", "job", "application", "event", "assistant"]
    assert list(SERVICE_PORTS.values()) == [9062, 9063, 9064, 9065, 9066, 9067]


def test_every_lab1_endpoint_belongs_to_exactly_one_service():
    everything = endpoints(single_app)
    assert len(everything) == 40
    owned = {key: endpoints(service_app(key)) for key in KEYS}
    assert set().union(*owned.values()) == everything             # nothing lost, nothing invented
    for a, b in itertools.combinations(KEYS, 2):
        assert not owned[a] & owned[b], f"{a} and {b} both serve {owned[a] & owned[b]}"


@pytest.mark.parametrize("key, expected", [
    ("student", {("POST", "/auth/student/signup"), ("POST", "/auth/login"), ("POST", "/auth/logout"),
                 ("GET", "/auth/me"), ("GET", "/students"), ("GET", "/students/me")}),
    ("company", {("POST", "/auth/company/signup"), ("GET", "/companies/me")}),
    ("job", {("GET", "/jobs"), ("POST", "/jobs"), ("GET", "/jobs/mine"), ("GET", "/jobs/{job_id}"),
             ("GET", "/meta/options")}),
    ("application", {("POST", "/jobs/{job_id}/apply"), ("GET", "/applications/mine"),
                     ("GET", "/jobs/{job_id}/applications")}),
    ("event", {("GET", "/events"), ("POST", "/events/{event_id}/register"), ("GET", "/events/registered")}),
    ("assistant", {("POST", "/assistant/chat")}),
])
def test_each_service_owns_the_expected_endpoints(key, expected):
    assert expected <= endpoints(service_app(key))


def test_routes_of_refuses_a_path_that_does_not_exist():
    from app.routers import auth
    with pytest.raises(RuntimeError):
        routes_of(auth.router, "/auth/typo")


# ---------------- /health ----------------
@pytest.mark.parametrize("key", KEYS)
def test_health_names_the_service(key):
    with TestClient(service_app(key)) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": f"p06-{key}", "pair": PAIR_STR, "port": SERVICE_PORTS[key]}
    assert r.headers["x-p06-service"] == f"p06-{key}"


def test_a_service_does_not_answer_for_another_services_paths():
    with TestClient(service_app("event")) as c:
        assert c.get("/jobs").status_code == 404
        assert c.get("/students/me").status_code == 404


# ---------------- Dockerfiles ----------------
@pytest.mark.parametrize("key", KEYS)
def test_dockerfile_matches_config_and_real_files(key):
    text = (BACKEND / "docker" / f"Dockerfile.{key}").read_text(encoding="utf-8")
    port = SERVICE_PORTS[key]
    assert re.findall(r"^EXPOSE (\d+)$", text, re.M) == [str(port)]
    assert f"--port\", \"{port}\"" in text                          # uvicorn starts on that port
    assert f"http://127.0.0.1:{port}/health" in text and "HEALTHCHECK" in text
    assert f"services.{key}.main:app" in text                        # it starts the right service
    assert "USER p06" in text                                        # not running as root
    # the files it copies exist, and only this service's requirements are installed
    assert (BACKEND / "requirements" / f"{key}.txt").is_file()
    assert (BACKEND / "services" / key / "main.py").is_file()
    assert f"pip install -r requirements/{key}.txt" in text
    assert "pytest" not in (BACKEND / "requirements" / f"{key}.txt").read_text()


def test_requirements_stay_minimal_and_pinned():
    base = (BACKEND / "requirements" / "base.txt").read_text()
    for forbidden in ("pytest", "faker", "httpx", "python-multipart"):   # extras live in the files that need them
        assert forbidden not in base
    assert "httpx" in (BACKEND / "requirements" / "assistant.txt").read_text()
    for name in ("student", "company", "application"):
        assert "python-multipart" in (BACKEND / "requirements" / f"{name}.txt").read_text()
    for path in (BACKEND / "requirements").glob("*.txt"):
        for line in path.read_text().splitlines():
            if line and not line.startswith(("#", "-r")):
                assert "==" in line, f"{path.name}: {line} is not pinned"


def test_no_secret_is_baked_into_an_image():
    ignore = (BACKEND / ".dockerignore").read_text().splitlines()
    assert ".env" in ignore and "tests/" in ignore and "venv/" in ignore
    for key in KEYS:
        text = (BACKEND / "docker" / f"Dockerfile.{key}").read_text()
        assert not re.search(r"(PASSWORD|SECRET|TOKEN)=", text), f"Dockerfile.{key} sets a secret"


# ---------------- the services share one login system ----------------
@pytest.fixture()
def clients(session_factory):
    """One test client per service, all on the SAME in-memory database (like the real shared database)."""
    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    apps = {key: service_app(key) for key in KEYS}
    for a in apps.values():
        a.dependency_overrides[get_db] = override
    opened = {key: TestClient(a) for key, a in apps.items()}
    yield opened
    for a in apps.values():
        a.dependency_overrides.clear()


def test_signup_in_one_service_works_in_the_others(clients):
    token = clients["student"].post("/auth/student/signup", json=STUDENT).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert clients["student"].get("/auth/me", headers=auth).json()["role"] == "student"
    assert clients["application"].get("/applications/mine", headers=auth).status_code == 200
    assert clients["event"].get("/events/registered", headers=auth).status_code == 200
    assert clients["job"].get("/jobs", headers=auth).status_code == 200


def test_company_signup_and_login_across_services(clients):
    assert clients["company"].post("/auth/company/signup", json=COMPANY).status_code == 201
    # login lives in the Student service but serves both roles
    login = clients["student"].post("/auth/login", json={"email": COMPANY["email"], "password": COMPANY["password"],
                                                          "role": "company"})
    assert login.status_code == 200 and login.json()["role"] == "company"
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert clients["company"].get("/companies/me", headers=auth).json()["name"] == "Acme Corp"
    assert clients["job"].get("/jobs/mine", headers=auth).status_code == 200


def test_role_rules_still_hold_in_the_split(clients):
    student = {"Authorization": "Bearer " + clients["student"].post("/auth/student/signup", json=STUDENT).json()["access_token"]}
    company = {"Authorization": "Bearer " + clients["company"].post("/auth/company/signup", json=COMPANY).json()["access_token"]}
    assert clients["job"].get("/jobs/mine", headers=student).status_code == 403          # students cannot list postings
    assert clients["company"].get("/companies/me", headers=student).status_code == 403
    assert clients["application"].get("/applications/mine", headers=company).status_code == 403
    assert clients["event"].get("/events/registered", headers=company).status_code == 403
    assert clients["assistant"].post("/assistant/chat", json={"message": "hi"}, headers=company).status_code == 403
    assert clients["job"].get("/jobs/mine").status_code == 401                            # no token
