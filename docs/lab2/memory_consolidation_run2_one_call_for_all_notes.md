# Memory consolidation: before and after

Run on 2026-11-14 02:21:46 with `python -m scripts.memory_demo`. Model: **qwen3:8b** (real Ollama, not scripted). Database: in-memory mongomock (no MongoDB server was reachable). The consolidation handler is the same function the Kafka worker runs; here the message was handed to it directly, without a Kafka broker.

**62 notes before, 34 after** (445.2 s). Model used: True; its answer was readable: True.

## Checks

| Check | Result | Detail |
|---|---|---|
| started with at least 60 notes | PASS | 62 notes |
| ended below 40 notes | PASS | 34 notes |
| no exact duplicate is left | PASS | 0 duplicate(s) left |
| duplicate dup1 merged to at most one note | PASS | 1 of 2 copies left |
| duplicate dup2 merged to at most one note | PASS | 1 of 2 copies left |
| duplicate dup3 merged to at most one note | PASS | 1 of 2 copies left |
| contradiction old1 vs new1 resolved in favour of the newer note | FAIL | BOTH notes are still there (unresolved) |
| contradiction old2 vs new2 resolved in favour of the newer note | PASS | old note removed, newer note kept |
| contradiction old3 vs new3 resolved in favour of the newer note | FAIL | both notes are gone (the newer fact was lost) |

## Decisions

| Kind | Notes | Accepted | What | Why rejected |
|---|---|---|---|---|
| duplicate | [2, 1] | yes | kept 2, removed copies [1] |  |
| duplicate | [4, 3] | yes | kept 4, removed copies [3] |  |
| duplicate | [6, 5] | yes | kept 6, removed copies [5] |  |
| merge | [13, 14, 15] | yes | merged into: Interested in data science and related fields |  |
| merge | [19, 39, 20, 21, 22, 23] | yes | merged into: Knows SQL and is comfortable writing SQL queries |  |
| merge | [24, 25, 26, 28] | yes | merged into: Prefers jobs in San Jose with a short commute |  |
| merge | [35, 36, 37, 38] | yes | merged into: Available 15 hours per week for work |  |
| merge | [44, 45, 56] | NO | Wants to become a data engineer, work at a startup, and apply to graduate school in 2028 | the notes are in different categories, so they are not the same fact |
| merge | [57, 27, 58, 28, 6] | NO | Prefers small companies, San Jose, and internships over full-time jobs | an id was used twice |
| merge | [50, 51, 52] | yes | merged into: Applied to data analyst, software engineer, and data internships |  |
| merge | [53, 54] | yes | merged into: Attended resume workshop and registered for Women in Tech panel |  |
| merge | [29, 30, 31, 32, 33, 34] | yes | merged into: Attended fall career fair and met recruiters |  |
| merge | [40, 41, 42, 43, 46, 59] | NO | Uses Git, built dashboards in Tableau, can write basic Java, strong with Excel pivot tables, and prefers a mentor on the team | the notes are in different categories, so they are not the same fact |
| merge | [11, 12] | yes | merged into: Is majoring in Computer Science and switched to Data Science |  |
| contradiction | [7, 8] | NO |  | the note it kept is OLDER than a note it dropped (the newer note must win) |
| contradiction | [10, 9] | yes | kept 10 (Needs a minimum pay of $40 per hour), dropped [9] |  |
| drop | [61] | yes | dropped one-off note: Prefers bullet points when comparing jobs |  |
| drop | [62] | yes | dropped one-off note: Reads email in the morning |  |

## Paraphrase groups

```
{
 "A": {
  "original_notes": 6,
  "originals_left": 3,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "B": {
  "original_notes": 5,
  "originals_left": 0,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "C": {
  "original_notes": 5,
  "originals_left": 1,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "D": {
  "original_notes": 6,
  "originals_left": 0,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "E": {
  "original_notes": 4,
  "originals_left": 0,
  "decision_kinds_that_touched_them": [
   "merge"
  ]
 },
 "S": {
  "original_notes": 24,
  "originals_left": 16
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
  7 | 2026-08-12 | preference  | Wants only remote jobs  [seed]
 44 | 2026-08-16 | goal        | Wants to become a data engineer  [seed]
 57 | 2026-08-19 | preference  | Prefers small companies  [seed]
 40 | 2026-08-22 | skill       | Uses Git every day  [seed]
 47 | 2026-08-28 | interest    | Interested in healthcare analytics  [seed]
 41 | 2026-09-04 | skill       | Has built dashboards in Tableau  [seed]
 45 | 2026-09-08 | goal        | Wants to work at a startup  [seed]
 63 | 2026-09-09 | interest    | Interested in data science and related fields  [consolidation]
 55 | 2026-09-10 | constraint  | Cannot work on Tuesday evenings because of classes  [seed]
 69 | 2026-09-14 | event       | Attended fall career fair and met recruiters  [consolidation]
 42 | 2026-09-19 | skill       | Can write basic Java  [seed]
 48 | 2026-09-22 | interest    | Interested in cloud computing  [seed]
 58 | 2026-09-26 | preference  | Likes jobs that use Python daily  [seed]
 16 | 2026-09-28 | interest    | Data science is a favorite topic  [seed]
  2 | 2026-10-02 | skill       | Knows Python  [seed]
 68 | 2026-10-06 | event       | Attended resume workshop and registered for Women in Tech panel  [consolidation]
 27 | 2026-10-08 | preference  | San Jose is the preferred location  [seed]
 43 | 2026-10-09 | skill       | Strong with Excel pivot tables  [seed]
  4 | 2026-10-11 | interest    | Interested in machine learning  [seed]
 67 | 2026-10-13 | application | Applied to data analyst, software engineer, and data internships  [consolidation]
 17 | 2026-10-14 | interest    | Enjoys data science projects  [seed]
 46 | 2026-10-15 | goal        | Plans to apply to graduate school in 2028  [seed]
 66 | 2026-10-18 | constraint  | Available 15 hours per week for work  [consolidation]
  8 | 2026-10-20 | preference  | Wants on-site jobs in San Jose and no remote work  [seed]
 49 | 2026-10-21 | interest    | Likes contributing to open source  [seed]
 56 | 2026-10-23 | constraint  | Needs the application deadline to be at least a week away  [seed]
 10 | 2026-10-25 | constraint  | Needs a minimum pay of $40 per hour  [seed]
 59 | 2026-10-26 | preference  | Prefers a mentor on the team  [seed]
 64 | 2026-10-28 | skill       | Knows SQL and is comfortable writing SQL queries  [consolidation]
 65 | 2026-10-29 | preference  | Prefers jobs in San Jose with a short commute  [consolidation]
  6 | 2026-10-30 | preference  | Prefers internships over full-time jobs  [seed]
 70 | 2026-11-01 | goal        | Is majoring in Computer Science and switched to Data Science  [consolidation]
 18 | 2026-11-03 | interest    | Curious about data science careers  [seed]
```
