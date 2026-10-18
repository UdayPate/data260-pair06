# METRICS: Lab 1

Machine for these runs: Lenovo Legion Slim 5 (Ryzen 5 7640HS, 16 GB RAM, RTX 4060 8 GB), Windows, MySQL 8 local.
Pair 06, SEED 6, PORT_BASE 9060.

<!-- PART A: paste the output of `python -m scripts.collect_metrics --with-tests` here (it is also saved in docs/part_a_metrics.md) -->

### Part A: platform (collected 2026-10-08 23:17)

Pair 06, SEED 6, cities San Jose, Sunnyvale, Mountain View, backend port 9060.

#### Seed data (MySQL row counts)

| Table | Rows | Required | Met |
|---|---:|---:|:---:|
| Companies | 50 | 50 | yes |
| Students | 200 | 200 | yes |
| Job postings | 300 | 300 | yes |
| Applications | 1500 | 1500 | yes |
| Events | 100 | 100 | yes |
| Event registrations | 400 | - | yes |
| Saved preferences | 151 | - | yes |
| Saved items | 150 | - | yes |
| Student skills | 877 | - | yes |
| Job skills | 1073 | - | yes |

#### API latency (each call repeated 30 times, local machine, milliseconds)

| Request | Status | Median | p95 | Slowest |
|---|:---:|---:|---:|---:|
| GET /jobs (no filter) | 200 | 16.7 | 21.0 | 35.1 |
| GET /jobs?q=data | 200 | 16.1 | 17.9 | 33.6 |
| GET /jobs (internship + city + remote) | 200 | 14.0 | 15.6 | 17.3 |
| GET /jobs (skills Python + SQL, all) | 200 | 15.2 | 20.8 | 85.7 |
| GET /jobs/1 | 200 | 10.4 | 11.4 | 23.8 |
| GET /events | 200 | 16.4 | 18.7 | 35.5 |
| GET /students?q=a (peer view) | 200 | 17.2 | 18.5 | 24.2 |
| GET /applications/mine | 200 | 10.0 | 11.6 | 15.0 |
| GET /students/me | 200 | 7.8 | 8.5 | 20.6 |
| GET /students/me/preferences | 200 | 7.2 | 7.8 | 9.4 |
| GET /meta/options | 200 | 1.7 | 2.2 | 2.9 |
| GET /jobs/mine (company) | 200 | 12.1 | 14.0 | 14.4 |
| GET /jobs/213/applications (company) | 200 | 10.3 | 11.4 | 12.1 |
| GET /events/mine (company) | 200 | 11.1 | 12.0 | 22.0 |
| GET /students (company view) | 200 | 16.6 | 18.3 | 19.7 |

Login (bcrypt, deliberately slow): median 375 ms over 5 logins.

## Frontend tests
Frontend (Vitest): 14 test files, 148 tests passed, 16.69 s.
Backend (pytest): 346 passed, 1 warning, 216.73 s.

<!-- PART B / PART C: your partner adds the assistant numbers below (tool-call success rate, latency per turn,
     tokens, injection results) -->

## Part B: assistant

Source: `docs/part_b_transcripts.txt`, produced by `python -m scripts.run_transcripts` against the seeded MySQL
database `p06_handshake`, model `qwen3:8b` (Ollama, temperature 0), demo student, run date 2026-10-16.
An earlier run before the system-prompt fix is kept in `docs/part_b_transcripts_run1_before_prompt_fix.txt`.

| Test | Student message | Tool calls | Model calls | Seconds | Tool errors |
|---|---|---|---|---|---|
| 1 | Find an internship in my city. | 2 (`get_student_preferences`, `search_jobs`) | 3 | 326 | 0 |
| 2 | Find a remote data science internship. | 1 (`search_jobs`) | 2 | 117 | 0 |
| 3 | Find an event for computer science students next month. | 1 (`search_events`) | 2 | 1544 | 0 |
| 4 | Make it closer or higher paying. (follow-up to test 2) | 1 (`search_jobs`) | 2 | 125 | 0 |
| 5 | Find me a job at Hooli Quantum Falconry. | 1 (`search_jobs`) | 2 | 31 | 0 |
| Total | | 6 | 11 | 2143 | 0 |

- All 6 tool calls returned a normal result (no `Error:` string), and no run hit the iteration ceiling (limit 6 model
  calls per message).
- Test 3 took 1544 s, far longer than the others. The cause was not investigated, so no explanation is given here.
- Not covered by these five queries: `get_job_details` and `save_job_or_event` (saving is gated and belongs to Part C).
- Unit tests for the loop, tools and model client use a fake model: `backend/tests/test_agent.py` and
  `test_assistant.py`, 43 tests passed (5.31 s).
- Full backend suite after adding Part B: 394 passed, 1 warning, 447.46 s (346 from Part A plus the new assistant tests).
- Token counts were not recorded.

## Part C: safety and reliability

_Partner fills in._
