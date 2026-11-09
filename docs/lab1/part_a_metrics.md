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
