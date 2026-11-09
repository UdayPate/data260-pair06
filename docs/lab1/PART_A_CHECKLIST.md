# Part A checklist (Lab 1, 22 points)

Use this as the source for the report. Each row of the handout's Part A list is matched to where it lives in the
project and how it is tested.

## 1. Requirements -> where they are

| Handout requirement | Where in the app | Backend | Tests |
|---|---|---|---|
| Student signup (name, email, password, college), bcrypt | `/signup` | `POST /auth/student/signup` | `test_auth.py`, `signup.test.jsx` |
| Sign in / sign out (JWT) | `/login`, navbar *Sign out* | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | `test_auth.py`, `login.test.jsx`, `navbar.test.jsx` |
| Student profile + every updatable field + picture | `/profile` | `GET/PATCH /students/me`, `POST /students/me/profile-picture` | `test_profiles.py`, `profile.test.jsx` |
| Search jobs by company or title; filter category and city | `/jobs` | `GET /jobs` | `test_jobs.py`, `jobs.test.jsx` |
| Job details, company profile, deadline, location, salary, contact | `/jobs/:id` | `GET /jobs/{id}` | `test_jobs.py`, `jobs.test.jsx` |
| Apply with PDF resume; applications with date and status; filter Pending / Reviewed / Declined | `/jobs/:id`, `/applications` | `POST /jobs/{id}/apply`, `GET /applications/mine` | `test_applications.py`, `jobs.test.jsx` |
| Events in date order, search by name, details, register if eligible, registered events | `/events`, `/events/:id`, `/events/registered` | `GET /events`, `POST/DELETE /events/{id}/register`, `GET /events/registered` | `test_events.py`, `events_students.test.jsx` |
| Browse students by name or college, filter by major | `/students` | `GET /students` (peer view) | `test_directory.py`, `events_students.test.jsx` |
| AI Assistant chat on home page | `/` (student) | `POST /assistant/chat` | `test_assistant.py`, `chat.test.jsx` |
| Company signup (name, email, password, location), sign in / out | `/signup` (company toggle) | `POST /auth/company/signup` | `test_auth.py` |
| Post jobs (title, posting date, deadline, location, salary, description, category) | `/company/jobs/new` | `POST /jobs` | `test_jobs.py`, `company_jobs.test.jsx` |
| Own postings and who applied | `/company/jobs`, `/company/jobs/:id/applicants` | `GET /jobs/mine`, `GET /jobs/{id}/applications` | `test_applications.py`, `company_jobs.test.jsx` |
| Open a student profile, preview PDF resume, set status | `/company/applications/:id` | `GET /applications/{id}`, `.../resume`, `PATCH .../status` | `test_applications.py`, `company_jobs.test.jsx` |
| Company profile (name, location, description, contact, picture) | `/company/profile` | `GET/PATCH /companies/me`, `POST /companies/me/profile-picture` | `test_profiles.py`, `company_more.test.jsx` |
| Students tab: search by name, college, skills; view profiles | `/students`, `/students/:id` | `GET /students` (company view) | `test_directory.py`, `company_more.test.jsx` |
| Events tab: post events, registered students and profiles | `/company/events/...` | `POST /events`, `GET /events/{id}/registrations` | `test_events.py`, `company_more.test.jsx` |
| Preferences | `/profile` (second tab) | `GET/PUT/DELETE /students/me/preferences` | `test_preferences.py`, `profile.test.jsx` |
| Dashboards | `/` | totals from the list endpoints; extra: application activity heatmap from `GET /students/me/activity` | `home.test.jsx`, `activity.test.jsx`, `test_activity.py` |
| Validate every input, encrypt passwords, exceptions, authorization | everywhere | see README *Security and validation* | the 401 / 403 / 404 / 409 / 422 tests in every file |
| React with Bootstrap, Axios, loading and error states, separate components / pages / services | `frontend/src` | n/a | `components.test.jsx`, `home.test.jsx` |
| Swagger or Postman with parameters, headers, sample responses | `/docs`, `docs/` | `openapi.json`, `postman_collection.json` | n/a |
| Seed: >= 300 jobs, 1500 applications, 200 students, 50 companies, 100 events | `backend/seed` | `python -m seed.generate_seed --reset` | `collect_metrics.py` checks the minimums |

## 2. Commands to produce the evidence (run from the repo, venv active)

**METRICS.md numbers**
```powershell
cd backend
uvicorn app.main:app --port 9060        # leave running in a second window
python -m scripts.collect_metrics --with-tests
```
Paste the printed block into `METRICS.md` (it is also saved as `docs/part_a_metrics.md`). Then run `npm test` in
`frontend/` and paste its last lines under "Frontend tests".

**API documentation export** (already generated; run again after any API change)
```powershell
cd backend
python -m scripts.export_api_docs
```

**RUN_LOG.txt** (a real transcript of the commands and their output). In a fresh PowerShell window:
```powershell
cd C:\Users\patel\data260-pair06
Start-Transcript -Path .\docs\run_transcript.txt
cd backend
python -m seed.generate_seed --reset
python -m pytest -q
cd ..\frontend
npm test
cd ..
Stop-Transcript
```
Then open `docs\run_transcript.txt`, check it contains no password (it should not), and paste it into `RUN_LOG.txt`
under the header. Do **not** run `type .env` or `echo $env:DB_PASSWORD` while recording.

## 3. Screenshots to take for the report (save in `docs/screenshots/`)

1. Swagger UI home (`/docs`) showing the endpoint groups
2. Swagger: `POST /auth/login` 200 and the Authorize dialog
3. Swagger: `GET /jobs` with filters (total and items)
4. Swagger: a 403 (company token on a student endpoint) and a 404 (another student's resume)
5. Swagger: `GET /students` as a student (no email) next to the same call as a company (with email)
6. MySQL row counts (output of `collect_metrics`, or `SELECT COUNT(*)` per table)
7. Sign up and sign in pages
8. Student home with stats and the AI chat window
9. Job search with filters; job details; the Apply box after applying
10. My applications with status tabs, and the resume window
11. Events list, event details with the reason when not eligible, My events
12. Students directory (student) and a peer profile
13. Student profile page and the preferences tab
14. Company: My postings, Post a job, Applicants, applicant detail with resume preview and status buttons
15. Company: Company profile, Students tab, Events (post, registered students)
16. Passing tests: `pytest` and `npm test` summaries
17. Git commit history (`git log --oneline --graph` or the GitHub commits page) showing both partners

## 4. Repository and submission checklist

- [ ] Repository is **private**
- [ ] Partner and the instructors / graders named on Canvas are invited as collaborators
- [ ] `.gitignore` covers `venv/`, `node_modules/`, `__pycache__/`, `.env`, `uploads/` (see `.gitignore.suggested`)
- [ ] `git ls-files | Select-String "\.env$|venv|node_modules|__pycache__|uploads"` prints nothing
- [ ] `.env.example` has placeholders only (no real password)
- [ ] README, `requirements.txt`, `METRICS.md`, `RUN_LOG.txt`, `AI_USE.md` present and filled in
- [ ] Both partners have commits
- [ ] Tag created and pushed: `git tag lab1` then `git push origin lab1`
- [ ] Five-minute recording: both partners run the system and explain code the grader picks
- [ ] Report `LabPair-06_Lab1_Report.pdf` (goals, design, screenshots, API tests, pair parameters, seed counts, transcripts,
      reliability table, injection before / after, tool-call evidence)
