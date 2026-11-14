"""
Learning and consolidating the assistant's memory (Lab 2, Part 3). This code runs in a KAFKA WORKER, never inside a
user's chat request (a model call can take minutes on a CPU and must not make the chat wait).

Two events, both keyed by student_id so one student's events stay in order:

  memory.session_ended         {student_id, conversation_id}   learn notes from a finished chat, then consolidate if the
                                                               student has more than CONSOLIDATE_ABOVE notes
  memory.consolidate_requested {student_id}                    consolidate now (the /memory consolidate command)

LEARNING: the model reads only the student's own words and the assistant's replies (never tool results: those hold text
written by companies, which could be an injection attack) and returns a short JSON list of notes.

CONSOLIDATION, in three steps (the code is the judge, the model only proposes):
  A. Exact duplicates (same category and same words) are merged by code. The newest copy stays.
  B. For each category that still has two or more notes, the model reads that small list and points at problems, by id:
       same            several notes that say the same thing   ->  the code merges them into one note
       contradictions  PAIRS of notes that cannot both be true ->  the code keeps the NEWER one (the model never picks)
       drop            one-off notes that no longer matter (a past event the student went to)
     Asking per category, and only for pairs, came from two real runs with qwen3:8b: one call about all 59 notes made it
     merge unrelated notes, merge two contradictory notes into one sentence, and keep the OLDER note of a pair.
     Every decision is checked by code before it is applied (ids must be among the notes shown; merges are small and
     short and never contain a contradicting pair; only one-off categories may be dropped). A decision that fails a
     check is rejected and written to the report, so a model mistake can never delete a note it had no right to delete.
  C. If the memory is still at or above TARGET_MAX notes (the model failed, was unreachable, or did too little), a
     deterministic safety net keeps only the newest CAP_PER_CATEGORY notes of each category.
Writes happen as "add the merged notes, then delete the old ones": a crash in between leaves duplicates (merged by the
next run), never a lost fact.
"""
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Set

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import db_timing, mongo
from ..events.errors import PermanentError
from ..mongo import Doc
from . import memory, tracing
from .model_client import ModelClient, ModelError, OllamaClient
from .usage import Usage

logger = logging.getLogger("handshake.memory")

TARGET_MAX = 39               # the assignment: the result must be BELOW 40 entries
CAP_PER_CATEGORY = 4          # safety net: 8 categories x 4 = at most 32 notes
CONSOLIDATE_ABOVE = 40        # after learning, consolidate when the student has more notes than this
LEARN_LIMIT = 8               # at most this many new notes from one conversation
DROPPABLE = {"event", "application", "note"}      # one-off categories the model may drop outright
MAX_MERGE = 8                 # one merge may combine at most this many notes
MAX_MERGED_CHARS = 200        # a merged note is one short sentence
MODEL_TIMEOUT_SECONDS = float(os.getenv("MEMORY_MODEL_TIMEOUT_SECONDS", "240"))

# Tests plug in a fake model here (None = the real Ollama client).
model_client: Optional[ModelClient] = None


def get_client() -> ModelClient:
    return model_client or OllamaClient(timeout=MODEL_TIMEOUT_SECONDS, json_format=True)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """For comparing notes: lower case, punctuation removed, one space between words."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def parse_json(text: str):
    """Read the JSON a model wrote, even when it wrapped it in ```json fences or added a sentence around it.
    Returns None when nothing readable is found."""
    text = re.sub(r"```(?:json)?", "", text or "")
    # Try whichever bracket opens FIRST: a list of objects starts with "[" even though it contains "{" later.
    openers = sorted((text.find(o), o, c) for o, c in (("{", "}"), ("[", "]")) if o in text)
    for start, _, closer in openers:
        end = text.rfind(closer)
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Learning notes from a conversation
# ---------------------------------------------------------------------------
LEARN_PROMPT = f"""You write short notes about a student for a career assistant's long-term memory.
Read the conversation and note only what the STUDENT said about themselves: preferences, skills, interests, goals,
constraints, and jobs or events they applied to or attended. Do not note job listings, company claims or guesses.
Answer with ONLY JSON: {{"notes": [{{"category": "...", "description": "..."}}]}} with at most {LEARN_LIMIT} notes.
category is one of: {', '.join(memory.CATEGORIES)}. description is one short sentence in plain words.
If the student said nothing worth remembering, answer {{"notes": []}}."""


def conversation_text(messages: List[dict]) -> str:
    """The part of a conversation the model may read. Tool results are left out on purpose: they contain text written
    by companies (possible prompt injection). Automatic repair notices are left out too: they are not the student's."""
    lines = []
    for m in messages:
        content = (m.get("content") or "").strip()
        if m.get("role") not in ("user", "assistant") or not content or content.startswith("[automatic notice]"):
            continue
        if content.startswith("[Conversation summary") or content == "Understood. I have the summary of our earlier conversation and will continue from it.":
            continue                           # a compaction summary holds tool results, not the student's own words
        lines.append(f"{'Student' if m['role'] == 'user' else 'Assistant'}: {content}")
    return "\n".join(lines)[-6000:]


def learn(db: Database, student_id: int, messages: List[dict], client: ModelClient,
          today: Optional[date] = None) -> List[Doc]:
    """Ask the model for notes and store the valid ones. A ModelError escapes (the worker retries it); an answer
    that cannot be read just means no notes."""
    text = conversation_text(messages)
    if not text:
        return []
    reply = client.complete([{"role": "system", "content": LEARN_PROMPT}, {"role": "user", "content": text}], [])
    items = parse_json(reply.content)
    if isinstance(items, dict):              # JSON mode answers with an object: {"notes": [...]}
        items = items.get("notes")
    if not isinstance(items, list):
        logger.warning("event=memory_learn student_id=%s error=unreadable_model_answer", student_id)
        return []
    known = {(e.category, normalize(e.description)) for e in memory.list_entries(db, student_id)}
    added = []
    for item in items[:LEARN_LIMIT]:
        if not isinstance(item, dict) or not isinstance(item.get("description"), str):
            continue
        category = memory.clean_category(item.get("category") if isinstance(item.get("category"), str) else None)
        key = (category, normalize(memory.clean_description(item["description"])))
        if not key[1] or key in known:          # empty, or the student already has exactly this note
            continue
        entry = memory.add_entry(db, student_id, category, item["description"], on=today, source="conversation")
        if entry is not None:
            known.add(key)
            added.append(entry)
    return added


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------
@dataclass
class Decision:
    kind: str                     # duplicate, merge, contradiction, drop, fallback_cap
    ids: List[int]                # the notes it is about
    detail: str                   # what was decided, in words
    accepted: bool = True
    reason: str = ""              # why a decision was rejected


@dataclass
class Report:
    before: int = 0
    after: int = 0
    decisions: List[Decision] = field(default_factory=list)
    used_model: bool = False
    model_error: Optional[str] = None
    model_answer_readable: Optional[bool] = None
    model_calls: int = 0              # one call per category that has at least two notes

    def as_dict(self) -> dict:
        return {"before": self.before, "after": self.after, "used_model": self.used_model, "model_calls": self.model_calls,
                "model_error": self.model_error, "model_answer_readable": self.model_answer_readable,
                "decisions": [d.__dict__ for d in self.decisions]}


CATEGORY_PROMPT = """You tidy a student's long-term notes for a career assistant. Every note below is in the category "{category}". Each note is: id | date | text.
Find:
  "same": groups of notes that say the SAME thing in different words -> {{"ids": [..], "description": "one short sentence that keeps every distinct fact"}}
  "contradictions": pairs of notes that cannot both be true now -> [id, id]. Only list the pair: you do NOT decide which note is right.
  "drop": ids of one-off notes that no longer matter, such as a past event or application. {drop_rule}
Rules: use only ids from the list. Never invent facts. Notes about different things are NOT the same.

Example (different notes, to show the format):
7 | 2026-01-02 | Knows Excel
8 | 2026-02-03 | Good with Excel
9 | 2026-01-05 | Wants a remote job
10 | 2026-03-04 | Wants an on-site job
Answer: {{"same": [{{"ids": [7, 8], "description": "Knows Excel well"}}], "contradictions": [[9, 10]], "drop": []}}

Answer with ONLY JSON of this shape: {{"same": [], "contradictions": [], "drop": []}}"""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _ask_group(category: str, group: List[Doc], client: ModelClient) -> Optional[dict]:
    """One model call about the notes of ONE category (a small list is much easier for a small model than all notes at once)."""
    drop_rule = "" if category in DROPPABLE else 'Leave "drop" empty for this category.'
    listing = "\n".join(f"{e.id} | {e.date} | {e.description}" for e in group)
    system = CATEGORY_PROMPT.format(category=category, drop_rule=drop_rule)
    reply = client.complete([{"role": "system", "content": system}, {"role": "user", "content": listing}], [])
    proposal = parse_json(reply.content)
    return proposal if isinstance(proposal, dict) else None


def _apply_group(proposal: dict, group: List[Doc], report: Report):
    """Check each decision the model proposed for one category and keep the valid ones.
    Returns (ids to delete, new notes to create). The model only POINTS at notes; the code decides who wins."""
    by_id = {e.id: e for e in group}
    category = group[0].category
    delete: Set[int] = set()
    create: List[dict] = []
    merged: Set[int] = set()          # ids already used by a merge or a drop: each may be used once

    def reject(kind: str, ids, detail: str, reason: str):
        report.decisions.append(Decision(kind, [i for i in ids if _is_int(i)] if isinstance(ids, list) else [],
                                         detail, accepted=False, reason=reason))

    def known(ids) -> Optional[str]:
        """A problem with a list of ids, or None when it is fine."""
        if not isinstance(ids, list) or not ids or not all(_is_int(i) for i in ids):
            return "ids must be a non-empty list of whole numbers"
        if any(i not in by_id for i in ids):
            return "an id is not one of the notes shown for this category"
        if len(set(ids)) != len(ids):
            return "an id was listed twice"
        return None

    # 1. Contradictions: the model lists PAIRS. The code decides: the newer note wins (on the same date, the later one).
    pairs = []
    for pair in proposal.get("contradictions") or []:
        problem = known(pair) or (None if len(pair) == 2 else "a contradiction is a pair of exactly two ids")
        if problem:
            reject("contradiction", pair, "", problem)
            continue
        older, newer = sorted((by_id[i] for i in pair), key=lambda e: (e.date, e.id))
        pairs.append((older.id, newer.id))
        delete.add(older.id)
        report.decisions.append(Decision(
            "contradiction", [newer.id, older.id],
            f"kept {newer.id} ({newer.description}); dropped the older {older.id} ({older.description})"))

    # 2. Merges: the same fact in different words. One category, a handful of notes, one short sentence. (A real run showed
    #    why: qwen3:8b once merged 11 unrelated notes into one paragraph, and once merged two contradictory notes.)
    for item in proposal.get("same") or []:
        item = item if isinstance(item, dict) else {}
        ids, text = item.get("ids"), item.get("description")
        problem = known(ids) or (None if len(ids) >= 2 else "a merge needs at least two ids") \
            or (None if len(ids) <= MAX_MERGE else f"a merge may combine at most {MAX_MERGE} notes") \
            or (None if isinstance(text, str) and memory.clean_description(text) else "the merged description is empty") \
            or (None if len(text) <= MAX_MERGED_CHARS else f"the merged description is longer than {MAX_MERGED_CHARS} characters, so it is not one fact") \
            or ("the notes contradict each other, so they cannot be merged" if any(a in ids and b in ids for a, b in pairs) else None) \
            or ("it includes a note that a contradiction already removed" if set(ids) & delete else None) \
            or ("an id was already used by another decision" if set(ids) & merged else None)
        if problem:
            reject("merge", ids, str(text), problem)
            continue
        create.append({"category": category, "description": text, "date": max(by_id[i].date for i in ids)})
        delete.update(ids)
        merged.update(ids)
        report.decisions.append(Decision("merge", list(ids), f"merged into: {memory.clean_description(text)}"))

    # 3. Drops: one-off notes that no longer matter. Only the one-off categories may lose notes this way.
    drops = proposal.get("drop") or []
    for i in drops if isinstance(drops, list) else []:
        problem = known([i]) or (None if category in DROPPABLE else "only one-off categories (event, application, note) may be dropped") \
            or ("already handled by another decision" if i in delete or i in merged else None)
        if problem:
            reject("drop", [i], "", problem)
            continue
        delete.add(i)
        merged.add(i)
        report.decisions.append(Decision("drop", [i], f"dropped one-off note: {by_id[i].description}"))
    return delete, create


def consolidate(db: Database, student_id: int, client: Optional[ModelClient] = None) -> Report:
    """Merge duplicates, resolve contradictions and shrink one student's memory. Returns a report of every decision."""
    entries = memory.list_entries(db, student_id)
    report = Report(before=len(entries))
    delete: Set[int] = set()
    create: List[dict] = []

    # --- step A: exact duplicates (same category, same words). The newest copy stays. ---
    groups: Dict[tuple, List[Doc]] = {}
    for e in entries:
        groups.setdefault((e.category, normalize(e.description)), []).append(e)
    for group in groups.values():
        if len(group) > 1:
            newest = max(group, key=lambda e: (e.date, e.id))
            old = [e.id for e in group if e.id != newest.id]
            delete.update(old)
            report.decisions.append(Decision("duplicate", [newest.id] + old, f"kept {newest.id}, removed copies {old}"))
    remaining = [e for e in entries if e.id not in delete]

    # --- step B: the model points at problems, one category at a time; the code checks and decides ---
    by_category: Dict[str, List[Doc]] = {}
    for note in remaining:
        by_category.setdefault(note.category, []).append(note)
    readable = True
    for category, group in by_category.items():
        if len(group) < 2:                 # one note alone cannot be a duplicate or a contradiction
            continue
        client = client or get_client()
        report.used_model = True
        report.model_calls += 1
        try:
            proposal = _ask_group(category, group, client)
        except ModelError as exc:
            report.model_error, readable = str(exc), False
            break                          # the model is not reachable: stop asking
        if proposal is None:
            readable = False
            report.decisions.append(Decision("model_answer", [], f"the answer for category '{category}' was not readable JSON",
                                             accepted=False, reason="unreadable"))
            continue
        more_delete, more_create = _apply_group(proposal, group, report)
        delete |= more_delete
        create += more_create
    report.model_answer_readable = readable if report.used_model else None

    # --- step C: the safety net, if the memory is still too big ---
    survivors = [e for e in remaining if e.id not in delete]
    # Each candidate is (category, date, existing id or None, position in `create` or None).
    candidates = [(e.category, e.date, e.id, None) for e in survivors] + \
                 [(c["category"], c["date"], None, n) for n, c in enumerate(create)]
    if len(candidates) > TARGET_MAX:
        by_category: Dict[str, list] = {}
        # newest first; on the same date a merged (new) note counts as newer than an old one
        for item in sorted(candidates, key=lambda c: (c[1], c[2] if c[2] is not None else 10 ** 9), reverse=True):
            by_category.setdefault(item[0], []).append(item)
        dropped_notes = [i for items in by_category.values() for i in items[CAP_PER_CATEGORY:]]
        cut_ids = [i[2] for i in dropped_notes if i[2] is not None]
        cut_new = {i[3] for i in dropped_notes if i[3] is not None}
        delete.update(cut_ids)
        create = [c for n, c in enumerate(create) if n not in cut_new]
        report.decisions.append(Decision("fallback_cap", cut_ids, f"still over {TARGET_MAX} notes: kept the newest "
                                         f"{CAP_PER_CATEGORY} of each category, removed {len(dropped_notes)}"))

    # --- write: add the new notes first, then delete the old ones ---
    for c in create:
        memory.add_entry(db, student_id, c["category"], c["description"], on=date.fromisoformat(c["date"]),
                         source="consolidation")
    if delete:
        db.student_memory.delete_many({"_id": {"$in": sorted(delete)}, "student_id": student_id})
    report.after = mongo.count(db, "student_memory", {"student_id": student_id})
    return report


# ---------------------------------------------------------------------------
# The two Kafka handlers (handlers.py calls these)
# ---------------------------------------------------------------------------
PROCESSED, DUPLICATE = "processed", "duplicate"


def _payload_int(payload: dict, name: str) -> int:
    value = payload.get(name)
    if not _is_int(value):
        raise PermanentError(f"payload.{name} is missing or is not an integer")
    return value


def _record_run(db: Database, env, student_id: int, summary: dict) -> str:
    """The run log (collection memory_runs, _id = the event id). It makes the handler idempotent: the same event delivered
    twice is recognised and skipped. It is also the audit trail shown in the report."""
    try:
        db.memory_runs.insert_one({"_id": env.event_id, "event_type": env.event_type, "student_id": student_id,
                                   "trace_id": env.trace_id, "at": datetime.now(), **summary})
    except DuplicateKeyError:
        return DUPLICATE
    return PROCESSED


def _already_done(db: Database, env) -> bool:
    return db.memory_runs.count_documents({"_id": env.event_id}) > 0


class TimedClient(ModelClient):
    """Wraps the model client to count how long the model took and how many tokens it used (for the worker's trace)."""

    def __init__(self, inner: ModelClient):
        self.inner, self.model_ms, self.usage = inner, 0.0, Usage()

    def complete(self, messages, tools):
        began = time.perf_counter()
        try:
            reply = self.inner.complete(messages, tools)
        finally:
            self.model_ms += (time.perf_counter() - began) * 1000
        self.usage.add(reply)
        return reply


def queue_wait_ms(env) -> float:
    """How long the message waited in Kafka: from the moment it was published (envelope timestamp, UTC) to now, when the
    worker starts on it. In the one-process 'inline' mode there is no queue and this is about zero."""
    try:
        sent = datetime.fromisoformat(env.timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.0
    return max((datetime.now(timezone.utc) - sent).total_seconds() * 1000.0, 0.0)


@contextmanager
def _traced(db: Database, env, student_id: int):
    """Time the worker's part of a request and store it as a trace (kind memory_worker) with the request's trace id.
    Yields the model client to use, so the model time and tokens are counted."""
    waited = queue_wait_ms(env)                      # measured first: it is the time BEFORE the worker started
    client = TimedClient(get_client())
    began = time.perf_counter()
    status = "ok"
    with db_timing.measure() as timer:
        try:
            yield client
        except Exception:
            status = "error"
            raise
        finally:
            total = (time.perf_counter() - began) * 1000
            tracing.record(db, trace_id=env.trace_id, kind="memory_worker", student_id=student_id, status=status,
                           total_ms=total, detail=env.event_type, usage=client.usage.as_dict(),
                           stages=tracing.stages_from(client.model_ms, 0.0, timer.db_ms, 0.0, timer.db_calls, waited))


def handle_session_ended(db: Database, env) -> str:
    student_id, conversation_id = _payload_int(env.payload, "student_id"), env.payload.get("conversation_id")
    if not isinstance(conversation_id, str):
        raise PermanentError("payload.conversation_id is missing or is not text")
    if _already_done(db, env):
        return DUPLICATE
    if mongo.get(db, "students", student_id) is None:
        raise PermanentError(f"student {student_id} does not exist")
    raw = db.conversations.find_one({"_id": conversation_id})
    if raw is None or raw.get("student_id") != student_id:
        # The chat was already discarded (the one-day expiry) or is not this student's: nothing to learn, not an error.
        return _record_run(db, env, student_id, {"learned": 0, "note": "conversation not found"})
    with _traced(db, env, student_id) as client:
        added = learn(db, student_id, raw.get("messages") or [], client)
        summary = {"learned": len(added), "learned_ids": [e.id for e in added]}
        if mongo.count(db, "student_memory", {"student_id": student_id}) > CONSOLIDATE_ABOVE:
            summary["consolidation"] = consolidate(db, student_id, client).as_dict()
    logger.info("event=memory.session_ended student_id=%s learned=%s trace_id=%s", student_id, len(added), env.trace_id)
    return _record_run(db, env, student_id, summary)


def handle_consolidate(db: Database, env) -> str:
    student_id = _payload_int(env.payload, "student_id")
    if _already_done(db, env):
        return DUPLICATE
    if mongo.get(db, "students", student_id) is None:
        raise PermanentError(f"student {student_id} does not exist")
    with _traced(db, env, student_id) as client:
        report = consolidate(db, student_id, client)
    logger.info("event=memory.consolidate student_id=%s before=%s after=%s trace_id=%s",
                student_id, report.before, report.after, env.trace_id)
    return _record_run(db, env, student_id, {"consolidation": report.as_dict()})
