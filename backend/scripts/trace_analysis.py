"""
Where does an assistant request spend its time? (Lab 2, Part 6: stage timing over 50 requests)

    python -m scripts.trace_analysis                    (from backend/; in-memory MongoDB, REAL Ollama model, 50 requests)
    python -m scripts.trace_analysis --requests 8       (a shorter run)
    python -m scripts.trace_analysis --real-db          (the MongoDB at MONGO_URL: needed for database timing, see below)

Each request goes through the same function the website calls (services/assistant.run_assistant), so every request gets a
trace id, is timed stage by stage, and leaves a document in the `traces` collection. This script then READS those documents
and answers the assignment's question: does model inference, database queries, tool execution or queue wait dominate?

One request is sent to a model address that does not answer, so the output also shows a FAILED trace with its timings.

Honest limits (also written into the output):
  * An in-memory database (mongomock) sends no command events, so database time reads 0 there. Run with --real-db against
    a real MongoDB to measure it.
  * Queue wait only exists for Kafka messages (/memory learn and /memory consolidate). The chat request itself is answered
    straight away, so it has no queue; the worker part of a trace measures it when Kafka is running.
Output: docs/lab2/trace_analysis.json and docs/lab2/trace_analysis.md
"""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1")
os.environ.setdefault("MONGO_TIMEOUT_MS", "2000")

from app import mongo  # noqa: E402
from app.assistant import tracing  # noqa: E402
from app.assistant.model_client import OLLAMA_MODEL, OllamaClient  # noqa: E402
from app.services import assistant as service  # noqa: E402
from scripts.compaction_demo import build_world  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "lab2"
MESSAGES = [
    "Find a data internship", "Find internships in Sunnyvale", "Which upcoming events are open to Computer Science students?",
    "What are my job preferences?", "Find remote analyst jobs", "Show jobs that match my skills Python and SQL",
    "Find an internship in Mountain View paying at least 25 dollars an hour", "Are there any career fairs next month?",
    "Find a cloud internship", "Find a backend engineer internship in San Jose",
]


def percentile(values, p):
    values = sorted(values)
    if not values:
        return 0.0
    k = (len(values) - 1) * p / 100
    low, high = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[low] + (values[high] - values[low]) * (k - low), 1)


def summarize(traces):
    """Per stage: mean, median, 95th percentile and the share of all time spent in that stage."""
    keys = [("model_ms", "model inference"), ("db_ms", "database queries"), ("tool_compute_ms", "tool execution (not database)"),
            ("tool_ms", "tool execution (including its database queries)")]
    total_all = sum(t["total_ms"] for t in traces) or 1.0
    rows = []
    for key, label in keys:
        values = [t["stages"].get(key, 0.0) for t in traces]
        rows.append({"stage": label, "field": key, "mean_ms": round(statistics.mean(values), 1), "median_ms": percentile(values, 50),
                     "p95_ms": percentile(values, 95), "share_of_total_time_pct": round(100 * sum(values) / total_all, 2)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--real-db", action="store_true", help="use the MongoDB at MONGO_URL (the demo student must exist)")
    args = parser.parse_args()

    if args.real_db:
        db = mongo.get_database()
        mongo.ensure_indexes(db)
        student = mongo.find_one(db, "students", {"email": "demo.student@sjsu.edu"})
        db_label = "real MongoDB (MONGO_URL)"
    else:
        db, student, _ = build_world()
        db_label = "in-memory mongomock (no command timing: database time reads 0)"
    db.traces.delete_many({"student_id": student.id})

    service.model_client = OllamaClient(timeout=1200)
    print(f"Sending {args.requests} requests through the assistant service with {OLLAMA_MODEL} ...")
    failed_at = args.requests // 2
    sent = []
    started = time.perf_counter()
    for i in range(args.requests):
        text = MESSAGES[i % len(MESSAGES)]
        trace_id = f"analysis-{i + 1:02d}"
        if i == failed_at:                                        # one request to a model that is not there
            service.model_client = OllamaClient(base_url="http://127.0.0.1:9", timeout=5)
            trace_id = "analysis-failed"
        began = time.perf_counter()
        response = service.run_assistant(db, student, text, None, trace_id)
        if i == failed_at:
            service.model_client = OllamaClient(timeout=1200)
        sent.append({"trace_id": trace_id, "message": text, "seconds": round(time.perf_counter() - began, 1)})
        print(f"  {i + 1:>2}/{args.requests} {trace_id}: {sent[-1]['seconds']} s  tools={[t.name for t in response.tool_calls]}", flush=True)
    elapsed = round(time.perf_counter() - started, 1)

    traces = list(db.traces.find({"student_id": student.id, "kind": "chat"}).sort("at", 1))
    ok = [t for t in traces if t["status"] == "ok"]
    failed = [t for t in traces if t["status"] != "ok"]
    dominant = {}
    for t in ok:
        label = tracing.dominant_stage(t["stages"]) or "none measured"
        dominant[label] = dominant.get(label, 0) + 1
    db_measured = any(t["stages"].get("db_ms", 0) > 0 for t in traces)
    result = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "model": OLLAMA_MODEL, "database": db_label,
        "requests_sent": args.requests, "requests_ok": len(ok), "requests_failed": len(failed), "elapsed_seconds": elapsed,
        "database_time_measured": db_measured,
        "queue_wait": "not applicable to the chat request (it is answered directly); measured in the worker part of a trace when Kafka runs",
        "stage_summary_successful_requests": summarize(ok) if ok else [],
        "slowest_stage_per_request": dominant,
        "total_ms": {"mean": round(statistics.mean(t["total_ms"] for t in ok), 1) if ok else None,
                     "median": percentile([t["total_ms"] for t in ok], 50), "p95": percentile([t["total_ms"] for t in ok], 95)},
        "one_successful_trace": {k: v for k, v in (ok[0] if ok else {}).items() if k != "_id"},
        "one_failed_trace": {k: v for k, v in (failed[0] if failed else {}).items() if k != "_id"},
        "requests": sent,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "trace_analysis.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    text = markdown(result, ok[:1], failed[:1])
    (OUT_DIR / "trace_analysis.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def markdown(r, ok, failed) -> str:
    lines = [
        "# Stage timing over assistant requests", "",
        f"Run on {r['run_at']}. Model **{r['model']}** (real Ollama). Database: {r['database']}. "
        f"{r['requests_sent']} requests sent through `services/assistant.run_assistant` (the website's path), "
        f"{r['requests_ok']} answered normally and {r['requests_failed']} failed on purpose (a model address that does not answer). "
        f"Total {r['elapsed_seconds']} s.", "",
        f"Request time (successful requests): mean {r['total_ms']['mean']} ms, median {r['total_ms']['median']} ms, p95 {r['total_ms']['p95']} ms.", "",
        "| Stage | Mean ms | Median ms | p95 ms | Share of all time |", "|---|---|---|---|---|"]
    lines += [f"| {s['stage']} | {s['mean_ms']} | {s['median_ms']} | {s['p95_ms']} | {s['share_of_total_time_pct']}% |"
              for s in r["stage_summary_successful_requests"]]
    lines += ["", f"Slowest of the four compared stages, per request: {r['slowest_stage_per_request']}.", "",
              f"Database time measured: {r['database_time_measured']}. " +
              ("" if r["database_time_measured"] else "An in-memory database emits no command events, so it reads 0 here; run with `--real-db` to measure it."),
              f"Queue wait: {r['queue_wait']}.", ""]
    if ok:
        lines += ["## One successful trace", "", "```", tracing.format_trace(ok), "```", ""]
    if failed:
        lines += ["## One failed trace", "", "```", tracing.format_trace(failed), "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
