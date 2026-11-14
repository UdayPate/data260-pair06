# DATA-260 Handshake Platform (Pair 06): Lab 1 and Lab 2

A Handshake-style career platform for **students** and **companies**, built with **React + FastAPI + MongoDB**
(MySQL in Lab 1), with a hand-built AI assistant that uses the same data.

- **Lab 1** (done, git tag `lab1`): the platform on MySQL, the assistant agent loop, the confirmation gate, injection
  defense and reliability measurements. Evidence is in `docs/lab1/`.
- **Lab 2** (in progress): the backend is split into six services and containerized, the database moved from MySQL to
  MongoDB (done), Kafka (done: asynchronous applications and notifications), and Kubernetes follows. The Lab 2 assignment is `docs/lab2/Handshake_Lab2.pdf`; work and evidence go in `docs/lab2/`.
  This README describes what exists now; each Lab 2 step adds its section below.

## Pair parameters (all derived from PAIR = 06)

| Parameter | Rule | Value |
|---|---|---|
| PAIR | assigned on Canvas | **06** |
| PORT_BASE | 9000 + (PAIR x 10) | **9060** |
| Backend (FastAPI, one app: local development and the tests) | PORT_BASE | **9060** |
| Gateway (nginx, Docker: routes to the services; replaces the single app on 9060) | PORT_BASE | **9060** |
| Frontend (React dev server, or the nginx image in Docker) | PORT_BASE + 1 | **9061** |
| Student / Company / Job / Application / Event / AI Assistant services (Lab 2) | PORT_BASE + 2 ... + 7 | **9062 / 9063 / 9064 / 9065 / 9066 / 9067** |
| Database / Kafka prefix | `p{PAIR}` | **p06** (database `p06_handshake`) |
| SEED | PAIR, for every generator | **6** (`random.Random(6)`, `Faker.seed(6)`) |
| CITY_SET | assigned on Canvas | **San Jose, Sunnyvale, Mountain View** |

## What is in the repository

```
backend/            FastAPI application
  app/              routers (HTTP) -> services (logic shared with the assistant) -> mongo.py + documents.py (MongoDB)
    core/           password hashing, JWT, login sessions, login checks, safe file uploads (stored in MongoDB GridFS)
    schemas/        every request and response shape, with the validation rules
    assistant/      Part B/C: model_client.py (one Ollama client), agent.py (hand-built loop), tools.py (5 tools), confirm.py (save gate)
  services/         Lab 2: the six services. services/common.py (health, CORS, service header) and one small
                    main.py per service that mounts only the routers it owns (the code in app/ is shared)
  requirements/     Lab 2: base.txt + one file per service, so each image installs only what it needs
  docker/           Lab 2: one Dockerfile per service (Dockerfile.student ... Dockerfile.assistant)
  seed/             generate_seed.py: 50 companies, 200 students, 300 jobs, 1500 applications, 100 events, ...
  scripts/          export_api_docs.py (OpenAPI + Postman), collect_metrics.py (numbers for METRICS.md)
  tests/            pytest suite (runs on an in-memory MongoDB, never touches a real database)
frontend/           React app (pages / components / services / context / hooks / utils / test) + Dockerfile, nginx.conf
gateway/            Lab 2: nginx gateway (Dockerfile, nginx.conf) that routes each path to its service
docs/               openapi.json, postman_collection.json (API docs)
  lab1/             Lab 1 evidence: metrics, test output, transcripts, screenshots, checklist, report PDF
  lab2/             Lab 2 work (schema, Kafka contract, evidence)
METRICS.md  RUN_LOG.txt  AI_USE.md
```

## Setup (Windows PowerShell)

Requirements: Python 3.11+, Node.js 18+, Docker Desktop (to run MongoDB 7; any MongoDB 7 works).

**0. MongoDB** (one container, port 9069 on your machine so it never clashes with another MongoDB)
```powershell
docker run -d --name p06-mongo -p 9069:27017 mongo:7
```
Stop it with `docker stop p06-mongo`, start it again with `docker start p06-mongo`.

**1. Backend**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then open .env: set MONGO_URL=mongodb://localhost:9069 and a JWT_SECRET
```
`.env` is git-ignored. Never put real values in `.env.example`.

**2. Fill the database** (empties `p06_handshake` in MongoDB, creates the indexes, and seeds it; the layout is in `docs/lab2/MONGO_SCHEMA.md`)
```powershell
python -m seed.generate_seed --reset
```
Running it again gives the same data (SEED = 6; only the generated dates of birth depend on the day it runs). Demo logins (the same password for every seeded account is `Password123!`):

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

## Lab 2: the six services and Docker images

(For running everything at once, skip to "run the whole stack with Docker Compose" below.)

The Lab 1 backend is one FastAPI app. For Lab 2 it is split into six services that share the same code in
`backend/app/` but each start only their own routes (`backend/services/<name>/main.py`):

| Service | Port | Image | Endpoints it owns |
|---|---|---|---|
| Student | 9062 | `p06-student` | `/auth/student/signup`, `/auth/login`, `/auth/logout`, `/auth/me` (login serves both roles), `/students/*` (profile, activity, directory), `/students/me/preferences`, `/media/profile_pics` |
| Company | 9063 | `p06-company` | `/auth/company/signup`, `/companies/*` |
| Job | 9064 | `p06-job` | `/jobs`, `/jobs/mine`, `/jobs/{id}`, `/meta/options` |
| Application | 9065 | `p06-application` | `/jobs/{id}/apply`, `/jobs/{id}/applications`, `/applications/*` |
| Event | 9066 | `p06-event` | `/events/*` |
| AI Assistant | 9067 | `p06-assistant` | `/assistant/chat` |

The 40 Lab 1 endpoints are split with no overlap and none missing (checked by `backend/tests/test_services.py`).
Every service has `GET /health` (alive) and `GET /health/ready` (alive and MongoDB answers), and adds an `X-P06-Service` header to its
replies, so you can see who answered. The assistant also has `GET /health/dependencies`.
A token issued by one service is accepted by all of them (same JWT secret, same database).

The website still calls one address, `http://localhost:9060`. In Docker that address is the **gateway**
(`gateway/nginx.conf`), which forwards each path to the service that owns it. For example `/jobs` goes to the Job service,
but `/jobs/12/apply` goes to the Application service.

**Build the images** (PowerShell, from the repo root; Docker Desktop must be running):
```powershell
cd backend
foreach ($s in "student","company","job","application","event","assistant") {
  docker build -f docker/Dockerfile.$s -t p06-${s}:1.0.0 .
}
cd ..\gateway;  docker build -t p06-gateway:1.0.0 .
cd ..\frontend; docker build -t p06-frontend:1.0.0 --build-arg VITE_API_URL=http://localhost:9060 .
cd ..
docker images "p06-*"
```
Each image installs only its own `backend/requirements/<service>.txt`, runs as a normal user (not root), exposes its
port and has a Docker `HEALTHCHECK` that calls `/health`. `VITE_API_URL` is baked into the website at build time, so for
AWS it must be the LoadBalancer address.

**Try one service on its own** (it reports healthy without a database, because `/health` does not touch the database):
```powershell
docker run -d --name p06-student -p 9062:9062 p06-student:1.0.0
docker ps --filter name=p06-student        # STATUS becomes "healthy" after a few seconds
curl.exe -i http://localhost:9062/health   # {"status":"ok","service":"p06-student",...} and X-P06-Service: p06-student
docker logs p06-student
docker stop p06-student; docker rm p06-student
```

## Lab 2: run the whole stack with Docker Compose

`docker-compose.yml` (repo root) starts everything: MongoDB, one Kafka broker (KRaft, no ZooKeeper), the six services, the gateway
the three Kafka workers and the website, all on one network (`p06-net`), with the data kept in two named volumes (`p06-mongo-data`, `p06-kafka-data`).
Every container, image, network and volume is named `p06-...`. Each service waits (`depends_on ... service_healthy`) until
MongoDB is healthy, the gateway waits for the six services, and the website waits for the gateway.

| What | Address on your machine | Container |
|---|---|---|
| Website | http://localhost:9061 | `p06-frontend` |
| API gateway (what the website calls) | http://localhost:9060 | `p06-gateway` |
| Kafka workers: application / event / job (no address: they read Kafka) | - | `p06-application-worker`, `p06-event-worker`, `p06-job-worker` |
| Student / Company / Job / Application / Event / AI Assistant | 127.0.0.1:9062 ... 9067 (this machine only) | `p06-student` ... `p06-assistant` |
| Kafka (for tools on your machine) | localhost:9068 (inside Docker: `p06-kafka:9092`) | `p06-kafka` |
| MongoDB | 127.0.0.1:9069 (inside Docker: `p06-mongo:27017`) | `p06-mongo` |

**1. Settings.** Compose reads passwords from a file named `.env` (git-ignored; never commit it):
```powershell
copy .env.example .env        # then open .env and change MONGO_PASSWORD and JWT_SECRET
```
The MongoDB password goes into a connection URL, so use letters, digits and hyphens only. Compose refuses to start if a password is missing.

**2. Build, start, inspect, stop** (PowerShell, repo root, Docker Desktop running)
```powershell
docker compose build                      # builds the eight images p06-<name>:1.0.0
docker compose up -d                      # starts the stack; waits for every dependency to be healthy
docker compose ps                         # every container should say (healthy)
docker compose logs -f p06-student        # follow one container's log (Ctrl+C to stop following)
docker compose logs --tail 20             # the last lines of every container
docker compose exec p06-mongo mongosh -u p06admin -p <your MONGO_PASSWORD> --authenticationDatabase admin p06_handshake --eval "db.getCollectionNames()"
docker compose down                       # stop and remove the containers; the data stays in the volumes
docker compose down -v                    # ... and ALSO delete the data (MongoDB and Kafka volumes)
```

**3. Put the seed data into the stack's MongoDB** (the database starts empty; this runs from your Python environment)

On a fresh clone there is no virtual environment yet: create it first with **Setup step 1** above (`python -m venv venv`, activate it,
`pip install -r requirements.txt`). You do not need `backend\.env` or a local MongoDB container for this; the stack's MongoDB is the target.
```powershell
cd backend
.\venv\Scripts\Activate.ps1
$env:MONGO_URL = "mongodb://p06admin:<your MONGO_PASSWORD>@localhost:9069/?authSource=admin"
python -m seed.generate_seed --reset      # 50 companies, 200 students, 300 jobs, 1500 applications, ...
cd ..
```
Then open http://localhost:9061 and sign in as `demo.student@sjsu.edu` (or `demo.company@example.com`).

**4. Check that the parts reach each other**
```powershell
curl.exe -s http://localhost:9060/health                                  # the gateway
curl.exe -si http://localhost:9060/jobs/mine | Select-String "HTTP|x-p06"   # 401 from p06-job: gateway -> Job service
curl.exe -s http://127.0.0.1:9064/health/ready                            # the Job service can reach MongoDB
curl.exe -s http://127.0.0.1:9067/health/dependencies                     # the AI assistant: MongoDB, the five services, Kafka, Ollama
```
`/health` says "the process is alive" (used by Docker's HEALTHCHECK). `/health/ready` also pings MongoDB and answers 503 when it cannot
(used later as the Kubernetes readiness probe). `/health/dependencies` (assistant only) lists what the assistant can reach:
`required` = MongoDB and the five platform services, `optional` = Kafka and Ollama.

**5. Kafka: what happens when you apply** (full contract: `docs/lab2/KAFKA_CONTRACT.md`)

`POST /jobs/{id}/apply` checks the request, stores the PDF in MongoDB and puts an `application.created` event on Kafka, then answers
**202 Accepted** (not 201). The **Application worker** reads the event and saves the application a moment later (normally within
milliseconds); the website shows "received" and refreshes itself until the application appears. Three more events follow the same
pattern but the API has already saved its data: a company changing a status (`application.status_changed`), a student registering
for an event (`event.registration_created`) and a company posting a job (`job.created`). Their workers write **notifications**
(stored in MongoDB's `notifications` collection) for the student, the registered student and the students whose saved preferences fit
the new job. Every message carries an `event_id`, a `trace_id` (also in the Kafka headers) and a timestamp.
```powershell
# the topics
docker exec p06-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server p06-kafka:9092 --list
# watch a topic, with headers and keys (apply for a job in the website first)
docker exec p06-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server p06-kafka:9092 --topic p06.application.created --from-beginning --timeout-ms 5000 --property print.headers=true --property print.key=true
# has the worker read AND committed everything? (LAG 0)
docker exec p06-kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server p06-kafka:9092 --describe --group p06-application-worker
docker compose logs --tail 20 p06-application-worker              # one line per message, with its trace_id
# the dead-letter topic (messages that failed for good) should be empty
docker exec p06-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server p06-kafka:9092 --topic p06.dlq --from-beginning --timeout-ms 5000
```
A student can also replace the resume of a Pending application with `PUT /applications/{id}/resume` (202); that publishes
`application.updated`, and the worker points the application at the new PDF and removes the old one.

**The three failure demos** (idempotent consumer, a worker killed before its commit, poison messages and bounded retries) run against
the real broker with the script below; the output of a real run is in `RUN_LOG.txt` (PHASE 5), the explanation in
`docs/lab2/KAFKA_CONTRACT.md` section 7, and the architecture diagram in `docs/lab2/ARCHITECTURE.md`.
```powershell
cd backend; .\venv\Scripts\Activate.ps1          # the stack must be running and seeded; the MongoDB login is read from the root .env
python -m scripts.kafka_demos idempotent          # also: crash | poison | retries | all
```
Without Kafka (`uvicorn app.main:app` on a laptop, and all the unit tests) `KAFKA_BOOTSTRAP` is not set and the same handler runs
inline, inside the API, so the website still works; the answer is still 202.

**Notes**
* **Ollama** runs on your machine, not in Docker. The assistant container reaches it at `http://host.docker.internal:11434`. Ollama listens only
  on 127.0.0.1 by default; if `/health/dependencies` says `"ollama": "unreachable"`, set the Windows environment variable `OLLAMA_HOST=0.0.0.0`
  and restart Ollama.
* **Ports already in use?** Stop whatever uses them (`npm run dev` uses 9061, `uvicorn` 9060, a `docker run` MongoDB 9069 and the name `p06-mongo`).
  The Compose stack and the "run it by hand" setup above are alternatives, not a pair.
* **Images for AWS:** the images are named `p06-<service>:<TAG>` (TAG defaults to 1.0.0) so they are easy to retag for ECR,
  for example `docker tag p06-job:1.0.0 <account>.dkr.ecr.<region>.amazonaws.com/p06-job:1.0.0`.

## Lab 2: Kubernetes (kind on your machine)

The same eight images run in Kubernetes, in the namespace **`p06-handshake`**: MongoDB and Kafka as StatefulSets with volumes, the six
services and three Kafka workers as Deployments, the gateway and the website as Deployments with NodePort Services (on kind). The
manifests are in `k8s/` (no passwords in them: the Secret is created from your git-ignored `.env`). The full guide, what each file is, how the
pods find each other, and notes for the AWS deployment are in **`k8s/README.md`**. The short version (Windows PowerShell, repo root, Docker
Desktop running, `kind` installed with `winget install Kubernetes.kind`, Compose stopped because both use ports 9060 and 9061):

```powershell
docker compose stop
kind create cluster --config k8s/kind-config.yaml
python k8s/load_images.py
kubectl apply -f k8s/base/namespace.yaml
python k8s/create_secret.py
kubectl apply -k k8s/overlays/local
kubectl -n p06-handshake get pods                 # about one minute until all 18 are 1/1 Running
# seed the database once: see k8s/README.md, step 5
curl.exe http://localhost:9060/health             # the gateway; the website is http://localhost:9061
kind delete cluster --name p06-handshake; docker compose start       # when you are done
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
  (magic bytes, 2 MB). File names are generated by the server. Files are stored in MongoDB (GridFS), so no container needs a
  disk. Resumes are **private**: they live in their own bucket and are served only through
  `GET /applications/{id}/resume` to the applicant and the owning company, with `Cache-Control: private, no-store`.
  Pictures are public by design (`GET /media/profile_pics/{name}`).
- **Sessions (Lab 2):** every login creates a session document in MongoDB; the JWT is accepted only while it exists.
  Signing out deletes it (the token stops working at once) and MongoDB deletes expired sessions itself (TTL index, 8 hours).
  Passwords stay bcrypt hashes. Important actions are written to an `activity_logs` collection.
- **Views by role:** a company sees a student's contact details and GPA but never the date of birth; another student sees
  only name, college, major, skills, objective and experience (no email, phone, GPA, date of birth or home city).
- **Errors:** database errors become a generic 500 without internal details; validation errors name the field.
- **Race conditions:** unique indexes (one application per student and job, one registration per student and event,
  one preferences document per student, one account per email) are the final guard, and the API turns a violation
  into a clean 409.
- **Secrets:** `.env` is git-ignored; there are no API keys in the code; the JWT secret comes from the environment.

## How the assistant plugs in

`POST /assistant/chat` takes `{ "message", "conversation_id" }` and returns `{ "reply", "conversation_id", "tool_calls" }`.
`run_assistant()` in `backend/app/services/assistant.py` keeps one in-memory conversation per `conversation_id` and hands
the work to the hand-built loop in `backend/app/assistant/agent.py` (no agent framework, at most 6 model calls per
message). The only code that talks to Ollama is `OllamaClient.complete(messages, tools)` in `model_client.py`
(default model `qwen3:8b`). The five tools live in `tools.py`: `get_student_preferences`, `search_jobs`,
`get_job_details`, `search_events` and `save_job_or_event`. They call the same service functions as the website
(`services/jobs.py`, `services/events.py`, `services/preferences.py`), so the assistant and the website always agree on
what "matching" means. Every tool returns a string and never raises. `save_job_or_event` is the only tool that changes
data: it asks the student in chat first and saves only after an explicit yes (`confirm.py`).

Real transcripts of the five required queries: `docs/lab1/part_b_transcripts.txt`. Those and the other Lab 1 experiment
scripts (`scripts/run_transcripts.py`, `scripts/run_part_c.py`, `scripts/collect_metrics.py`) were written for the MySQL data
layer and do not run on the MongoDB version; their Lab 1 outputs are in `docs/lab1/`, and `git checkout lab1` gives the code
that produced them.

### Safety and reliability (Part C)

- **Confirmation gate:** `confirm_action(tool_name, arguments, auto_approve=False)` in `assistant/confirm.py`. Only an
  explicit "yes" lets `save_job_or_event` run; a "no" returns a `CANCELLED` string, and the loop never asks twice for
  the same declined save. Read-only tools are not gated.
- **Prompt-injection defense:** job and event text written by companies is wrapped in
  `<<<UNTRUSTED_DATABASE_CONTENT ...>>>` markers (`mark_untrusted` in `tools.py`), and the system prompt says that text
  between the markers is data, never instructions. Measured result: on the two local models tested it did **not**
  reduce the number of successful injections; the confirmation gate is what kept the data safe (see `METRICS.md`, C2).
- **Repair path:** a bad tool name, bad arguments, a text answer where a tool was needed, or a lost multi-step chain is
  re-prompted once with the specific error, then the loop stops cleanly (`MAX_REPAIRS = 1` in `agent.py`).
- Run the experiments with `python -m scripts.run_part_c gate`, `injection` or `reliability` (from `backend/`; the model
  comes from the `OLLAMA_MODEL` environment variable). The injection run inserts one poisoned job and deletes it again.

### Lab 2: guardrails and the evaluation harness (Part 6)

The eight guardrails are listed at the top of `backend/app/assistant/guardrails.py` with the place each one lives
(allowlist, schema validation, authorization, confirmation, injection defense, secret and privacy filter, bounded
execution with a request deadline and one tool retry, grounded answers).

Run the harness with one command (from `backend/`, with the venv active; it needs no Ollama and no MongoDB server):

```powershell
python -m scripts.agent_harness
```

A scripted model plays the language model; the agent loop, guardrails, validation and tools are the production code, on
an in-memory MongoDB. It runs 16 cases (read-only search, accepted and declined save, malformed arguments, unknown tool,
no match, history follow-up, injection before and after the defense, iteration ceiling, timeout, one retry, secrets,
privacy, invented ids, authorization) plus a before/after-repair comparison. Output: `docs/lab2/agent_harness.json`
(every record) and `docs/lab2/agent_harness_summary.md` (the tables). The harness supplements the real Ollama
transcripts and does not replace them.

## Testing

- Backend: `python -m pytest -q` runs the full API suite on an in-memory MongoDB (authentication and sessions, profiles,
  jobs, applications, resumes, events, directory, preferences, assistant endpoint, the Lab 2 service split and the
  MongoDB data layer).
- Frontend: `npm test` (Vitest + Testing Library + a fake server) covers every page, form checks, loading and error
  states, and the role-based routing.
- Numbers for the latest run are in `METRICS.md`.

## Known limitations (honest list)

- `npm audit` reports a few advisories in development tools (Vite/esbuild dev server); they do not ship in the built site.
- The login token is kept in `localStorage` (simple and common for a course project; an HttpOnly cookie would resist
  script injection better). There are no refresh tokens or password reset.
- Uploaded files live on the local disk of the API server (`uploads/`), not in object storage.
- Search uses regular expressions on MongoDB, not a full-text index; at this data size every query answers in milliseconds (see METRICS.md).

## Partners

- Uday: Lab 1 Part A (platform, API, database, seed data, website). Lab 2: Docker images, Docker Compose, Kubernetes
  manifests, Kafka, MongoDB migration.
- Sreeramachandra Sai Achutuni: Lab 1 Parts B and C (assistant, safety, reliability). Lab 2: AWS (ECR and EKS),
  assistant memory, Redux, JMeter, context management and guardrails.
