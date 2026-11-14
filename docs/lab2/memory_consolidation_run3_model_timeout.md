# Memory consolidation: before and after

Run on 2026-11-14 02:44:02 with `python -m scripts.memory_demo`. Model: **qwen3:8b** (real Ollama, not scripted). Database: in-memory mongomock (no MongoDB server was reachable). The consolidation handler is the same function the Kafka worker runs; here the message was handed to it directly, without a Kafka broker.

**62 notes before, 30 after** (1171.2 s). Model calls: 5 (one per category with two or more notes); every answer readable: False.

## Checks

| Check | Result | Detail |
|---|---|---|
| started with at least 60 notes | PASS | 62 notes |
| ended below 40 notes | PASS | 30 notes |
| no exact duplicate is left | PASS | 0 duplicate(s) left |
| duplicate dup1 merged to at most one note | PASS | 1 of 2 copies left |
| duplicate dup2 merged to at most one note | PASS | 1 of 2 copies left |
| duplicate dup3 merged to at most one note | PASS | 1 of 2 copies left |
| contradiction old1 vs new1 resolved in favour of the newer note | PASS | old note removed, newer note kept |
| contradiction old2 vs new2 resolved in favour of the newer note | PASS | old note removed, newer note kept |
| contradiction old3 vs new3 resolved in favour of the newer note | FAIL | BOTH notes are still there (unresolved) |

## Decisions

| Kind | Notes | Accepted | What | Why rejected |
|---|---|---|---|---|
| duplicate | [2, 1] | yes | kept 2, removed copies [1] |  |
| duplicate | [4, 3] | yes | kept 4, removed copies [3] |  |
| duplicate | [6, 5] | yes | kept 6, removed copies [5] |  |
| merge | [13, 14, 15, 16, 17, 18] | yes | merged into: Interested in data science |  |
| merge | [19, 20, 21, 23] | yes | merged into: Knows SQL and can write SQL queries |  |
| contradiction | [8, 7] | yes | kept 8 (Wants on-site jobs in San Jose and no remote work); dropped the older 7 (Wants only remote jobs) |  |
| contradiction | [6, 57] | yes | kept 6 (Prefers internships over full-time jobs); dropped the older 57 (Prefers small companies) |  |
| merge | [24, 27, 28, 25] | yes | merged into: Prefers to work in San Jose |  |
| fallback_cap | [47, 44, 58, 26, 42, 41, 40, 39, 55, 36, 9, 35, 32, 31, 30, 29] | yes | still over 39 notes: kept the newest 4 of each category, removed 16 |  |

## Paraphrase groups

```
{
 "A": {
  "original_notes": 6,
  "originals_left": 0,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "B": {
  "original_notes": 5,
  "originals_left": 1,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "C": {
  "original_notes": 5,
  "originals_left": 0,
  "decision_kinds_that_touched_them": [
   "fallback_cap",
   "merge"
  ]
 },
 "D": {
  "original_notes": 6,
  "originals_left": 2,
  "decision_kinds_that_touched_them": [
   "fallback_cap"
  ]
 },
 "E": {
  "original_notes": 4,
  "originals_left": 2,
  "decision_kinds_that_touched_them": [
   "fallback_cap"
  ]
 },
 "S": {
  "original_notes": 24,
  "originals_left": 15
 }
}
```

## Memory before

```
 13 | 2026-08-03 | interest    | Interested in data science
  1 | 2026-08-05 | skill       | Knows Python
 19 | 2026-08-07 | skill       | Knows SQL
 60 | 2026-08-08 | note        | Likes short answers
 24 | 2026-08-09 | preference  | Prefers jobs in San Jose
 39 | 2026-08-10 | skill       | Knows React
  7 | 2026-08-12 | preference  | Wants only remote jobs
 35 | 2026-08-14 | constraint  | Available 15 hours a week
 44 | 2026-08-16 | goal        | Wants to become a data engineer
  3 | 2026-08-18 | interest    | Interested in machine learning
 57 | 2026-08-19 | preference  | Prefers small companies
  9 | 2026-08-20 | constraint  | Needs a minimum pay of $25 per hour
 40 | 2026-08-22 | skill       | Uses Git every day
 14 | 2026-08-25 | interest    | Likes data science work
 47 | 2026-08-28 | interest    | Interested in healthcare analytics
 20 | 2026-08-30 | skill       | Comfortable writing SQL queries
 25 | 2026-08-31 | preference  | Wants to work near San Jose
  5 | 2026-09-01 | preference  | Prefers internships over full-time jobs
 11 | 2026-09-02 | goal        | Is majoring in Computer Science
 50 | 2026-09-03 | application | Applied to a Data Analyst internship at Acme Data
 41 | 2026-09-04 | skill       | Has built dashboards in Tableau
 36 | 2026-09-06 | constraint  | Can work about 15 hours weekly
 45 | 2026-09-08 | goal        | Wants to work at a startup
 15 | 2026-09-09 | interest    | Wants to work in data science
 55 | 2026-09-10 | constraint  | Cannot work on Tuesday evenings because of classes
 29 | 2026-09-12 | event       | Attended the fall career fair
 30 | 2026-09-12 | event       | Went to the SJSU fall career fair
 31 | 2026-09-13 | event       | Visited the career fair in the fall
 32 | 2026-09-13 | event       | Was at the fall career fair on campus
 33 | 2026-09-14 | event       | Walked the fall career fair and met recruiters
 34 | 2026-09-14 | event       | Fall career fair attendance
 21 | 2026-09-15 | skill       | Has used SQL in class projects
 61 | 2026-09-17 | note        | Prefers bullet points when comparing jobs
 42 | 2026-09-19 | skill       | Can write basic Java
 26 | 2026-09-20 | preference  | Lives in San Jose and wants a short commute
 48 | 2026-09-22 | interest    | Interested in cloud computing
 51 | 2026-09-24 | application | Applied to a Software Engineer internship at Globex
 58 | 2026-09-26 | preference  | Likes jobs that use Python daily
 37 | 2026-09-27 | constraint  | Only free 15 hours per week during the semester
 16 | 2026-09-28 | interest    | Data science is a favorite topic
 54 | 2026-09-30 | event       | Went to the resume workshop on campus
  2 | 2026-10-02 | skill       | Knows Python
 22 | 2026-10-05 | skill       | SQL is one of their strongest skills
 53 | 2026-10-06 | event       | Registered for the Women in Tech panel
 27 | 2026-10-08 | preference  | San Jose is the preferred location
 43 | 2026-10-09 | skill       | Strong with Excel pivot tables
  4 | 2026-10-11 | interest    | Interested in machine learning
 52 | 2026-10-13 | application | Applied to a data internship at Initech
 17 | 2026-10-14 | interest    | Enjoys data science projects
 46 | 2026-10-15 | goal        | Plans to apply to graduate school in 2028
 38 | 2026-10-18 | constraint  | Part-time availability of 15 hours per week
  8 | 2026-10-20 | preference  | Wants on-site jobs in San Jose and no remote work
 49 | 2026-10-21 | interest    | Likes contributing to open source
 56 | 2026-10-23 | constraint  | Needs the application deadline to be at least a week away
 10 | 2026-10-25 | constraint  | Needs a minimum pay of $40 per hour
 59 | 2026-10-26 | preference  | Prefers a mentor on the team
 23 | 2026-10-28 | skill       | Can write joins and aggregations in SQL
 28 | 2026-10-29 | preference  | Looking for roles in the San Jose area
  6 | 2026-10-30 | preference  | Prefers internships over full-time jobs
 62 | 2026-10-31 | note        | Reads email in the morning
 12 | 2026-11-01 | goal        | Switched major to Data Science
 18 | 2026-11-03 | interest    | Curious about data science careers
```

## Memory after

```
 60 | 2026-08-08 | note        | Likes short answers  [seed]
 11 | 2026-09-02 | goal        | Is majoring in Computer Science  [seed]
 50 | 2026-09-03 | application | Applied to a Data Analyst internship at Acme Data  [seed]
 45 | 2026-09-08 | goal        | Wants to work at a startup  [seed]
 33 | 2026-09-14 | event       | Walked the fall career fair and met recruiters  [seed]
 34 | 2026-09-14 | event       | Fall career fair attendance  [seed]
 61 | 2026-09-17 | note        | Prefers bullet points when comparing jobs  [seed]
 48 | 2026-09-22 | interest    | Interested in cloud computing  [seed]
 51 | 2026-09-24 | application | Applied to a Software Engineer internship at Globex  [seed]
 37 | 2026-09-27 | constraint  | Only free 15 hours per week during the semester  [seed]
 54 | 2026-09-30 | event       | Went to the resume workshop on campus  [seed]
  2 | 2026-10-02 | skill       | Knows Python  [seed]
 22 | 2026-10-05 | skill       | SQL is one of their strongest skills  [seed]
 53 | 2026-10-06 | event       | Registered for the Women in Tech panel  [seed]
 43 | 2026-10-09 | skill       | Strong with Excel pivot tables  [seed]
  4 | 2026-10-11 | interest    | Interested in machine learning  [seed]
 52 | 2026-10-13 | application | Applied to a data internship at Initech  [seed]
 46 | 2026-10-15 | goal        | Plans to apply to graduate school in 2028  [seed]
 38 | 2026-10-18 | constraint  | Part-time availability of 15 hours per week  [seed]
  8 | 2026-10-20 | preference  | Wants on-site jobs in San Jose and no remote work  [seed]
 49 | 2026-10-21 | interest    | Likes contributing to open source  [seed]
 56 | 2026-10-23 | constraint  | Needs the application deadline to be at least a week away  [seed]
 10 | 2026-10-25 | constraint  | Needs a minimum pay of $40 per hour  [seed]
 59 | 2026-10-26 | preference  | Prefers a mentor on the team  [seed]
 64 | 2026-10-28 | skill       | Knows SQL and can write SQL queries  [consolidation]
 65 | 2026-10-29 | preference  | Prefers to work in San Jose  [consolidation]
  6 | 2026-10-30 | preference  | Prefers internships over full-time jobs  [seed]
 62 | 2026-10-31 | note        | Reads email in the morning  [seed]
 12 | 2026-11-01 | goal        | Switched major to Data Science  [seed]
 63 | 2026-11-03 | interest    | Interested in data science  [consolidation]
```
