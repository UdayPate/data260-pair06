"""
Context compaction demo (Lab 2, Part 6): token counts before and after, and proof of recall.

    python -m scripts.compaction_demo            (from backend/; in-memory MongoDB, REAL Ollama model)

Steps (all printed, and written to docs/lab2/compaction_demo.json and .md):
  1. A long conversation is built with REAL tools (the production search_jobs / search_events / get_student_preferences
     run against the database). A scripted model plays the student's assistant in this step only, so building the history is
     quick. Its token counts are ESTIMATES (marked as such): the aim is to get the context above 70 percent.
  2. BEFORE: the real model (Ollama) is asked one question on top of that history. Its own token counts are recorded
     (this is the real "before" number, and the warning flag must be on).
  3. COMPACT: compaction.compact() replaces the history with the summary. The report gives the sizes.
  4. AFTER: the real model is asked two RECALL questions that can only be answered from the summary (the history is gone):
     which company posted a given job, and what that job's id is. Its own token counts are recorded again.
  5. The answers are checked against the database: a recall passes only if the answer contains the true fact.
The result is printed as it is: a failed recall is reported as a failure.
"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1")
os.environ.setdefault("MONGO_TIMEOUT_MS", "200")

import mongomock  # noqa: E402

from app import mongo  # noqa: E402
from app.assistant import compaction  # noqa: E402
from app.assistant.agent import Conversation, build_system_prompt, run_assistant  # noqa: E402
from app.assistant.model_client import CONTEXT_WINDOW, OLLAMA_MODEL, ModelClient, ModelReply, OllamaClient, ToolRequest  # noqa: E402
from app.assistant.tools import TOOL_SCHEMAS, ToolContext  # noqa: E402
from app.assistant.usage import WARN_AT_PERCENT, estimate_messages_tokens, estimate_tokens  # noqa: E402
from app.enums import JobCategory, PayPeriod  # noqa: E402
from tests.factories import make_company, make_event, make_job, make_student  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "lab2"
COMPANIES = ["Acme Data", "Globex Analytics", "Initech Labs", "Umbrella Health", "Hooli Cloud", "Stark Robotics"]
TITLES = ["Data Science Intern", "Data Analyst Intern", "Machine Learning Intern", "Backend Engineer Intern",
          "Cloud Platform Intern", "Business Intelligence Intern", "Software Engineer Intern", "Research Assistant"]
CITIES = ["San Jose", "Sunnyvale", "Mountain View"]


class GrowingHistoryModel(ModelClient):
    """Step 1 only: asks for one search per student message, then answers. Reports ESTIMATED token counts."""

    def __init__(self, overhead_tokens: int):
        self.overhead, self.pending_search, self.n = overhead_tokens, None, 0

    def complete(self, messages, tools):
        tokens = self.overhead + estimate_messages_tokens(messages)
        if messages[-1].get("role") == "tool":
            reply = ModelReply("Here are the results above.")
        else:
            self.n += 1
            reply = ModelReply("", [ToolRequest("search_jobs", {"title": self.pending_search, "limit": 10})])
        reply.prompt_tokens, reply.completion_tokens = tokens, 30
        return reply


def build_world():
    today = date.today()
    db = mongomock.MongoClient()["p06_compaction_demo"]
    mongo.ensure_indexes(db)
    student = make_student(db, name="Sam Student", email="sam@s.test", college="SJSU", city="San Jose", major="Computer Science")
    companies = [make_company(db, name=name, email=f"hr{i}@c.test", city=CITIES[i % 3], state="CA") for i, name in enumerate(COMPANIES)]
    jobs = []
    for i in range(36):                                                 # enough that every search fills its 10 result lines
        jobs.append(make_job(
            db, companies[i % len(companies)].id, title=f"{TITLES[i % len(TITLES)]} {i + 1}", description="Work on real projects.",
            category=JobCategory.internship, city=CITIES[i % 3], state="CA", is_remote=bool(i % 2), salary_min=20 + i % 9,
            salary_max=30 + i % 11, pay_period=PayPeriod.hourly, skills=["Python", "SQL"],
            posting_date=today - timedelta(days=1 + i % 9), deadline=today + timedelta(days=20 + i)))
    make_event(db, companies[0].id, name="CS Career Fair", description="Meet employers.", city="San Jose", location="Hall A",
               event_datetime=datetime.combine(today + timedelta(days=25), datetime.min.time()), eligible_majors=["Computer Science"])
    return db, student, jobs


def run_turn(text, conversation, ctx, client, label, turns):
    began = time.perf_counter()
    result = run_assistant(text, conversation, ctx, client=client, log=lambda _l: None, timeout_seconds=1500)
    turns.append({"label": label, "student_said": text, "reply": result.reply, "tools": [t.name for t in result.tool_calls],
                  "tool_arguments": [t.arguments for t in result.tool_calls], "seconds": round(time.perf_counter() - began, 1),
                  "usage_this_request": result.usage.as_dict(), "error": result.error})
    return result


def main() -> int:
    db, student, jobs = build_world()
    ctx = ToolContext(db=db, student=student, today=date.today())
    overhead = estimate_tokens(build_system_prompt(ctx)) + estimate_tokens(json.dumps(TOOL_SCHEMAS))
    conversation = Conversation("compaction-demo", student.id)
    turns = []

    # ---- step 1: build a long history with the real tools (estimated token counts)
    builder = GrowingHistoryModel(overhead)
    searches = ["data", "analyst", "machine", "backend", "cloud", "intelligence", "software", "research", "science", "platform",
                "engineer", "learning", "intern", "projects"]
    for word in searches:
        builder.pending_search = word
        run_turn(f"show me {word} internships", conversation, ctx, builder, f"build history: {word}", turns)
        context = conversation.usage.exact_percent()
        print(f"  built: {len(conversation.messages)} messages, context about {context:.0f}% (estimated)")
        # The estimate runs about 15 percent above the model's real count (first run: estimated 74, real 64), so build until the
        # estimate is well past the warning line; the REAL number measured in step 2 is the one that is reported.
        if context > WARN_AT_PERCENT + 28:
            break
    estimated_before = conversation.usage.as_dict()
    history_messages_before = len(conversation.messages)

    # ---- step 2: the REAL model, on top of the long history
    real = OllamaClient(timeout=1500)
    print(f"Asking the real model ({OLLAMA_MODEL}) on top of a {history_messages_before}-message history ...")
    run_turn("Which of those internships pays the most per hour?", conversation, ctx, real, "REAL model, before compaction", turns)
    before_real = turns[-1]["usage_this_request"]

    # ---- step 3: compact
    report = compaction.compact(conversation, db, student)
    print(f"Compacted: {report['messages_before']} -> {report['messages_after']} messages")

    # ---- step 4: the REAL model, recall questions that only the summary can answer
    summary_text = conversation.messages[0]["content"]
    in_summary = [j for j in jobs if f"job {j.id}:" in summary_text]
    probe = in_summary[len(in_summary) // 2]                              # a job that is certainly inside the summary
    questions = [
        (f"Which company posted the job called \"{probe.title}\"?", mongo.get(db, "companies", probe.company_id).name,
         "company of a job"),
        (f"What is the id of the job called \"{probe.title}\"?", str(probe.id), "id of a job"),
    ]
    recall = []
    for text, expected, what in questions:
        print(f"RECALL ({what}): {text}")
        run_turn(text, conversation, ctx, real, f"REAL model, after compaction: {what}", turns)
        turn = turns[-1]
        evidence = turn["reply"] + " " + " ".join(json.dumps(a) for a in turn["tool_arguments"])
        recall.append({"question": text, "expected": expected, "passed": expected.lower() in evidence.lower(),
                       "reply": turn["reply"], "tools": turn["tools"], "seconds": turn["seconds"],
                       "context_tokens": turn["usage_this_request"]["context_tokens"],
                       "context_percent": turn["usage_this_request"]["context_percent"]})
    after_real = turns[-1]["usage_this_request"]

    result = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "model": OLLAMA_MODEL, "context_window": CONTEXT_WINDOW,
        "database": "in-memory mongomock",
        "history_built_with": "REAL tools, scripted model, ESTIMATED token counts (step 1 only)",
        "estimated_usage_before_real_call": estimated_before, "history_messages_before": history_messages_before,
        "before_compaction_real_model": before_real,
        "compaction": {k: v for k, v in report.items() if k != "summary"}, "summary": report.get("summary"),
        "after_compaction_real_model_first_recall_turn": after_real,
        "recall": recall, "all_recalls_passed": all(r["passed"] for r in recall), "turns": turns,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "compaction_demo.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    text = markdown(result)
    (OUT_DIR / "compaction_demo.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["all_recalls_passed"] else 1


def markdown(r) -> str:
    b, c, first = r["before_compaction_real_model"], r["compaction"], r["recall"][0]
    lines = [
        "# Context compaction: token counts before and after, and recall", "",
        f"Run on {r['run_at']}. Model: **{r['model']}** (real Ollama), context window {r['context_window']} tokens. "
        f"Database: {r['database']}. The long history was built with the real tools and a scripted model (token counts for "
        "that step are estimates); every number marked REAL below is the model's own count.", "",
        "| | Messages in the stored history | Context tokens, REAL (what the model read + wrote) | Context window used |", "|---|---|---|---|",
        f"| Before compaction | {c['messages_before']} | {b['context_tokens']} (last model call of the request, prompt + answer) | "
        f"{b['context_percent']}% |",
        f"| After compaction | {c['messages_after']} | {first['context_tokens']} (last model call of the next request) | "
        f"{first['context_percent']}% |", "",
        f"Estimated size of the stored history alone: {c['estimated_history_tokens_before']} -> {c['estimated_history_tokens_after']} tokens "
        "(characters / 4).", "",
        "## Recall after compaction", "", "| Question | Expected | Passed | Answer |", "|---|---|---|---|"]
    lines += [f"| {x['question']} | {x['expected']} | {'PASS' if x['passed'] else 'FAIL'} | {x['reply'][:160].replace(chr(10), ' ')} |"
              for x in r["recall"]]
    lines += ["", "## The summary that replaced the history", "", "```", r["summary"] or "", "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
