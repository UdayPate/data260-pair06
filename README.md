# DATA-260 Lab 1: Handshake Prototype (Pair 06)

A Handshake-style career platform for **students** and **companies**, built with **React + FastAPI + MySQL**,
with a hand-built AI assistant (Parts B and C, built by the other partner) that uses the same data.

This README covers the platform (Part A). The assistant's design, transcripts and safety work are documented in the
report and in `docs/` once Parts B and C are merged.

## Pair parameters (all derived from PAIR = 06)

| Parameter | Rule | Value |
|---|---|---|
| PAIR | assigned on Canvas | **06** |
| PORT_BASE | 9000 + (PAIR x 10) | **9060** |
| Backend (FastAPI) | PORT_BASE | **9060** |
| Frontend (React dev server) | PORT_BASE + 1 | **9061** |
| Database / Kafka prefix | `p{PAIR}` | **p06** (database `p06_handshake`) |
| SEED | PAIR, for every generator | **6** (`random.Random(6)`, `Faker.seed(6)`) |
| CITY_SET | assigned on Canvas | **San Jose, Sunnyvale, Mountain View** |

## What is in the repository

```
backend/            FastAPI application
  app/              routers (HTTP) -> services (logic shared with the assistant) -> models (MySQL tables)
    core/           password hashing, JWT, login checks, safe file uploads
    schemas/        every request and response shape, with the validation rules
    assistant/      reserved for Part B (Ollama client + agent loop)
  seed/             generate_seed.py: 50 companies, 200 students, 300 jobs, 1500 applications, 100 events, ...
  scripts/          export_api_docs.py (OpenAPI + Postman), collect_metrics.py (numbers for METRICS.md)
  tests/            pytest suite (runs on in-memory SQLite, never touches MySQL)
frontend/           React app (pages / components / services / context / hooks / utils / test)
docs/               openapi.json, postman_collection.json, part_a_metrics.md, screenshots, checklist
METRICS.md  RUN_LOG.txt  AI_USE.md
```

## Setup (Windows PowerShell)

Requirements: Python 3.11+, Node.js 18+, MySQL 8 running locally.

**1. Backend**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then open .env and put YOUR MySQL password in it
```
`.env` is git-ignored. Never put real values in `.env.example`.

**2. Create and fill the database** (creates `p06_handshake`, all tables, and the seed data)
```powershell
python -m seed.generate_seed --reset
```
Running it again gives identical data (SEED = 6). Demo logins (the same password for every seeded account is `Password123!`):

| Role | Email |
|---|---|
| Student | `demo.student@sjsu.edu` |
| Company | `demo.company@example.com` |

**3. Run the API** (always from the `backend` folder)
```powershell
uvicorn app.main:app --port 9060 --reload
```
Swagger UI: http://localhost:9060/docs  (click **Authorize** after `POST /auth/login`)

**4. Run the website**
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:9061. The port is fixed (`strictPort`) because the API only accepts requests from that origin.

**5. Run the tests**
```powershell
cd backend ; python -m pytest -q       # backend
cd frontend ; npm test                 # frontend
```

## Features

**Student:** sign up / sign in / sign out; profile (picture, contact details, education, experience, skills, career
objective); search jobs by title or company and filter by type, city, remote, pay, skills and deadline; job and company
details; apply with a PDF resume; applications list filtered by Pending / Reviewed / Declined; events (earliest first,
search, details, register when eligible by major, registered events); student directory (search by name or college,
filter by major, skills); saved job and event preferences; application activity heatmap and AI assistant chat on the home page.

**Company:** sign up / sign in / sign out; post and edit jobs; see own postings with applicant counts; see applicants,
open a student's profile, preview the uploaded PDF resume and set the status (Pending, Reviewed, Declined); company
profile with logo; students tab (search by name, college, skills); events tab (post, edit, see registered students).

## REST API

Interactive documentation is Swagger UI at `/docs`. Exports for grading are in `docs/`:
`openapi.json` and `postman_collection.json` (import into Postman, run *Auth > Log in as demo student* first).
Regenerate them with `python -m scripts.export_api_docs` from `backend/`.

| Area | Endpoints |
|---|---|
| Authentication | `POST /auth/student/signup`, `POST /auth/company/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Student profile | `GET/PATCH /students/me`, `POST /students/me/profile-picture`, `GET /students/me/activity?days=365` (applications per day, for the home-page heatmap) |
| Preferences | `GET/PUT/DELETE /students/me/preferences` |
| Student directory | `GET /students`, `GET /students/{id}` |
| Company profile | `GET/PATCH /companies/me`, `POST /companies/me/profile-picture`, `GET /companies/{id}` |
| Jobs | `POST /jobs`, `GET /jobs`, `GET /jobs/mine`, `GET /jobs/{id}`, `PATCH /jobs/{id}` |
| Applications | `POST /jobs/{id}/apply`, `GET /applications/mine`, `GET /jobs/{id}/applications`, `GET /applications/{id}`, `PATCH /applications/{id}/status`, `GET /applications/{id}/resume` |
| Events | `POST /events`, `GET /events`, `GET /events/mine`, `GET /events/registered`, `GET /events/{id}`, `PATCH /events/{id}`, `GET /events/{id}/registrations`, `POST/DELETE /events/{id}/register` |
| Assistant | `POST /assistant/chat` |
| Other | `GET /meta/options` (dropdown values), `GET /health` |

Dashboards use the `total` of `GET /applications/mine`, `/events/registered`, `/jobs/mine` and `/events/mine`.

## Security and validation

- **Passwords** are hashed with bcrypt (12 rounds by default); minimum 8 characters, at least one letter and one digit,
  at most 72 bytes (bcrypt's limit). The hash is never returned by any endpoint.
- **Authentication** is a signed JWT (HS256, 8 hours) sent as `Authorization: Bearer <token>`. Unknown or expired
  tokens get 401. Logging in uses the same message for a wrong email and a wrong password.
- **Authorization:** role guards give 403 for the wrong persona. A user's own data always comes from the token, never
  from an id in the URL (`/students/me`). Other people's applications and resumes answer 404 (not 403) so their existence
  is not revealed. Companies can only edit their own jobs and events.
- **Input validation:** every request body is a Pydantic model. The job, event, preference, profile-update,
  status-update and chat bodies use `extra="forbid"` (unknown fields such as `company_id` are refused with 422); the
  signup and login bodies ignore unknown fields, which never reach the database. Text is trimmed, lengths, ranges, dates and cross-field rules
  (deadline after posting date, pay minimum below maximum) are checked on the server. The React forms check the same
  rules first, but the server never trusts them.
- **Uploads:** resumes must really be PDFs (`%PDF-` magic bytes, 5 MB). Pictures must really be PNG, JPEG or WebP
  (magic bytes, 2 MB). File names are generated by the server. Resumes are **private**: stored outside the public media
  folder and served only through `GET /applications/{id}/resume` to the applicant and the owning company, with
  `Cache-Control: private, no-store`. Pictures are public by design.
- **Views by role:** a company sees a student's contact details and GPA but never the date of birth; another student sees
  only name, college, major, skills, objective and experience (no email, phone, GPA, date of birth or home city).
- **Errors:** database errors become a generic 500 without internal details; validation errors name the field.
- **Race conditions:** UNIQUE constraints (one application per student and job, one registration per student and event,
  one preferences row per student) are the final guard, and the API turns a violation into a clean 409.
- **Secrets:** `.env` is git-ignored; there are no API keys in the code; the JWT secret comes from the environment.

## How the assistant plugs in

`POST /assistant/chat` takes `{ "message", "conversation_id" }` and returns `{ "reply", "conversation_id", "tool_calls" }`.
The body of `run_assistant()` in `backend/app/services/assistant.py` is the only thing Part B replaces. Tools should
reuse `search_jobs` (`services/jobs.py`), `search_events` (`services/events.py`) and `get_student_preferences`
(`services/preferences.py`), so the assistant and the website always agree on what "matching" means.

## Testing

- Backend: `python -m pytest -q` runs the full API suite on an in-memory database (authentication, profiles, jobs,
  applications, resumes, events, directory, preferences, assistant endpoint).
- Frontend: `npm test` (Vitest + Testing Library + a fake server) covers every page, form checks, loading and error
  states, and the role-based routing.
- Numbers for the latest run are in `METRICS.md`.

## Known limitations (honest list)

- `npm audit` reports a few advisories in development tools (Vite/esbuild dev server); they do not ship in the built site.
- The login token is kept in `localStorage` (simple and common for a course project; an HttpOnly cookie would resist
  script injection better). There are no refresh tokens or password reset.
- Uploaded files live on the local disk of the API server (`uploads/`), not in object storage.
- Search uses SQL `LIKE`, not a full-text index; at this data size every query answers in milliseconds (see METRICS.md).

## Partners

- Uday: Part A (platform, API, database, seed data, website)
- Sreeramachandra Sai Achutuni : Parts B and C (assistant, safety, reliability)
