"""
Memory consolidation demo (Lab 2, Part 3): seed one student's memory with 62 notes, run the consolidation handler,
and show the memory before and after.

    python -m scripts.memory_demo                 (from backend/; in-memory MongoDB, REAL Ollama model)
    python -m scripts.memory_demo --real-db       (the MongoDB that MONGO_URL points to; the demo student must exist)

What is real and what is not
  * The model is the real one (Ollama, OLLAMA_MODEL, default qwen3:8b): nothing about the model is scripted.
  * The handler is the same function the Kafka worker calls (events.handlers.dispatch -> handle_consolidate). Without
    --real-db the database is an in-memory mongomock, and the message is passed to the handler directly instead of through
    a Kafka broker. The output files say which database was used.

The seed (SEED = 6 in the pair configuration; this list is fixed text, nothing random):
  * 3 EXACT DUPLICATES   the same note stored twice
  * 3 CONTRADICTIONS     an older note and a newer note that cannot both be true (the newer one must win)
  * 26 notes in 5 groups of paraphrases (the same fact in different words) that should merge
  * 24 notes that are all different and should stay
Output: docs/lab2/memory_consolidation.json and docs/lab2/memory_consolidation.md
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("MONGO_TIMEOUT_MS", "2000")

import mongomock  # noqa: E402

from app import mongo  # noqa: E402
from app.assistant import memory, memory_consolidation as mc  # noqa: E402
from app.assistant.model_client import OLLAMA_MODEL  # noqa: E402
from app.events import topics  # noqa: E402
from app.events.envelope import new_envelope  # noqa: E402
from app.events.handlers import dispatch  # noqa: E402
from tests.factories import make_student  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "lab2"
DEMO_EMAIL = "demo.student@sjsu.edu"

# (tag, category, description, date). The tag is only for checking the result; it is never stored.
SEED_NOTES = [
    # --- 3 exact duplicates (each pair is the identical note, stored twice) ---
    ("dup1", "skill", "Knows Python", "2026-08-05"), ("dup1", "skill", "Knows Python", "2026-10-02"),
    ("dup2", "interest", "Interested in machine learning", "2026-08-18"), ("dup2", "interest", "Interested in machine learning", "2026-10-11"),
    ("dup3", "preference", "Prefers internships over full-time jobs", "2026-09-01"), ("dup3", "preference", "Prefers internships over full-time jobs", "2026-10-30"),
    # --- 3 contradictions: (old, new) pairs; the new note must win ---
    ("old1", "preference", "Wants only remote jobs", "2026-08-12"),
    ("new1", "preference", "Wants on-site jobs in San Jose and no remote work", "2026-10-20"),
    ("old2", "constraint", "Needs a minimum pay of $25 per hour", "2026-08-20"),
    ("new2", "constraint", "Needs a minimum pay of $40 per hour", "2026-10-25"),
    ("old3", "goal", "Is majoring in Computer Science", "2026-09-02"),
    ("new3", "goal", "Switched major to Data Science", "2026-11-01"),
    # --- group A: data science interest (6 paraphrases) ---
    ("A", "interest", "Interested in data science", "2026-08-03"), ("A", "interest", "Likes data science work", "2026-08-25"),
    ("A", "interest", "Wants to work in data science", "2026-09-09"), ("A", "interest", "Data science is a favorite topic", "2026-09-28"),
    ("A", "interest", "Enjoys data science projects", "2026-10-14"), ("A", "interest", "Curious about data science careers", "2026-11-03"),
    # --- group B: SQL skill (5 paraphrases) ---
    ("B", "skill", "Knows SQL", "2026-08-07"), ("B", "skill", "Comfortable writing SQL queries", "2026-08-30"),
    ("B", "skill", "Has used SQL in class projects", "2026-09-15"), ("B", "skill", "SQL is one of their strongest skills", "2026-10-05"),
    ("B", "skill", "Can write joins and aggregations in SQL", "2026-10-28"),
    # --- group C: wants to work around San Jose (5 paraphrases) ---
    ("C", "preference", "Prefers jobs in San Jose", "2026-08-09"), ("C", "preference", "Wants to work near San Jose", "2026-08-31"),
    ("C", "preference", "Lives in San Jose and wants a short commute", "2026-09-20"), ("C", "preference", "San Jose is the preferred location", "2026-10-08"),
    ("C", "preference", "Looking for roles in the San Jose area", "2026-10-29"),
    # --- group D: attended the fall career fair (6 one-off event notes) ---
    ("D", "event", "Attended the fall career fair", "2026-09-12"), ("D", "event", "Went to the SJSU fall career fair", "2026-09-12"),
    ("D", "event", "Visited the career fair in the fall", "2026-09-13"), ("D", "event", "Was at the fall career fair on campus", "2026-09-13"),
    ("D", "event", "Walked the fall career fair and met recruiters", "2026-09-14"), ("D", "event", "Fall career fair attendance", "2026-09-14"),
    # --- group E: available 15 hours a week (4 paraphrases) ---
    ("E", "constraint", "Available 15 hours a week", "2026-08-14"), ("E", "constraint", "Can work about 15 hours weekly", "2026-09-06"),
    ("E", "constraint", "Only free 15 hours per week during the semester", "2026-09-27"), ("E", "constraint", "Part-time availability of 15 hours per week", "2026-10-18"),
    # --- 24 different notes that should stay ---
    ("S", "skill", "Knows React", "2026-08-10"), ("S", "skill", "Uses Git every day", "2026-08-22"),
    ("S", "skill", "Has built dashboards in Tableau", "2026-09-04"), ("S", "skill", "Can write basic Java", "2026-09-19"),
    ("S", "skill", "Strong with Excel pivot tables", "2026-10-09"),
    ("S", "goal", "Wants to become a data engineer", "2026-08-16"), ("S", "goal", "Wants to work at a startup", "2026-09-08"),
    ("S", "goal", "Plans to apply to graduate school in 2028", "2026-10-15"),
    ("S", "interest", "Interested in healthcare analytics", "2026-08-28"), ("S", "interest", "Interested in cloud computing", "2026-09-22"),
    ("S", "interest", "Likes contributing to open source", "2026-10-21"),
    ("S", "application", "Applied to a Data Analyst internship at Acme Data", "2026-09-03"),
    ("S", "application", "Applied to a Software Engineer internship at Globex", "2026-09-24"),
    ("S", "application", "Applied to a data internship at Initech", "2026-10-13"),
    ("S", "event", "Registered for the Women in Tech panel", "2026-10-06"), ("S", "event", "Went to the resume workshop on campus", "2026-09-30"),
    ("S", "constraint", "Cannot work on Tuesday evenings because of classes", "2026-09-10"),
    ("S", "constraint", "Needs the application deadline to be at least a week away", "2026-10-23"),
    ("S", "preference", "Prefers small companies", "2026-08-19"), ("S", "preference", "Likes jobs that use Python daily", "2026-09-26"),
    ("S", "preference", "Prefers a mentor on the team", "2026-10-26"),
    ("S", "note", "Likes short answers", "2026-08-08"), ("S", "note", "Prefers bullet points when comparing jobs", "2026-09-17"),
    ("S", "note", "Reads email in the morning", "2026-10-31"),
]
CONTRADICTION_PAIRS = [("old1", "new1"), ("old2", "new2"), ("old3", "new3")]
DUPLICATE_TAGS = ["dup1", "dup2", "dup3"]


def open_database(real: bool):
    if real:
        db = mongo.get_database()
        mongo.ensure_indexes(db)
        return db, "real MongoDB (MONGO_URL)"
    db = mongomock.MongoClient()["p06_memory_demo"]
    mongo.ensure_indexes(db)
    return db, "in-memory mongomock (no MongoDB server was reachable)"


def seed(db, student):
    """Replace the student's memory with the seed. Returns {tag: [ids]}."""
    db.student_memory.delete_many({"student_id": student.id})
    ids = {}
    for tag, category, text, day in SEED_NOTES:
        entry = memory.add_entry(db, student.id, category, text, on=date.fromisoformat(day), source="seed")
        ids.setdefault(tag, []).append(entry.id)
    return ids


def snapshot(db, student_id):
    return [{"id": e.id, "date": e.date, "category": e.category, "description": e.description, "source": e.source}
            for e in memory.list_entries(db, student_id)]


def check(before, after, ids, report):
    """The verification the assignment asks for. Every check is computed from the data, none is assumed."""
    after_ids = {e["id"] for e in after}
    keys = [(e["category"], mc.normalize(e["description"])) for e in after]
    checks = []

    def add(name, passed, detail):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add("started with at least 60 notes", len(before) >= 60, f"{len(before)} notes")
    add("ended below 40 notes", len(after) < 40, f"{len(after)} notes")
    add("no exact duplicate is left", len(keys) == len(set(keys)), f"{len(keys) - len(set(keys))} duplicate(s) left")
    for tag in DUPLICATE_TAGS:
        copies = [i for i in ids[tag] if i in after_ids]
        add(f"duplicate {tag} merged to at most one note", len(copies) <= 1, f"{len(copies)} of {len(ids[tag])} copies left")
    for old_tag, new_tag in CONTRADICTION_PAIRS:
        old_left, new_left = ids[old_tag][0] in after_ids, ids[new_tag][0] in after_ids
        detail = ("old note removed, newer note kept" if new_left and not old_left else
                  "BOTH notes are still there (unresolved)" if old_left and new_left else
                  "the OLD note is still there and the newer one is gone (wrong way round)" if old_left else
                  "both notes are gone (the newer fact was lost)")
        add(f"contradiction {old_tag} vs {new_tag} resolved in favour of the newer note", new_left and not old_left, detail)
    return checks


def group_summary(ids, after, report):
    """For each paraphrase group: how many of its original notes are left, and which decisions touched them."""
    after_ids = {e["id"] for e in after}
    out = {}
    for tag in ["A", "B", "C", "D", "E"]:
        members = ids[tag]
        touched = sorted({d.kind for d in report.decisions if d.accepted and set(d.ids) & set(members)})
        out[tag] = {"original_notes": len(members), "originals_left": sum(i in after_ids for i in members),
                    "decision_kinds_that_touched_them": touched}
    out["S"] = {"original_notes": len(ids["S"]), "originals_left": sum(i in after_ids for i in ids["S"])}
    return out


def markdown(result):
    r = result
    lines = ["# Memory consolidation: before and after", "",
             f"Run on {r['run_at']} with `python -m scripts.memory_demo`. Model: **{r['model']}** (real Ollama, not scripted). "
             f"Database: {r['database']}. The consolidation handler is the same function the Kafka worker runs; here the "
             "message was handed to it directly, without a Kafka broker.", "",
             f"**{r['before_count']} notes before, {r['after_count']} after** ({r['elapsed_seconds']} s). "
             f"Model calls: {r['report']['model_calls']} (one per category with two or more notes); every answer readable: "
             f"{r['report']['model_answer_readable']}.", "",
             "## Checks", "", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {c['check']} | {'PASS' if c['passed'] else 'FAIL'} | {c['detail']} |" for c in r["checks"]]
    lines += ["", "## Decisions", "", "| Kind | Notes | Accepted | What | Why rejected |", "|---|---|---|---|---|"]
    for d in r["report"]["decisions"]:
        lines.append(f"| {d['kind']} | {d['ids']} | {'yes' if d['accepted'] else 'NO'} | {d['detail']} | {d['reason']} |")
    lines += ["", "## Paraphrase groups", "", "```", json.dumps(r["groups"], indent=1), "```", "",
              "## Memory before", "", "```"] + [f"{e['id']:>3} | {e['date']} | {e['category']:<11} | {e['description']}" for e in r["before"]]
    lines += ["```", "", "## Memory after", "", "```"] + [f"{e['id']:>3} | {e['date']} | {e['category']:<11} | {e['description']}  [{e['source']}]" for e in r["after"]]
    lines += ["```", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-db", action="store_true", help="use the MongoDB at MONGO_URL instead of an in-memory one")
    args = parser.parse_args()

    db, db_label = open_database(args.real_db)
    student = mongo.find_one(db, "students", {"email": DEMO_EMAIL}) if args.real_db else \
        make_student(db, name="Demo Student", email=DEMO_EMAIL, college="SJSU", major="Computer Science")
    if student is None:
        print(f"The demo student {DEMO_EMAIL} does not exist in this database.")
        return 2

    ids = seed(db, student)
    before = snapshot(db, student.id)
    print(f"Seeded {len(before)} notes for {DEMO_EMAIL}. Calling the consolidation handler with the real model ...")

    envelope = new_envelope(topics.MEMORY_CONSOLIDATE_REQUESTED, {"student_id": student.id}, "memory-demo", "memory_demo")
    started = time.perf_counter()
    outcome = dispatch(db, envelope)
    elapsed = round(time.perf_counter() - started, 1)
    after = snapshot(db, student.id)
    run = db.memory_runs.find_one({"_id": envelope.event_id})
    report_dict = run["consolidation"]

    class _R:                       # the stored report, as objects, for group_summary()
        decisions = [mc.Decision(**d) for d in report_dict["decisions"]]

    result = {"run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "model": OLLAMA_MODEL, "database": db_label,
              "handler_outcome": outcome, "elapsed_seconds": elapsed, "before_count": len(before), "after_count": len(after),
              "checks": check(before, after, ids, _R), "groups": group_summary(ids, after, _R), "report": report_dict,
              "before": before, "after": after}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "memory_consolidation.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    text = markdown(result)
    (OUT_DIR / "memory_consolidation.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if all(c["passed"] for c in result["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
