"""
Context compaction (Lab 2, Part 6).

Every message of a conversation is sent to the model again on the next turn, so a long chat fills the context window
(see usage.py). COMPACTION replaces the stored history with one short SUMMARY, so the conversation can go on.

The summary is built by CODE from the messages, not written by the model. That is deliberate:
  * it cannot invent a job, an id or a date, because it only copies lines that a tool really returned;
  * it keeps the exact ids ("job 12"), so after compaction the student can still say "save the second one" or
    "tell me more about job 12" and the assistant knows what that is (the "recall" check in the report);
  * it costs no model call, so it is instant and works even when the model is slow or down.

What the summary holds (the list the assignment asks for):
    the student's preferences, the jobs and companies and events that came up, the student's applications on file,
    what was saved, what the student asked before, and the CURRENT request (the last thing the student said).

When it runs: automatically when the context is 85 percent full (usage.COMPACT_AT_PERCENT), or when the student types
/compact. The result reports the size before and after.
"""
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from pymongo.database import Database

from .. import mongo
from ..mongo import Doc
from . import guardrails
from .tools import UNTRUSTED_END, UNTRUSTED_START, mark_untrusted
from .usage import estimate_messages_tokens

SUMMARY_MARKER = "[Conversation summary"          # every summary message starts with this (other code recognises it)
MAX_JOBS, MAX_EVENTS, MAX_EARLIER_REQUESTS, MAX_APPLICATIONS = 15, 10, 6, 5
ACK = "Understood. I have the summary of our earlier conversation and will continue from it."

# The lines the tools print (see tools.py: _job_line, _event_line, get_job_details).
_JOB_LINE = re.compile(r"^- id (\d+) \| (.+?) \| (.+?) \| (.+?) \| (\w+) \| (.+?) \| deadline (\d{4}-\d{2}-\d{2})")
_EVENT_LINE = re.compile(r"^- id (\d+) \| (.+?) \| (\d{4}-\d{2}-\d{2}) [\d:]+ \| (.+?) \| host: (.+?) \| open to: (.+?)(?: \||$)")
_DETAIL_HEAD = re.compile(r"^Job id (\d+): (.+)$")
_DETAIL_COMPANY = re.compile(r"^Company: (.+?) \(")


def is_summary(message: dict) -> bool:
    return (message.get("content") or "").startswith(SUMMARY_MARKER)


def _tool_text(content: str) -> str:
    """A tool result without the untrusted-data markers around it."""
    return content.replace(UNTRUSTED_START, "").replace(UNTRUSTED_END, "").strip()


def _gather(messages: List[dict]) -> dict:
    """Read the messages once and collect the facts a summary needs. Later mentions replace earlier ones (same id)."""
    jobs: Dict[str, str] = {}        # id -> one line
    events: Dict[str, str] = {}
    companies: List[str] = []
    saved: List[str] = []
    preferences = ""
    earlier: List[str] = []
    previous_summary = ""

    def add_company(name: str) -> None:
        name = name.strip()
        if name and name not in companies:
            companies.append(name)

    for m in messages:
        role, content = m.get("role"), (m.get("content") or "")
        if is_summary(m):
            previous_summary = content                        # a second compaction keeps what the first one knew
        elif role == "user" and not content.startswith("[automatic notice]"):
            earlier.append(content.strip())
        elif role == "tool":
            body = _tool_text(content)
            if m.get("tool_name") == "get_student_preferences" and not body.startswith("Error"):
                preferences = body
            elif m.get("tool_name") == "save_job_or_event" and body.startswith("Saved"):
                saved.append(body.replace("Saved: ", "", 1))
            lines = body.splitlines()
            for line in lines:
                job, event = _JOB_LINE.match(line), _EVENT_LINE.match(line)
                if job:
                    jid, title, company, where, category, pay, deadline = job.groups()
                    jobs[jid] = f"job {jid}: {title} at {company} ({where}, {category}, {pay}, deadline {deadline})"
                    add_company(company)
                elif event:
                    eid, name, day, place, host, majors = event.groups()
                    events[eid] = f"event {eid}: {name} on {day} at {place} (host {host}; open to {majors})"
                    add_company(host)
            head = _DETAIL_HEAD.match(lines[0]) if lines else None      # get_job_details
            if head:
                company = next((_DETAIL_COMPANY.match(l).group(1) for l in lines if _DETAIL_COMPANY.match(l)), "")
                jobs.setdefault(head.group(1), f"job {head.group(1)}: {head.group(2)} at {company}".strip())
                add_company(company)
    return {"jobs": jobs, "events": events, "companies": companies, "saved": saved, "preferences": preferences,
            "earlier": earlier, "previous_summary": previous_summary}


def _applications_on_file(db: Optional[Database], student: Optional[Doc]) -> List[str]:
    """The student's most recent applications, read from the database (the assistant has no tool for them)."""
    if db is None or student is None:
        return []
    lines = []
    for application in mongo.find(db, "applications", {"student_id": student.id},
                                  sort=[("applied_at", -1)], limit=MAX_APPLICATIONS):
        job = mongo.get(db, "jobs", application.job_id)
        lines.append(f"{job.title if job else 'job ' + str(application.job_id)} ({application.status})")
    return lines


def build_summary(messages: List[dict], db: Optional[Database] = None, student: Optional[Doc] = None,
                  today: Optional[date] = None, number: int = 1) -> str:
    """The text that replaces the history."""
    facts = _gather(messages)
    requests = facts["earlier"]
    current = requests[-1] if requests else "(none)"
    last_answer = next((m["content"].strip() for m in reversed(messages)
                        if m.get("role") == "assistant" and (m.get("content") or "").strip()), "")
    body = []
    if facts["previous_summary"]:
        body.append("Earlier summary (kept): " + facts["previous_summary"].split("\n", 1)[-1][:1500])
    body.append("Student's preferences: " + (facts["preferences"][:700].replace("\n", " ") or "none recorded in this conversation"))
    body.append("Jobs that came up: " + ("; ".join(list(facts["jobs"].values())[-MAX_JOBS:]) or "none"))
    body.append("Companies mentioned: " + (", ".join(facts["companies"][-20:]) or "none"))
    body.append("Events that came up: " + ("; ".join(list(facts["events"].values())[-MAX_EVENTS:]) or "none"))
    body.append("Saved during this conversation: " + ("; ".join(facts["saved"]) or "nothing"))
    applications = _applications_on_file(db, student)
    body.append("Applications on file: " + ("; ".join(applications) or "none"))
    body.append("What the student asked before: " +
                (" | ".join(r[:160] for r in requests[-(MAX_EARLIER_REQUESTS + 1):-1]) or "nothing else"))
    if last_answer:
        body.append("Your last answer began: " + last_answer[:300].replace("\n", " "))
    body.append("Current request: " + current[:500])
    when = (today or date.today()).isoformat()
    text = "\n".join(body)
    text, _ = guardrails.redact_secrets(text)
    # The job and event lines were written by companies: label the whole block as data, like every other tool result.
    return (f"{SUMMARY_MARKER} #{number}, {when}: the earlier messages were replaced by this summary to save space. "
            f"Use it as background; the facts in it came from tool results.]\n{mark_untrusted(text)}")


def compact(conversation, db: Optional[Database] = None, student: Optional[Doc] = None,
            today: Optional[date] = None) -> dict:
    """Replace the conversation's history with a summary. Returns a report with the sizes before and after.
    Nothing is changed when a save is waiting for the student's yes or no (the history holds that question)."""
    messages = conversation.messages
    report = {"compacted": False, "messages_before": len(messages), "messages_after": len(messages)}
    if conversation.pending is not None:
        report["skipped"] = "a save is waiting for your yes or no"
        return report
    if len(messages) < 3:
        report["skipped"] = "the conversation is too short to compact"
        return report
    before = estimate_messages_tokens(messages)
    number = conversation.compactions + 1
    summary = build_summary(messages, db, student, today, number)
    conversation.messages = [{"role": "user", "content": summary}, {"role": "assistant", "content": ACK}]
    conversation.compactions = number
    after = estimate_messages_tokens(conversation.messages)

    # The next model call will measure the real size. Until then, estimate it: the last real prompt minus what we removed.
    usage = conversation.usage
    report_context_before = usage.context_tokens
    usage.last_prompt_tokens = max(0, usage.last_prompt_tokens - max(0, before - after))
    usage.last_completion_tokens = 0
    usage.estimated = True
    report.update({
        "compacted": True, "messages_after": len(conversation.messages), "summary_number": number,
        "estimated_history_tokens_before": before, "estimated_history_tokens_after": after,
        "context_tokens_before": report_context_before, "context_tokens_after_estimated": usage.context_tokens,
        "summary": summary,
    })
    return report
