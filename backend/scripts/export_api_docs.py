"""
Exports the API documentation without needing the server or the database:

    docs/openapi.json              the full OpenAPI description (the same one Swagger UI shows)
    docs/postman_collection.json   a Postman collection: every endpoint, with parameters, the
                                   Authorization header and a sample request body

Run from backend/:     python -m scripts.export_api_docs
In Postman: Import -> docs/postman_collection.json. Run "Auth > Log in as demo student" first;
it saves the token into the {{token}} variable and every other request uses it.
"""
import json
import os
import re
import sys

from app.config import BACKEND_PORT
from app.main import app

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
DEMO = {"student": ("demo.student@sjsu.edu", "student"), "company": ("demo.company@example.com", "company")}
PASSWORD = "Password123!"


# ---------- a sample value for each schema ----------
def resolve(spec, schema):
    while "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        schema = spec["components"]["schemas"][name]
    return schema


# Realistic values for well-known field names (so the samples look like real requests).
SAMPLES = {
    "title": "Data Analyst Intern", "description": "Work with the data team on dashboards and SQL pipelines.",
    "city": "San Jose", "state": "CA", "location": "San Jose", "salary_min": 30, "salary_max": 40,
    "posting_date": "2026-10-20", "deadline": "2027-06-30", "contact_email": "jobs@example.com",
    "skills": ["Python", "SQL"], "name": "Demo Student", "college": "San Jose State University",
    "email": "demo.student@sjsu.edu", "password": "Password123!", "phone": "(408) 555-0123",
    "major": "Computer Science", "degree": "MS", "graduation_year": 2027, "cgpa": 3.8,
    "career_objective": "Build reliable data products.", "location_text": "Student Union",
    "event_datetime": "2027-02-10T17:30:00", "eligible_majors": ["Computer Science"],
    "message": "Find me an internship in San Jose", "conversation_id": None,
    "preferred_categories": ["internship"], "preferred_cities": ["San Jose"], "preferred_roles": ["Data Analyst"],
    "min_hourly_rate": 25, "open_to_remote": True, "event_interests": ["Career Fair"],
    "status": "Reviewed", "q": "data", "page": 1, "page_size": 20,
}


def example(spec, schema, depth=0, field=None):
    if field in SAMPLES:
        return SAMPLES[field]
    schema = resolve(spec, schema)
    if "example" in schema:
        return schema["example"]
    if "default" in schema and schema["default"] is not None:
        return schema["default"]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            return example(spec, options[0], depth + 1) if options else None
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        if depth > 3:
            return {}
        return {k: example(spec, v, depth + 1, k) for k, v in schema.get("properties", {}).items()}
    if kind == "array":
        return [example(spec, schema.get("items", {}), depth + 1)] if depth < 3 else []
    if kind == "integer":
        return schema.get("minimum", 1)
    if kind == "number":
        return schema.get("minimum", 1.0)
    if kind == "boolean":
        return False
    fmt = schema.get("format")
    return {"date": "2027-01-15", "date-time": "2027-01-15T17:30:00", "email": "name@example.com"}.get(fmt, "text")


# ---------- Postman ----------
def to_request(spec, path, method, op):
    secured = bool(op.get("security"))
    url_path = re.sub(r"\{(\w+)\}", r":\1", path)          # Postman writes path variables as :id
    params = op.get("parameters", [])
    def query_value(p):
        value = example(spec, p.get("schema", {}), 0, p["name"]) if p.get("schema") else ""
        if isinstance(value, list):                 # repeated keys are written one at a time in Postman
            value = value[0] if value else ""
        return str(value).lower() if isinstance(value, bool) else str(value)

    query = [{"key": p["name"], "value": query_value(p),
              "disabled": not p.get("required", False), "description": p.get("description", "")}
             for p in params if p["in"] == "query"]
    variables = [{"key": p["name"], "value": "1"} for p in params if p["in"] == "path"]
    request = {
        "method": method.upper(),
        "header": ([{"key": "Authorization", "value": "Bearer {{token}}"}] if secured else []),
        "url": {"raw": "{{base_url}}" + url_path, "host": ["{{base_url}}"],
                "path": [seg for seg in url_path.strip("/").split("/") if seg], "query": query, "variable": variables},
        "description": (op.get("summary", "") + "\n\n" + op.get("description", "")).strip(),
    }
    body = op.get("requestBody", {}).get("content", {})
    if "application/json" in body:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": json.dumps(example(spec, body["application/json"]["schema"]), indent=2),
                           "options": {"raw": {"language": "json"}}}
    elif "multipart/form-data" in body:
        schema = resolve(spec, body["multipart/form-data"]["schema"])
        request["body"] = {"mode": "formdata", "formdata": [{"key": k, "type": "file", "src": []}
                                                            for k in schema.get("properties", {})]}
    return {"name": f'{method.upper()} {path}', "request": request}


def build_collection(spec):
    groups = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            tag = (op.get("tags") or ["Other"])[0]
            item = to_request(spec, path, method, op)
            item["name"] = op.get("summary") or item["name"]
            groups.setdefault(tag, []).append(item)

    def login(who):
        email, role = DEMO[who]
        script = ('const body = pm.response.json();\n'
                  'pm.collectionVariables.set("token", body.access_token);\n'
                  'pm.test("logged in", () => pm.response.to.have.status(200));')
        return {"name": f"Log in as demo {who}", "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": script.split("\n")}}],
                "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}],
                            "url": {"raw": "{{base_url}}/auth/login", "host": ["{{base_url}}"], "path": ["auth", "login"]},
                            "body": {"mode": "raw", "raw": json.dumps({"email": email, "password": PASSWORD, "role": role}, indent=2),
                                     "options": {"raw": {"language": "json"}}}}}

    auth = groups.pop("Authentication", [])
    items = [{"name": "Auth", "item": [login("student"), login("company")] + auth}]
    items += [{"name": tag, "item": reqs} for tag, reqs in sorted(groups.items())]
    return {
        "info": {"name": "Handshake Clone API (Pair 06)", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                 "description": "Run 'Auth > Log in as demo student' (or company) first; it stores the JWT in {{token}}."},
        "variable": [{"key": "base_url", "value": f"http://localhost:{BACKEND_PORT}"}, {"key": "token", "value": ""}],
        "item": items,
    }


def main():
    spec = app.openapi()
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "openapi.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    collection = build_collection(spec)
    with open(os.path.join(DOCS_DIR, "postman_collection.json"), "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2)
    n = sum(1 for p in spec["paths"].values() for m in p if m in ("get", "post", "put", "patch", "delete"))
    print(f"Wrote docs/openapi.json and docs/postman_collection.json ({n} endpoints)")


if __name__ == "__main__":
    sys.exit(main())
