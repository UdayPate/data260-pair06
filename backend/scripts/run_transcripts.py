"""
Runs the five required Part B test queries against the REAL model and the REAL database and
writes the complete transcripts (every tool call and result) to a text file.

Run from backend/ with Ollama running and the database seeded:
    python -m scripts.run_transcripts                 # all five tests
    python -m scripts.run_transcripts 1 3             # only tests 1 and 3
    python -m scripts.run_transcripts --out docs\\part_b_transcripts.txt

Tests 2 and 4 share one conversation on purpose: test 4 is the follow-up to test 2's job
search ("make it closer or higher paying" refines the previous result). Test 4 therefore
needs test 2 to run in the same invocation.
The demo student (demo.student@sjsu.edu) is used; saves are never triggered by these queries.
"""
import argparse
import sys
import time
from datetime import date

from sqlalchemy import select

from app.assistant.agent import Conversation, run_assistant
from app.assistant.model_client import OLLAMA_MODEL
from app.assistant.tools import ToolContext
from app.database import SessionLocal
from app.models import Student

# (test number, conversation group, what the grader looks for, the student's message)
TESTS = [
    (1, "A", "must call get_student_preferences FIRST and use the result", "Find an internship in my city."),
    (2, "B", "must filter by category, location/remote and skills", "Find a remote data science internship."),
    (3, "C", "must filter by date (next month) and eligibility", "Find an event for computer science students next month."),
    (4, "B", "follow-up: must refine the previous result using history", "Make it closer or higher paying."),
    (5, "D", "must say no match exists and invent nothing", "Find me a job at Hooli Quantum Falconry."),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252 and garble the en dash
    parser = argparse.ArgumentParser()
    parser.add_argument("tests", nargs="*", type=int, help="test numbers to run (default: all)")
    parser.add_argument("--out", default="part_b_transcripts.txt")
    args = parser.parse_args()
    wanted = set(args.tests) or {t[0] for t in TESTS}
    if 4 in wanted:
        wanted.add(2)   # the follow-up needs the search it refines

    db = SessionLocal()
    student = db.scalar(select(Student).where(Student.email == "demo.student@sjsu.edu"))
    if student is None:
        sys.exit("Demo student not found. Seed first: python -m seed.generate_seed --reset")
    ctx = ToolContext(db=db, student=student)
    conversations = {}
    lines = [f"Part B transcripts | model {OLLAMA_MODEL} | run date {date.today().isoformat()} | "
             f"student {student.email} (major {student.major}, city {student.city})", ""]

    for number, group, expectation, message in TESTS:
        if number not in wanted:
            continue
        conv = conversations.setdefault(group, Conversation(conversation_id=f"test-{group}", student_id=student.id))
        lines += ["=" * 78, f"TEST {number}: {expectation}", f"STUDENT: {message}", "-" * 78]
        printed = []
        started = time.time()
        result = run_assistant(message, conv, ctx, log=printed.append)
        seconds = time.time() - started
        for record, log_line in zip(result.tool_calls, [p for p in printed if p.startswith("[tool]")]):
            lines += [log_line, "    RESULT: " + record.result.replace("\n", "\n            ")]
        lines += [printed[-1], f"ASSISTANT: {result.reply}",
                  f"(model calls: {result.iterations}, seconds: {seconds:.0f}, stopped at ceiling: {result.stopped_at_ceiling})", ""]
        print("\n".join(lines[-(len(result.tool_calls) * 2 + 6):]), flush=True)

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print(f"\nTranscript written to {args.out}")


if __name__ == "__main__":
    main()
