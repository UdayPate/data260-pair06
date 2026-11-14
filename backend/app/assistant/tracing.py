"""
Tracing (Lab 2, Part 6): follow one assistant request from the browser to the end, and say where its time went.

A TRACE ID is a short token given to a request. Every piece of work caused by that request carries it: the chat request
itself, the log lines, the Kafka event that a /memory command publishes (in its headers and in its body), and the worker's
own log lines and records. Searching for the id finds the whole story of the request.

Where the id comes from: the gateway (nginx) puts a fresh X-Request-ID on every request, a caller may send its own
X-Trace-ID, and app/core/trace.py reads it. The router passes it down to run_assistant().

What is recorded (collection `traces`, one document per piece of work):
    kind       "chat"  the request in the Assistant service      |   "memory_worker"  the Kafka consumer's part
    status     "ok", or the kind of failure (model_unreachable, timeout, iteration_ceiling, bad_tool_use, ...)
    stages     where the milliseconds went:
        model_ms          waiting for the language model (inference)
        db_ms             all MongoDB commands of the request (measured by pymongo itself, see db_timing.py)
        tool_ms           running tools (this includes the MongoDB queries the tools make)
        tool_db_ms        the MongoDB part of tool_ms
        tool_compute_ms   tool_ms minus tool_db_ms: tool work that is not waiting for the database
        queue_wait_ms     for a Kafka message: from "published" to "the worker started on it"
    Nothing the student typed is stored in a trace: only ids, counts, names of tools and timings.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pymongo.database import Database

logger = logging.getLogger("handshake.trace")

# The four stages the assignment asks us to compare, and the field of `stages` each one is measured by.
COMPARED_STAGES = {
    "model inference": "model_ms",
    "database queries": "db_ms",
    "tool execution (not database)": "tool_compute_ms",
    "queue wait": "queue_wait_ms",
}


def stages_from(model_ms: float, tool_ms: float, db_ms: float, tool_db_ms: float, db_calls: int,
                queue_wait_ms: Optional[float] = None) -> Dict[str, float]:
    """Turn the raw measurements into the stage dictionary stored in a trace."""
    stages = {
        "model_ms": round(model_ms, 1), "db_ms": round(db_ms, 1), "db_calls": db_calls,
        "tool_ms": round(tool_ms, 1), "tool_db_ms": round(tool_db_ms, 1),
        "tool_compute_ms": round(max(tool_ms - tool_db_ms, 0.0), 1),
    }
    if queue_wait_ms is not None:
        stages["queue_wait_ms"] = round(queue_wait_ms, 1)
    return stages


def dominant_stage(stages: Dict[str, float]) -> Optional[str]:
    """The stage with the most time among the four the assignment compares (None when nothing was measured)."""
    measured = {label: stages.get(key, 0.0) for label, key in COMPARED_STAGES.items() if stages.get(key) is not None}
    if not measured or max(measured.values()) <= 0:
        return None
    return max(measured, key=measured.get)


def log_line(trace_id: str, kind: str, status: str, total_ms: float, stages: Dict[str, float],
             usage: Optional[dict] = None) -> str:
    """One structured log line (key=value) that carries the trace id: what 'service logs' means here."""
    line = (f"event=assistant_{kind} trace_id={trace_id} status={status} total_ms={total_ms:.1f} "
            + " ".join(f"{k}={v}" for k, v in stages.items()))
    if usage:
        line += (f" model_calls={usage.get('model_calls')} prompt_tokens={usage.get('prompt_tokens')} "
                 f"completion_tokens={usage.get('completion_tokens')} context_percent={usage.get('context_percent')}")
    return line


def record(db: Database, *, trace_id: str, kind: str, student_id: Optional[int], status: str, total_ms: float,
           stages: Dict[str, float], usage: Optional[dict] = None, tools: Optional[List[str]] = None,
           detail: Optional[str] = None) -> None:
    """Store one trace document and write its log line. A tracing problem must never break the request, so errors are
    only logged."""
    logger.info(log_line(trace_id, kind, status, total_ms, stages, usage))
    try:
        db.traces.insert_one({
            "trace_id": trace_id, "kind": kind, "student_id": student_id, "at": datetime.now(timezone.utc).replace(tzinfo=None),
            "status": status, "total_ms": round(total_ms, 1), "stages": stages,
            "model_calls": (usage or {}).get("model_calls", 0),
            "prompt_tokens": (usage or {}).get("prompt_tokens", 0),
            "completion_tokens": (usage or {}).get("completion_tokens", 0),
            "context_percent": (usage or {}).get("context_percent"),
            "tools": tools or [], "detail": detail})
    except Exception as exc:          # a full disk or a database blip: the chat answer is more important than its trace
        logger.warning("event=trace_not_saved trace_id=%s error=%s", trace_id, exc)


def latest_for_student(db: Database, student_id: int) -> List[dict]:
    """The student's most recent trace and everything that shares its trace id (the chat part and any worker part)."""
    newest = db.traces.find_one({"student_id": student_id, "kind": "chat"}, sort=[("at", -1)])
    if newest is None:
        return []
    return list(db.traces.find({"trace_id": newest["trace_id"], "student_id": student_id}).sort("at", 1))


def format_trace(docs: List[dict]) -> str:
    """The text the /trace command shows."""
    if not docs:
        return "I have no trace for you yet. Send a message first."
    lines = [f"Trace {docs[0]['trace_id']} (this id is in the logs and in any Kafka event this request caused):"]
    for d in docs:
        s = d.get("stages", {})
        lines.append(f"- {d['kind']}: {d['status']}, {d['total_ms']} ms total")
        lines.append("    " + ", ".join(f"{k}={v}" for k, v in s.items()))
        if d.get("model_calls"):
            lines.append(f"    {d['model_calls']} model call(s), {d['prompt_tokens']} prompt + {d['completion_tokens']} "
                         f"completion tokens, context {d.get('context_percent')}% full")
        if d.get("tools"):
            lines.append("    tools: " + ", ".join(d["tools"]))
        top = dominant_stage(s)
        if top:
            lines.append(f"    slowest stage: {top}")
    return "\n".join(lines)
