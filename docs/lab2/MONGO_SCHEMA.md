# MongoDB schema (Pair 06, Lab 2)

Database **`p06_handshake`** on MongoDB 7. Every service reads and writes it through `backend/app/mongo.py`
(the driver is `pymongo`). The connection string is the environment variable `MONGO_URL`
(default `mongodb://localhost:27017`; in Kubernetes it comes from a Secret). `MONGO_DB_NAME` overrides the database name.

This file is the reference for the assistant-memory work (Part 3, partner): it lists every collection, every field,
every index, and the conventions to follow when you add yours.

## 1. Conventions (read these first)

| Topic | Rule |
|---|---|
| Ids | Whole numbers, not ObjectId. Every new document gets the next id of its collection from the `counters` collection (`mongo.next_id` / `mongo.insert`). The URLs (`/jobs/12`), the website and the assistant tools all rely on integer ids. A failed insert (duplicate key) skips its id, so ids can have gaps. |
| Dates | A date (no time) is stored as text `"2026-10-05"` (readable in a viewer, sorts correctly). A date-time is a real MongoDB date. `mongo.load()` turns the text back into Python dates, `mongo.dump()` does the reverse. Fields stored as text dates: `students.date_of_birth`, `students.experiences[].start_date/end_date`, `jobs.posting_date`, `jobs.deadline`. |
| Time zones | `sessions.*` and `activity_logs.at` are **UTC** (MongoDB's expiry clock is UTC). The business timestamps (`created_at`, `updated_at`, `applied_at`, `registered_at`, `saved_at`, `event_datetime`) are the server's wall-clock time stored without a zone, exactly as in Lab 1 (an event at 14:00 means 14:00 local). In the Docker images the clock is UTC. |
| Enums | Stored as their text: `category` = `full_time` / `part_time` / `on_campus` / `internship`; `pay_period` = `hourly` / `yearly`; `status` = `Pending` / `Reviewed` / `Declined`; `item_type` = `job` / `event`. |
| Embedding | Things that never exist without their parent are inside it: a student's `skills` and `experiences`, a job's `skills`, an event's `eligible_majors`. Things that are looked up on their own (applications, registrations, saved items, preferences) are separate collections that point at their parents by id. |
| Derived fields | Lower-case or pre-computed copies used only for searching and sorting: `students.name_lower`, `students.skills_lower`, `jobs.skills_lower`, `jobs.salary_yearly_max`, `events.eligible_majors_lower`. Always written together with the field they come from (`documents.derived()`); never edit them by hand. |
| New documents | Build them with the functions in `backend/app/documents.py` (`documents.student(...)`, `documents.job(...)`...). They set every field, fill the derived ones and refuse unknown or missing fields. |
| Files | Resumes and profile pictures are stored in MongoDB (GridFS), not on a disk, so every service container stays stateless. |
| Deletes | The API never deletes accounts, jobs, events or applications, so there are no cascading deletes (Lab 1's SQL cascade rules are not needed). It does delete: sessions (sign-out, expiry), preferences, event registrations, replaced profile pictures. |
| Search | Case-insensitive search uses regular expressions (`re.escape` is applied so a typed `%` or `.` is an ordinary character) and the lower-case derived fields. There is no text index; at this data size every query answers in milliseconds. |

## 2. Collections at a glance

| Collection | Documents (seed) | Purpose | Written by | Also read by |
|---|---:|---|---|---|
| `students` | 200 | student account + profile (skills and experience inside) | Student service | all services (login check, role views), Assistant |
| `companies` | 50 | company account + profile | Company service | all services (job/event cards) |
| `jobs` | 300 | job postings (skills inside) | Job service | Application, Student (heatmap), Assistant |
| `applications` | 1,500 | one application per student and job | the **Application worker** (from the Kafka event `application.created`); the Application service only changes the status | Job (applicant counts), Student (heatmap), Company views |
| `events` | 100 | events (eligible majors inside) | Event service | Assistant |
| `event_registrations` | 400 | one registration per student and event | Event service | Event, Student views |
| `student_preferences` | 151 | saved job and event preferences (one per student) | Student service | Assistant (`get_student_preferences`) |
| `saved_items` | 150 | jobs and events a student saved | Assistant (`save_job_or_event`, after the student confirms) | Assistant |
| `sessions` | 0 | one document per login; expires by itself | login/signup (Student and Company services) | every service (checks the token) |
| `activity_logs` | 0 | what users did (audit trail) | every service and the Application worker | - |
| `notifications` | 0 | short messages for users, written by the Kafka workers (status change, event registration, a new job that fits a student's preferences) | Application, Event and Job workers | (no endpoint shows them yet) |
| `counters` | 9 | the next integer id per collection | `mongo.next_id` | - |
| `resumes.files`, `resumes.chunks` | 1 | GridFS bucket `resumes`: private resume PDFs (the seed stores ONE placeholder PDF that all 1,500 seeded applications share) | Application service | Application service only |
| `profile_pics.files`, `profile_pics.chunks` | 0 | GridFS bucket `profile_pics`: public pictures and company logos | Student and Company services | `GET /media/profile_pics/{name}` |

The Lab 1 MySQL tables map like this: `students`, `student_skills`, `student_experience` -> `students`; `jobs`, `job_skills` -> `jobs`;
`events`, `event_eligible_majors` -> `events`; `student_preferences`, `companies`, `applications`, `event_registrations`,
`saved_items` -> the collection of the same name. `sessions`, `activity_logs` and `counters` are new, and files moved from the
`uploads/` folder into GridFS.

Collections for the assistant memory layers (`assistant_rules`, `student_memory`, conversations) are **not defined here**: the
assistant-memory work owns their design. Follow the conventions above, add their indexes to `INDEXES` in `backend/app/mongo.py`,
and add a section to this file.

## 3. Collections in detail

Example documents come from the seeded database (long texts shortened, password hash replaced).

### `students`
```
{ _id: 1, name: "Demo Student", name_lower: "demo student", email: "demo.student@sjsu.edu",
  password_hash: "$2b$12$...", college: "San Jose State University", date_of_birth: "1998-07-06",
  city: "San Jose", state: "CA", country: "United States", career_objective: "Seeking opportunities in data science...",
  degree: "MS", major: "Data Science", graduation_year: 2027, cgpa: 2.83, phone: "(408) 361-5350",
  profile_pic_path: "profile_pics/student_1_6ee37d3453d5.png" | null,
  skills: ["Python", "Machine Learning"], skills_lower: ["python", "machine learning"],
  experiences: [ { id: 198, title: "TA", company: "SJSU", start_date: "2024-01-01", end_date: null, description: null } ],
  created_at: ISODate(...) }
```
`email` is stored lower-case (the request schemas normalise it). `password_hash` is a bcrypt hash and is never returned by any endpoint.
`experiences[].id` comes from the `student_experience` counter; a profile update replaces the whole list.
`profile_pic_path` is `profile_pics/<file name>`, the name of the file in the `profile_pics` GridFS bucket.

### `companies`
```
{ _id: 1, name: "Demo Analytics Co", email: "demo.company@example.com", password_hash: "$2b$12$...", city: "San Jose",
  state: "CA", industry: "Financial Services", description: "...", contact_email: "...", contact_phone: "(408) 093-5738",
  website: "https://www.demo.example.com", profile_pic_path: null, created_at: ISODate(...) }
```
The API calls `city` "location".

### `jobs`
```
{ _id: 1, company_id: 30, title: "Data Science Intern", description: "...", category: "internship", city: "Sunnyvale",
  state: "CA", is_remote: true, salary_min: 23, salary_max: 32, pay_period: "hourly", posting_date: "2026-08-30",
  deadline: "2027-03-27", contact_email: "...", skills: ["Python", "Machine Learning", "Statistics"],
  skills_lower: ["python", "machine learning", "statistics"], salary_yearly_max: 66560, created_at: ISODate(...) }
```
`salary_yearly_max` = `salary_max` x 2080 for hourly jobs (40 h x 52 weeks), `salary_max` for yearly jobs. It lets one query compare
hourly and yearly pay and sort by pay.

### `applications`
```
{ _id: 8, student_id: 1, job_id: 39, resume_file_id: ObjectId("..."), status: "Reviewed",
  applied_at: ISODate("2026-10-05T09:44:00Z"), updated_at: ISODate("2026-10-05T09:44:00Z"),
  source_event_id: null, trace_id: null }
```
`source_event_id` and `trace_id` are set when the application was created through Kafka (the `event_id` and `trace_id` of its
`application.created` message, see `KAFKA_CONTRACT.md`); they are `null` for the seeded applications.
`resume_file_id` is the id of the PDF in the `resumes` GridFS bucket (metadata there: `filename`, `content_type`, `student_id`, `job_id`).
The API never reveals it: it hands out `/applications/{id}/resume`, which checks who is asking.

### `events`
```
{ _id: 35, company_id: 50, name: "Alumni Panel: Careers in Cloud Computing", description: "...",
  event_datetime: ISODate("2026-11-06T12:00:00Z"), location: "93112 King Oval, Sunnyvale, CA", city: "Sunnyvale",
  eligible_majors: ["Computer Science"], eligible_majors_lower: ["computer science"], created_at: ISODate(...) }
```
`eligible_majors: ["All"]` means open to every major.

### `event_registrations`, `saved_items`, `student_preferences`
```
{ _id: 1, student_id: 102, event_id: 25, registered_at: ISODate(...) }
{ _id: 1, student_id: 71, item_type: "job", item_id: 65, saved_at: ISODate(...) }      // item_id points into jobs or events
{ _id: 1, student_id: 1, preferred_categories: ["internship"], preferred_cities: ["San Jose"],
  preferred_roles: ["Data Analyst"], min_hourly_rate: 25, open_to_remote: true, event_interests: ["Career Fair"],
  updated_at: ISODate(...) }
```
`min_hourly_rate` is US dollars per hour. `saved_items.item_id` has no foreign key because it points into two collections.

### `sessions` (login sessions with expiry)
```
{ _id: "af875f4beb764e75902379d50c8092c8", role: "student", user_id: 1,
  created_at: ISODate("2026-11-09T01:21:21Z"), expires_at: ISODate("2026-11-09T09:21:21Z") }
```
Every signup and login creates one (8 hours, `JWT_EXPIRE_MINUTES`). The JWT carries its id as the `jti` claim and is accepted
only while the session exists, so signing out (`POST /auth/logout`) deletes the session and the token stops working at once.
The TTL index on `expires_at` (`expireAfterSeconds: 0`) makes MongoDB delete the document itself; MongoDB checks about once a minute,
so the API also compares `expires_at` with the clock on every request.

### `activity_logs`
```
{ _id: ObjectId("..."), at: ISODate(...UTC), actor_role: "student", actor_id: 1, action: "login",
  ref_type: null, ref_id: null, detail: {} }
```
Actions written today: `signup`, `login`, `logout`, `profile_updated`, `preferences_saved`, `job_created`, `job_updated`,
`application_created` (`ref_type: "application"`, `detail: {job_id}`), `application_updated` (written by the Application worker after a resume replacement, `_id: "<event_id>:application_updated"`, `detail: {trace_id}`), `application_status_changed` (`detail: {status}`),
`event_created`, `event_updated`, `event_registered`, `event_unregistered`, `item_saved`. A failed log write is logged and
ignored; it never breaks the request. Entries written by the API use MongoDB's ObjectId as `_id`. **`application_created` is
written by the Application worker**, with `_id: "<event_id>:application_created"`, so the same Kafka event can never write it
twice.

### `notifications`
```
{ _id: "0b6f3d0e-6c0c-4a53-9f0a-2c7c1e4a8d11:student:12", user_role: "student", user_id: 12, kind: "application_status",
  title: "Application update: Data Analyst", body: "Acme changed the status of your application from Pending to Reviewed.",
  ref_type: "application", ref_id: 7, source_event_id: "0b6f3d0e-...", trace_id: "b5d4a0f1c2e34d6f9a1b3c5d7e9f0a12",
  created_at: ISODate(...UTC), read: false }
```
Written by the Kafka workers. `kind` is `application_status`, `event_registration` or `new_job_match`. The `_id` is a **text** made of the
Kafka `event_id`, the role and the user id (the one collection that does not use integer ids): the same event cannot create the
same notification twice, which is what makes the workers idempotent.

### `counters`
```
{ _id: "jobs", seq: 301 }          // the last id handed out for the collection "jobs"
```
One document per collection, increased atomically with `find_one_and_update($inc)`. `student_experience` is the counter for
`students.experiences[].id`. The seed script sets each counter to the number of seeded documents.

## 4. Indexes

Defined in one list, `INDEXES` in `backend/app/mongo.py`, and created when a service starts and by the seed script
(`mongo.ensure_indexes`, safe to run again).

| Collection | Index | Kind | Why |
|---|---|---|---|
| `students` | `email` | **unique** | one account per email (the race-safe version of the duplicate check) |
| `students` | `name_lower`; `major`; `skills_lower` | normal | directory sorting and filters |
| `companies` | `email` | **unique** | one account per email |
| `jobs` | `company_id`; `deadline`; `(posting_date desc, _id desc)`; `category`; `skills_lower`; `salary_yearly_max desc` | normal | search, "my postings", sorting |
| `applications` | `(student_id, job_id)` | **unique** | one application per student and job (stops a double click) |
| `applications` | `job_id`; `(student_id, applied_at desc)` | normal | applicants of a job; my applications; the heatmap |
| `events` | `company_id`; `event_datetime`; `eligible_majors_lower` | normal | event search, earliest first |
| `event_registrations` | `(student_id, event_id)` | **unique** | one registration per student and event |
| `event_registrations` | `event_id` | normal | registrations of an event, counts |
| `saved_items` | `(student_id, item_type, item_id)` | **unique** | a student cannot save the same item twice |
| `student_preferences` | `student_id` | **unique** | one preferences document per student |
| `sessions` | `expires_at` | **TTL** (`expireAfterSeconds: 0`) | MongoDB deletes expired sessions |
| `sessions` | `(user_id, role)` | normal | find a user's sessions |
| `activity_logs` | `(actor_role, actor_id, at desc)`; `action` | normal | a user's history; counting an action |
| `notifications` | `(user_role, user_id, created_at desc)` | normal | a user's notifications, newest first |

A violated unique index raises `pymongo.errors.DuplicateKeyError`; the API turns it into **409 Conflict**.

## 5. Security

* Passwords are hashed with **bcrypt** (12 rounds) before they are stored. No endpoint returns `password_hash`.
* A role view never leaks: a company sees a student's email, phone and GPA but never `date_of_birth`; a student sees peers
  without email, phone, GPA, date of birth or city. These rules live in the Pydantic response models, not in the collections.
* Resumes are private: they live in a GridFS bucket that only `GET /applications/{id}/resume` reads, after checking that the
  caller is the applicant or the company that owns the job (anyone else gets 404). Profile pictures are public by design.
* The connection string (it may contain a MongoDB password) is never in the code or the images: only `MONGO_URL`.

## 6. Seeding and checking

```powershell
cd backend
$env:MONGO_URL = "mongodb://localhost:9069"        # the local MongoDB container used while developing
python -m seed.generate_seed --reset               # empties every collection, creates the indexes, seeds again
```
Counts after seeding (the same numbers as Lab 1): companies 50, students 200, jobs 300, applications 1,500, events 100,
event_registrations 400, student_preferences 151, saved_items 150, student skills 877, job skills 1,073 (inside the documents).
`SEED = 6` for every random choice. The generated dates of birth depend on the day the seed runs (Faker computes ages from
today's date); nothing else does.

Quick look with the MongoDB shell: `docker exec p06-mongo mongosh p06_handshake --eval "db.getCollectionNames()"`.
