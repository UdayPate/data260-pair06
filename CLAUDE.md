# DATA-260 Handshake clone + hand-built AI assistant — Pair 06 (Lab 1 done, Lab 2 in progress)

Standing instructions for Claude Code. Two people use this repo, each with their own
Claude Code session: **Uday** and **his partner** (Sreeramachandra Sai Achutuni). Read this
whole file at the start of every session.

## First thing to do in every new session

1. Read the assignment for the lab in progress: **Lab 2 is `docs/lab2/Handshake_Lab2.pdf`**
   (due 11/16/2026). Lab 1 is `docs/lab1/Lab_1.pdf` (finished, tagged `lab1`). If a PDF is not
   in the repo, ask the user to add it and wait.
2. Read the existing code before proposing anything: `README.md`, `METRICS.md`,
   `RUN_LOG.txt`, `AI_USE.md`, everything in `docs/lab2/`, then `backend/app/` (main.py,
   models.py, routers/, services/, schemas/, assistant/), `backend/services/` (the six Lab 2
   services), `backend/docker/`, `gateway/`, `frontend/src/`, `backend/tests/`, and `k8s/` once it exists.
3. Run `git status` and `git log --oneline -15` so you know what is committed.
4. Tell the user, in a few sentences, what you understood: what is built, what is left,
   and which of the work below belongs to the person you are talking to.
5. Ask **who you are working with** (Uday or the partner) and **which task** they want,
   unless they already said. Do not start editing before that.

## Fixed pair configuration (never recompute, never ask)

| Value | Result |
|---|---|
| PAIR | 06 |
| PORT_BASE | 9060 |
| Ports | 9060 = backend (single app, local dev) or the nginx gateway (Docker); 9061 = website; 9062 Student, 9063 Company, 9064 Job, 9065 Application, 9066 Event, 9067 AI Assistant |
| Database name | `p06_handshake` (MySQL in Lab 1; MongoDB, same name, in Lab 2) |
| Prefix for everything Lab 2 | `p06`: images `p06-<service>:<version>`, containers, Kafka topics `p06.<name>` (dead letter `p06.dlq`), Kubernetes namespace `p06-handshake`, every resource named `p06-...` |
| SEED | 6 (every generator and every `random_state`) |
| CITY_SET | San Jose, Sunnyvale, Mountain View |
| Report filenames | `LabPair-06_Lab1_Report.pdf` (submitted, in `docs/lab1/`), `LabPair-06_Lab2_Report.pdf` |
| Git tags | `lab1` (on `61f114c`, pushed); `lab2` at the end |

Local model: Ollama, `qwen3:8b` by default (alternative `llama3-groq-tool-use:8b`;
fallback `qwen3:4b` or `llama3.2:3b` with a note about reduced reliability).

Demo logins (seeded): `demo.student@sjsu.edu` and `demo.company@example.com`, password
`Password123!`. Never put a real password or secret in any committed file.

## Who owns what

Lab 1 (finished): Uday = Part A (platform); partner = Parts B and C (assistant, safety, reliability).

Lab 2 split:

| Area | Owner |
|---|---|
| Part 1.1 Dockerfiles (6 services, HEALTHCHECK, `/health`), 1.2 Docker Compose, 1.3 Kubernetes manifests | Uday |
| Part 2 Kafka (KRaft in Compose and Kubernetes, the topic flows, 3 failure demos, architecture diagram) | Uday |
| Part 3 MongoDB migration (not the assistant memory layers) | Uday |
| Part 1.4-1.6 AWS (ECR, EKS, LoadBalancer, evidence), Part 3 assistant memory, Part 4 Redux, Part 5 JMeter, Part 6 | Partner |
| `docs/lab2/MONGO_SCHEMA.md`, `docs/lab2/KAFKA_CONTRACT.md` | Uday writes them for the partner |
| `README.md`, `METRICS.md`, `RUN_LOG.txt`, `AI_USE.md`, the Lab 2 report | Both; each person writes only their own part |

Rules for working in someone else's area:
- Do not edit files owned by the other person without asking the human first.
- Do not change an API contract (endpoint path, request body, response shape, Kafka message
  format) that the other person depends on without telling the human so they can tell their partner.
- Do not change the pair configuration, the seed counts, or the ports.

## Lab 2 design decisions (agreed 2026-11-08, do not reopen without asking)

1. **One codebase, six services.** `backend/app/` is shared; `backend/services/<name>/main.py`
   mounts only that service's routers. All six use the same database and the same JWT secret.
2. **nginx gateway on 9060** routes by path (`gateway/nginx.conf`); the website keeps calling one address.
   `/jobs/{id}/apply` and `/jobs/{id}/applications` belong to the Application service; the rest of `/jobs` to Job.
3. **MongoDB stores resumes and profile pictures (GridFS)** so every pod is stateless; no shared volumes.
4. **Apply is asynchronous (implemented):** the API validates and stores the PDF, publishes `p06.application.created`
   and returns **202**; the Application worker inserts the application, idempotent on its natural key (student, job).
   The website's ApplyBox shows "received" and polls; the Redux applications slice (partner) must handle the 202.
5. **Assistant tools stay in-process** (they use the shared data layer); the assistant service also checks
   the other services' `/health`. Partner's Part 6 harness depends on this.
6. **Local Kubernetes is `kind`** (downloaded when Kubernetes work starts).
7. **MongoDB keeps integer ids** (a `counters` collection), so URLs, the frontend and the assistant tools do not change.

Every Kafka message carries `event_id` (UUID, for idempotency), `event_type`, `timestamp`, `payload`
and `trace_id` (in the Kafka headers AND in the message body). The full contract (topics, envelope, payloads, retry and
dead-letter rules, how to add a producer or consumer) is `docs/lab2/KAFKA_CONTRACT.md`; the code is `backend/app/events/`.
A worker commits its offset only after its database write; handlers must be idempotent.

## The contract between the platform and the assistant

- The assistant endpoint is `POST /assistant/chat` with body `{message, conversation_id}`
  and response `{reply, conversation_id, tool_calls: [{name, arguments, result}]}`. The frontend chat
  window (`ChatWindow.jsx`, `assistantService.js`) works against this contract.
- Tools must reuse the existing **service functions** in `backend/app/services/` (jobs,
  events, students, preferences), not copy queries. Services already enforce who may see
  what, so tools get the same permission rules as the API.
- All model calls go through **one client class** with `complete(messages, tools)`
  (`backend/app/assistant/model_client.py`). Nothing else in the app may call Ollama directly.
  No agent frameworks (no LangChain, LlamaIndex, CrewAI): the loop is written by hand, with a hard iteration ceiling.
- Every tool returns a string in every case and never raises.
- `save_job_or_event` is the only state-changing tool. It is gated by
  `confirm_action(tool_name, arguments, auto_approve=False)` in its own module.
  Read-only tools are not gated.

## Architecture and conventions (follow these, do not reinvent)

Backend (FastAPI, Pydantic v2). The data layer is pymongo on MongoDB (`backend/app/mongo.py` helpers,
`backend/app/documents.py` builders; schema in `docs/lab2/MONGO_SCHEMA.md`). Lab 1 used SQLAlchemy on MySQL (tag
`lab1`); the migration kept every endpoint and response shape unchanged.
- MongoDB keeps integer ids (`mongo.insert` / `mongo.next_id`), stores dates as `"YYYY-MM-DD"` text, and builds
  documents only through `documents.*` (they fill the derived search fields). Index and unique rules are the
  `INDEXES` list in `mongo.py`. Files (resumes, pictures) are in GridFS.
- Sessions: every login makes a document in `sessions` (TTL index); the JWT's `jti` must match a live session, and
  `POST /auth/logout` deletes it. Important actions go to `activity_logs` (`services/activity_log.py`).
- Layering: `routers/` (HTTP only) -> `schemas/` (Pydantic validation) -> `services/`
  (business rules and queries). Routers stay thin.
- Passwords: bcrypt. Auth: JWT (HS256, 8 hours). Role checks in `core/deps.py`.
- A user asking for something they may not see gets **404**, not 403, for other people's
  applications and resumes (do not leak that it exists). 403 is for role or eligibility.
- Resumes are private: served only by the authenticated `GET /applications/{id}/resume`.
  Profile pictures are public under `/media/...`.
- Role views: a company sees student email, phone and GPA (never date of birth); a
  student sees a limited view of peers (no email, phone or GPA).
- Tests use pytest on an in-memory MongoDB (`mongomock`, see `tests/conftest.py` and `tests/factories.py`). They never
  touch a real database: `MONGO_URL` is pointed at a dead address while they run.
- The six services (`backend/services/`) must together serve exactly the endpoints of the single
  app, with no overlap: `backend/tests/test_services.py` checks it. A new endpoint needs an owner.
- Docker: one Dockerfile per service in `backend/docker/`, each installing only
  `backend/requirements/<service>.txt`, running as a non-root user, with a `HEALTHCHECK` on `/health`.
  Never copy `.env`, tests or secrets into an image. Kubernetes manifests and Compose files hold no real secrets
  (Compose reads them from the git-ignored root `.env`; `.env.example` has placeholders only).
- Every service has `GET /health` (alive, no database) and `GET /health/ready` (pings MongoDB, 503 if it cannot): use the
  first for liveness and the second for readiness. `get_db()` creates the indexes on the first request that finds MongoDB, so
  a service that starts before MongoDB (Kubernetes) still ends up with the unique rules.

Frontend (React 18, Vite, react-router 6, Axios, react-bootstrap):
- Pages never call Axios directly. Pages -> `services/*.js` -> `services/api.js`.
- Use the `useAsync` hook for loading, error and reload. Every request has a loading and
  an error state.
- Array filters must be sent as repeated keys (`paramsSerializer: { indexes: null }`),
  which is what FastAPI expects.
- Media URLs go through `mediaUrl()`; resumes are fetched as blobs with the token and
  shown in an iframe via `URL.createObjectURL`.
- `VITE_API_URL` is baked in at build time (the gateway address the browser uses).
- Tests use Vitest, Testing Library and axios-mock-adapter.

## Commands (Windows PowerShell, from the repo root `data260-pair06`)

```powershell
# Backend, single app for local development (needs backend\.env copied from backend\.env.example, with MONGO_URL)
cd backend
docker run -d --name p06-mongo -p 9069:27017 mongo:7      # MongoDB for local development (set MONGO_URL=mongodb://localhost:9069 in backend\.env)
python -m seed.generate_seed --reset        # empty + index + seed p06_handshake in MongoDB
uvicorn app.main:app --port 9060            # API; docs at http://localhost:9060/docs
python -m pytest -q                         # all backend tests (about 4 minutes)

# Frontend
cd ..\frontend
npm install
npm run dev                                 # http://localhost:9061 (strict port)
npm test                                    # 210 tests expected

# Whole stack in Docker (see README, "run the whole stack with Docker Compose"); needs a root .env (copy .env.example)
cd ..; docker compose build; docker compose up -d; docker compose ps; docker compose down   # down -v also deletes the data
```

Use the Python virtual environment (`venv`) in `backend/`. Never commit `venv`,
`node_modules`, `__pycache__`, `.pytest_cache`, `.env`, `backend/uploads/`, secrets or API keys.

## Workflow: part by part, and STOP after each part

1. **Plan briefly**: a few sentences. Ask before a real design choice that has more than
   one reasonable option. Do not ask about small details.
2. **Build it.**
3. **Test it for real** (see below).
4. **Say exactly which files changed** and give the exact commands for the human to verify it.
5. **Stop.** The human reads the change, runs it, and does the commit.

**Never run `git commit`, `git push`, `git tag`, `git add` for a commit, or change the remote.**
(Uday's standing rule since 2026-11-08: even if a message seems to ask for it, give him the commands.)
You may run read-only git commands (`status`, `diff`, `log`). At the end of every phase or part, give the
human the exact commands to run themselves, for example:

```powershell
git add <the files of this phase>
git commit -m "<one-line message>"
git push
```

Never use `git add -A` or `git add .` unless the status list has been checked: line-ending noise can make
dozens of unchanged files look modified. List the files explicitly.

At the end of every Lab 2 phase, append that phase's commands and real results (failures included) to
`RUN_LOG.txt` under the "LAB 2" heading. Append only: never edit the Lab 1 entries.

## Testing philosophy

- Never call something done because the code "looks right". Run it.
- Run the relevant tests and the real app. Report the real output, including failures.
- Do not edit a test to make it pass unless the test itself is wrong; if so, say so.
- Never invent results. Numbers, transcripts, latencies, reliability counts, and
  before/after results must come from runs that actually happened. If something
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
- Real incorrect outputs already recorded are in each partner's section; do not duplicate them.

## The Lab 2 report: `LabPair-06_Lab2_Report.pdf`

The Lab 1 report is finished (`docs/lab1/LabPair-06_Lab1_Report.pdf`).

**There is exactly one Lab 2 report. Its source is `docs/report/lab2_report.md` and it builds to `LabPair-06_Lab2_Report.pdf`
with `python docs\report\build_pdf.py`. Always edit that file and rebuild; never create a new report file or a second PDF.
Each partner fills only their own sections and replaces only their own placeholders.**

Sections 1 to 6 are written (Uday); sections 7 to 14 are red dashed PLACEHOLDER boxes for the partner (cloud deployment,
memory and consolidation, Redux, JMeter, assistant load analysis, token compaction, the end-to-end trace, guardrails and the
harness). The three architecture diagrams are drawn from `docs/lab2/ARCHITECTURE.md` (`python docs\report\build_pdf.py --redraw`
draws them again; that needs the internet once). The assignment requires the report to cover: architecture, cloud deployment, Kafka flows and failures, MongoDB schema,
memory and consolidation, Redux state, performance graphs, assistant load analysis, token
compaction evidence, one end-to-end trace, the agent guardrail results, the harness test matrix and
output, and the blocked-injection, declined-confirmation, repaired-call and bounded-stop evidence.
Each partner writes only their own sections; every claim needs a real log, screenshot or file.
Screenshots for Lab 2 go in `docs/lab2/screenshots/` and must show the `p06-` names; hide secrets in all of them.

## Submission checklist (Lab 2)

- [ ] Repository has Dockerfiles, Compose file, Kubernetes manifests, ECR/EKS configuration, Kafka
      producers and consumers, the MongoDB migration, Redux, JMeter plans and results, guardrails,
      the evaluation harness (source and output), `requirements.txt`, and README instructions for
      running locally, running the harness, and reaching the AWS deployment
- [ ] No venv, `node_modules`, `__pycache__`, `.pytest_cache`, credentials or API keys committed
- [ ] `METRICS.md`, `RUN_LOG.txt` (with the three Kafka failure demos and traces), `AI_USE.md` updated by both
- [ ] Both partners have commits
- [ ] `LabPair-06_Lab2_Report.pdf`
- [ ] Five-minute screen recording; both partners run the system and explain code the grader picks
- [ ] AWS: images in ECR, cluster running, demo can be restored at the scheduled time (live viva)
- [ ] Tag `lab2` created and pushed (human does this): `git tag lab2` then `git push origin lab2`

Due: Monday 11/16/2026.

## Status (update this section when something changes)

- Lab 1: complete and tagged `lab1` (`61f114c`). Evidence in `docs/lab1/`.
- Lab 2, Uday's scope:
  - Cleanup done (Lab 1 evidence moved to `docs/lab1/`, `.gitignore` merged, `docs/lab2/` created).
  - Phase 1 (Dockerfiles + `/health`): done, committed and pushed (`69b2f52`). The six services, gateway and
    frontend images build, report healthy and route correctly; 432 backend tests pass.
  - Phase 2 (MongoDB migration + `docs/lab2/MONGO_SCHEMA.md`): done, committed and pushed (`c299a74`).
  - Phase 3 (Docker Compose: MongoDB with a password, Kafka KRaft broker, six services, gateway, website; `/health/ready`
    and the assistant's `/health/dependencies`): done, committed and pushed (`bf9d345`); 474 backend tests pass.
    Lab 1's `scripts/run_transcripts.py`, `run_part_c.py` and `collect_metrics.py` used the SQL layer and no longer run.
  - Phase 4 (Kafka: topics, producers in the Application/Event/Job APIs, three workers, `docs/lab2/KAFKA_CONTRACT.md`,
    asynchronous apply with 202): done, committed (`efe6c06`).
  - Phase 5 (producer for `application.updated` = `PUT /applications/{id}/resume`; three failure demos run on the real broker with
    `backend/scripts/kafka_demos.py`; `docs/lab2/ARCHITECTURE.md`; RUN_LOG PHASE 5): done, committed and pushed (`55b5358`; 543 backend tests).
  - Phase 6 (Kubernetes manifests in `k8s/`, namespace `p06-handshake`, tested on kind with Kubernetes 1.34 pinned because Docker Desktop
    uses cgroup v1; Secret made by `k8s/create_secret.py`, images loaded by `k8s/load_images.py`; RUN_LOG PHASE 6): built and verified
    on kind (18 pods Running); done, committed (`6d83e1f`). The clean output of the Kafka demos is `docs/lab2/kafka_demos_output.txt` (`1b6de88`). Not done: the three Kafka failure demos inside Kubernetes (they ran on Compose).
  - Phase 7 (Uday's report sections 1 to 6 in `docs/report/lab2_report.md`, built by `docs/report/build_pdf.py` to
    `LabPair-06_Lab2_Report.pdf`; the Mermaid diagrams in `ARCHITECTURE.md` fixed and rendered to `docs/report/img/`; Uday's section of
    `AI_USE.md`; the three screenshots in `docs/lab2/screenshots/`): done, committed.
  - **Uday's Lab 2 scope is complete and committed** (Parts 1.1 to 1.3, Part 2, and the Part 3 MongoDB migration). Do not reopen it
    without asking.
- Lab 2, the partner (Sreeramachandra Sai Achutuni) still owns, with the pointers to start from:
  - Part 1.4 to 1.6 AWS: images to ECR, the EKS cluster, the LoadBalancer, the end-to-end request and the screenshots; report section 7; the README
    instructions for reaching the AWS deployment. Start with the notes at the end of `k8s/README.md` and `k8s/overlays/local/`.
  - Part 3 assistant memory: `assistant_rules`, `student_memory`, session conversations, memory in the prompt, `/memory`, and the consolidation
    as a Kafka consumer (see `docs/lab2/KAFKA_CONTRACT.md` section 5 and `docs/lab2/MONGO_SCHEMA.md`); report section 8.
  - Part 4 Redux (the applications slice must handle the 202 of `POST /jobs/{id}/apply`; DevTools evidence); report section 9.
  - Part 5 JMeter (plan, CRUD load tests, assistant load tests and analysis); report sections 10 and 11.
  - Part 6 token tracking, compaction, trace propagation, guardrails, the evaluation harness and stage timing; report sections 12 to 14.
  - Things to watch when starting (known, not fixed):
    - JMeter: `POST /auth/login` needs a `role` field in the body (`student` or `company`); an application is unique per student and job, so
      repeating the same pair returns 409 (use fresh pairs: the seed already holds 1,500 applications); `POST /jobs/{id}/apply` answers 202, not 201,
      and the application appears a moment later (the worker writes it); assistant answers can take minutes on a CPU (the model timeout is 600 s).
    - The Lab 1 scripts `backend/scripts/run_transcripts.py`, `run_part_c.py` and `collect_metrics.py` still use the SQL layer and need porting to
      MongoDB before the real Ollama transcripts and the reliability experiments can be run again.
    - `docs/openapi.json` and `docs/postman_collection.json` were not regenerated for Lab 2 (apply is listed as 201; the new endpoints are missing).
  - Their parts of `METRICS.md` (the marked slot "Partner: Lab 2 metrics") and `RUN_LOG.txt`, their section of `AI_USE.md` (an empty marked slot), their screenshots (AWS, Redux
    DevTools, the agentic safety tests), and the harness and AWS instructions in `README.md`.
  - Both partners: the five-minute recording, the live AWS viva, and the `lab2` tag (the human creates it).
- The data layer is MongoDB (the Lab 1 MySQL database is untouched and still on the laptop).
