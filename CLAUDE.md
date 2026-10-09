# DATA-260 Lab 1 (Handshake clone + hand-built AI assistant) — Pair 06

Standing instructions for Claude Code. Two people use this repo, each with their own
Claude Code session: **Uday** (Part A, platform) and **his partner** (Parts B and C,
assistant). Read this whole file at the start of every session.

## First thing to do in every new session

1. Read the assignment: `docs/Lab_1.pdf`. If it is not in the repo, ask the user to add it
   and wait. (Lab 1 only. Lab 2 comes later and is not in scope.)
2. Read the existing code before proposing anything: `README.md`, `METRICS.md`,
   `RUN_LOG.txt`, `AI_USE.md`, `docs/PART_A_CHECKLIST.md`, then `backend/app/` (main.py,
   models.py, routers/, services/, schemas/), `backend/tests/`, `frontend/src/`
   (App.jsx, pages/, components/, services/), `backend/seed/generate_seed.py`.
3. Run `git status` and `git log --oneline -15` so you know what is committed.
4. Tell the user, in a few sentences, what you understood: what is built, what is left,
   and which of the work below belongs to the person you are talking to.
5. Ask **who you are working with** (Uday or the partner) and **which task** they want,
   unless they already said. Do not start editing before that.

## Fixed pair configuration (never recompute, never ask)

| Value | Result |
|---|---|
| PAIR | 06 |
| PORT_BASE | 9060 (backend 9060, React dev server 9061) |
| Database name | `p06_handshake` (prefix `p06`; Kafka prefix `p06` in Lab 2) |
| SEED | 6 (every generator and every `random_state`) |
| CITY_SET | San Jose, Sunnyvale, Mountain View |
| Report filename | `LabPair-06_Lab1_Report.pdf` |
| Git tag at the end | `lab1` |

Local model: Ollama, `qwen3:8b` by default (alternative `llama3-groq-tool-use:8b`;
fallback `qwen3:4b` or `llama3.2:3b` with a note about reduced reliability).

Demo logins (seeded): `demo.student@sjsu.edu` and `demo.company@example.com`, password
`Password123!`. Never put a real password or secret in any committed file.

## Who owns what

| Area | Owner | Notes |
|---|---|---|
| Part A: React + FastAPI + MySQL platform, seed generator, API docs (22 pts) | Uday | Done and tested. Edits now are fixes and polish. |
| Part B: model client, agent loop, 5 tools, transcripts (12 pts) | Partner | |
| Part C: confirmation gate, injection defense, reliability table (6 pts) | Partner | |
| `README.md`, `METRICS.md`, `RUN_LOG.txt` | Both | Each person adds only their own part. |
| `AI_USE.md` | Both | Each person writes only their own section, see rules below. |
| Report Part A sections | Uday's Claude Code | |
| Report Part B and C sections | Partner's Claude Code | |

Rules for working in someone else's area:
- Do not edit files owned by the other person without asking the human first.
- Do not change an API contract (endpoint path, request body, response shape) that the
  other person depends on without telling the human so they can tell their partner.
- Do not change the pair configuration, the seed counts, or the ports.

## The contract between Part A and Part B

- The assistant endpoint is `POST /assistant/chat` with body `{message, conversation_id}`
  and response `{reply, conversation_id, tool_calls: [{name, arguments, result}]}`.
  The router, schemas and tests exist already. The partner replaces **only the body of
  `run_assistant()`** in `backend/app/services/assistant.py`. The frontend chat window
  (`ChatWindow.jsx`, `assistantService.js`) already works against this contract.
- Tools must reuse the existing **service functions** in `backend/app/services/` (jobs,
  events, students, preferences), not copy SQL. Services already enforce who may see
  what, so tools get the same permission rules as the API.
- All model calls go through **one client class** with `complete(messages, tools)`.
  Nothing else in the app may call Ollama directly. No agent frameworks (no LangChain,
  LlamaIndex, CrewAI): write the loop by hand, with a hard iteration ceiling.
- Every tool returns a string in every case and never raises.
- `save_job_or_event` is the only state-changing tool. It is gated by
  `confirm_action(tool_name, arguments, auto_approve=False)` in its own module (Part C).
  Read-only tools are not gated.

## Architecture and conventions (follow these, do not reinvent)

Backend (FastAPI, SQLAlchemy 2.0, Pydantic v2, MySQL via pymysql):
- Layering: `routers/` (HTTP only) -> `schemas/` (Pydantic validation) -> `services/`
  (business rules and queries). Routers stay thin.
- Passwords: bcrypt. Auth: JWT (HS256, 8 hours). Role checks in `core/deps.py`.
- A user asking for something they may not see gets **404**, not 403, for other people's
  applications and resumes (do not leak that it exists). 403 is for role or eligibility.
- Resumes are private: served only by the authenticated `GET /applications/{id}/resume`.
  Profile pictures are public under `/media/...`.
- Role views: a company sees student email, phone and GPA (never date of birth); a
  student sees a limited view of peers (no email, phone or GPA).
- Tests use pytest with an in-memory SQLite database. Do not point tests at MySQL.

Frontend (React 18, Vite, react-router 6, Axios, react-bootstrap):
- Pages never call Axios directly. Pages -> `services/*.js` -> `services/api.js`.
- Use the `useAsync` hook for loading, error and reload. Every request has a loading and
  an error state.
- Array filters must be sent as repeated keys (`paramsSerializer: { indexes: null }`),
  which is what FastAPI expects.
- Media URLs go through `mediaUrl()`; resumes are fetched as blobs with the token and
  shown in an iframe via `URL.createObjectURL`.
- Tests use Vitest, Testing Library and axios-mock-adapter.

## Commands (Windows PowerShell, from the repo root `data260-pair06`)

```powershell
# Backend (needs backend\.env copied from backend\.env.example, with a real MySQL password)
cd backend
python -m seed.generate_seed --reset        # drop + rebuild + seed p06_handshake
uvicorn app.main:app --port 9060            # API; docs at http://localhost:9060/docs
python -m pytest -q                         # 346 tests expected (takes about 3.5 minutes)
python -m scripts.collect_metrics           # writes docs\part_a_metrics.md
python -m scripts.export_api_docs           # refreshes docs\openapi.json and postman_collection.json

# Frontend
cd ..\frontend
npm install
npm run dev                                 # http://localhost:9061 (strict port)
npm test                                    # 148 tests expected
```

Use the Python virtual environment (`venv`) in the repo root. Never commit `venv`,
`node_modules`, `__pycache__`, `.env`, or `backend/uploads/`.

## Workflow: part by part, and STOP after each part

1. **Plan briefly**: a few sentences. Ask before a real design choice that has more than
   one reasonable option. Do not ask about small details.
2. **Build it.**
3. **Test it for real** (see below).
4. **Say exactly which files changed** so the human can review them.
5. **Stop.** The human reads the change, runs it, and does the commit.

**Never run `git commit`, `git push`, `git tag`, or change the remote unless the human
explicitly asks in that message.** You may run read-only git commands (`status`, `diff`,
`log`). When you finish a part, suggest a one-line commit message and let the human run it.

## Testing philosophy

- Never call something done because the code "looks right". Run it.
- Run the relevant tests and the real app. Report the real output, including failures.
- Do not edit a test to make it pass unless the test itself is wrong; if so, say so.
- Never invent results. Numbers, transcripts, latencies, reliability counts, and
  before/after injection results must come from runs that actually happened. If something
  could not be run (for example Ollama is not installed on this machine), say so plainly
  and leave a clearly marked placeholder. Do not fill it in.
- When you run a command that belongs in `RUN_LOG.txt`, tell the human so they can
  record it (the log is a recording of real commands and real output).

## Explain things

The graders pick code during the 5-minute recording and ask each partner to explain it.
So the human must be able to explain every line you write. Keep code simple and
commented where the logic is not obvious, and after each change explain in plain English
what it does and why. Spell out acronyms the first time (JWT = JSON Web Token). Do not
use clever shortcuts the human cannot explain.

## AI_USE.md rules

Each partner has their own section, written by that partner. It must identify the
assistant use, show one **real** incorrect output, how it was detected, and the fix.
- Never write or "improve" the other partner's section.
- Never invent an incorrect output. If the human asks for help drafting, ask them what
  actually went wrong and write down only what they tell you, in their words.
- Real incorrect outputs already recorded for Part A are in the Uday section; do not
  duplicate them.

## The report: `LabPair-06_Lab1_Report.pdf`

Source of truth is `docs/report/report.md` (Markdown, with images from
`docs/screenshots/`). Build the PDF from it with a script in `docs/report/` so it can be
rebuilt after every edit. If a PDF toolchain is missing, say so and ask before installing
anything large. Keep the final PDF at the repo root, and put the final commit hash on the
title page (the same convention as the homework reports).

Style: follow the homework reports. Short plain paragraphs, numbered sections, tables
for numbers, every claim backed by a real log, screenshot or file reference, no filler.
If `docs/report/style_sample.pdf` exists, read it and match its layout, headings and tone.
If it does not exist, ask the human for a sample before designing the layout.

Required sections, in this order (all of them are in the assignment):

| # | Section | Source of evidence | Owner |
|---|---|---|---|
| 1 | Goals | Lab_1.pdf, README | Uday |
| 2 | System design (architecture diagram, layers, data model, auth, role rules) | code, README | Uday |
| 3 | Pair parameters (PAIR, PORT_BASE, database, SEED, CITY_SET) | README | Uday |
| 4 | Seed counts | `docs/part_a_metrics.md`, METRICS.md | Uday |
| 5 | Screenshots (app screens, tests, row counts, git history) | `docs/screenshots/` | Uday; git history shot needs both partners |
| 6 | API tests (Swagger evidence, status codes, role rules, test suite results) | `docs/screenshots/api_*.png`, pytest output | Uday |
| 7 | Five transcripts (every tool call shown) | Part B runs | Partner |
| 8 | Reliability table (valid and failed calls over 20+ turns, before and after repair) | Part C runs | Partner |
| 9 | Injection before and after (five verification queries, exactly what changed) | Part C runs | Partner |
| 10 | Assistant tool-call evidence | Part B and C runs | Partner |

Rules:
- Sections 7 to 10 are the partner's. Until they exist, leave a visible placeholder like
  `<!-- PARTNER (Parts B/C): paste the five transcripts here, from real runs -->` and do
  not write them yourself.
- Each Claude Code session writes only its owner's sections and leaves the other's alone.
  If both edit `report.md`, keep changes to separate sections so merges stay clean.
- Part A numbers come only from `METRICS.md` / `docs/part_a_metrics.md` and real
  command output. Re-run `collect_metrics` if the data changed.
- Screenshots already saved: `docs/screenshots/api_01` to `api_20` (Swagger). Still
  to capture: React app screens (student home with chat, job search with filters,
  my applications with resume window, company applicant detail), `pytest` and `npm test`
  summaries, metrics terminal output, and the Git commit history screenshot at the end.

## Submission checklist (Lab 1)

- [ ] Private repo with README, `requirements.txt`, frontend and backend source,
      seed generator, API documentation (`docs/openapi.json`, Postman collection)
- [ ] Instructors or graders named on Canvas invited as collaborators
- [ ] `.gitignore` covers `venv/`, `node_modules/`, `__pycache__/`, `.env`, uploads
- [ ] `git ls-files | Select-String "\.env$|venv|node_modules|__pycache__|uploads"`
      shows nothing except our own source file `backend/app/core/uploads.py`
- [ ] `METRICS.md`, `RUN_LOG.txt`, `AI_USE.md` filled in (both partners)
- [ ] Both partners have commits
- [ ] `LabPair-06_Lab1_Report.pdf` with all ten sections
- [ ] Five-minute screen recording; both partners run the system and explain code the
      grader picks
- [ ] Tag created and pushed (human does this): `git tag lab1` then `git push origin lab1`

Due: Monday Oct 19, 2026, 3:00 PM.

## Status (update this section when something changes)

- Part A: complete. Backend 346 tests pass, frontend 148 tests pass.
- Seed (SEED=6): 50 companies, 200 students, 300 jobs, 1500 applications, 100 events,
  400 registrations. Measured on real MySQL; all endpoints returned 200, medians under
  18 ms except login (about 375 ms, bcrypt on purpose).
- Evidence files exist: README.md, METRICS.md (Part A), RUN_LOG.txt (Part A),
  AI_USE.md (Uday section), docs/.
- Part B and C: not started in this repo yet (placeholder `run_assistant()` returns a
  stub reply).
- Report: not started.
