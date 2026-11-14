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
  B. The model reads the remaining notes and proposes decisions as JSON, by id:
       merges          several notes that say the same thing  ->  one note
       contradictions  notes that cannot both be true         ->  keep the NEWER one
       drop            one-off notes that no longer matter (a past event the student went to)
     Every decision is checked by code before it is applied (ids must exist and be used once; a "contradiction" must
     keep the newer note; only one-off categories may be dropped). A decision that fails a check is rejected and written
     to the report, so a model mistake can never delete a note it had no right to delete.
  C. If the memory is still at or above TARGET_MAX notes (the model failed, was unreachable, or did too little), a
     deterministic safety net keeps only the newest CAP_PER_CATEGORY notes of each category.
Writes happen as "add the merged notes, then delete the old ones": a crash in between leaves duplicates (merged by the
next run), never a lost fact.
"""
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Set

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import mongo
from ..events.errors import PermanentError
from ..mongo import Doc
from . import memory
from .model_client import ModelClient, ModelError, OllamaClient

logger = logging.getLogger("handshake.memory")

TARGET_MAX = 39               # the assignment: the result must be BELOW 40 entries
CAP_PER_CATEGORY = 4          # safety net: 8 categories x 4 = at most 32 notes
CONSOLIDATE_ABOVE = 40        # after learning, consolidate when the student has more notes than this
LEARN_LIMIT = 8               # at most this many new notes from one conversation
DROPPABLE = {"event", "application", "note"}      # one-off categories the model may drop outright
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

    def as_dict(self) -> dict:
        return {"before": self.before, "after": self.after, "used_model": self.used_model,
                "model_error": self.model_error, "model_answer_readable": self.model_answer_readable,
                "decisions": [d.__dict__ for d in self.decisions]}


CONSOLIDATE_PROMPT = """You tidy a student's long-term notes for a career assistant. Each note is: id | date | category | text.
Propose changes as JSON, using only ids that appear in the list:
  "merges": notes that say the same thing in different words -> {"ids": [..], "category": "...", "description": "one short sentence that keeps every distinct fact"}
  "contradictions": notes that cannot both be true now -> {"keep": id, "drop": [ids]}  (keep the note with the NEWER date)
  "drop": ids of one-off notes that no longer matter, such as a past event or application
Rules: an id may appear in only one change. Do not merge notes about different things. Never invent facts.
Answer with ONLY this JSON: {"merges": [], "contradictions": [], "drop": []}"""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _ask_model(entries: List[Doc], client: ModelClient) -> Optional[dict]:
    listing = "\n".join(f"{e.id} | {e.date} | {e.category} | {e.description}" for e in entries)
    reply = client.complete([{"role": "system", "content": CONSOLIDATE_PROMPT}, {"role": "user", "content": listing}], [])
    proposal = parse_json(reply.content)
    return proposal if isinstance(proposal, dict) else None


def _apply_proposal(proposal: dict, by_id: Dict[int, Doc], report: Report):
    """Check each proposed decision and keep the valid ones. Returns (ids to delete, notes to create)."""
    delete: Set[int] = set()
    create: List[dict] = []
    used: Set[int] = set()            # every id may take part in only one decision

    def reject(kind: str, ids, detail: str, reason: str):
        report.decisions.append(Decision(kind, [i for i in ids if _is_int(i)], detail, accepted=False, reason=reason))

    def usable(ids) -> Optional[str]:
        if not isinstance(ids, list) or not ids or not all(_is_int(i) for i in ids):
            return "ids must be a non-empty list of whole numbers"
        if any(i not in by_id for i in ids):
            return "an id is not in the memory"
        if len(set(ids)) != len(ids) or any(i in used for i in ids):
            return "an id was used twice"
        return None

    for item in proposal.get("merges") or []:
        item = item if isinstance(item, dict) else {}
        ids, text = item.get("ids"), item.get("description")
        problem = usable(ids) or (None if isinstance(ids, list) and len(ids) >= 2 else "a merge needs at least two ids") \
            or (None if isinstance(text, str) and memory.clean_description(text) else "the merged description is empty")
        if problem:
            reject("merge", ids if isinstance(ids, list) else [], str(text), problem)
            continue
        members = [by_id[i] for i in ids]
        category = memory.clean_category(item.get("category") if isinstance(item.get("category"), str) else members[0].category)
        create.append({"category": category, "description": text, "date": max(m.date for m in members)})
        delete.update(ids)
        used.update(ids)
        report.decisions.append(Decision("merge", list(ids), f"merged into: {memory.clean_description(text)}"))

    for item in proposal.get("contradictions") or []:
        item = item if isinstance(item, dict) else {}
        keep, drop = item.get("keep"), item.get("drop")
        problem = usable(([keep] if _is_int(keep) else []) + (drop if isinstance(drop, list) else [])) \
            or (None if _is_int(keep) and isinstance(drop, list) and drop else "keep must be one id and drop a list")
        if not problem and any(by_id[i].date > by_id[keep].date for i in drop):
            problem = "the note it kept is OLDER than a note it dropped (the newer note must win)"
        if problem:
            reject("contradiction", ([keep] if _is_int(keep) else []) + (drop if isinstance(drop, list) else []), "", problem)
            continue
        delete.update(drop)
        used.update(drop + [keep])
        report.decisions.append(Decision("contradiction", [keep] + drop,
                                         f"kept {keep} ({by_id[keep].description}), dropped {drop}"))

    drop_ids = proposal.get("drop") or []
    for i in drop_ids if isinstance(drop_ids, list) else []:
        problem = usable([i]) or (None if by_id.get(i) and by_id[i].category in DROPPABLE
                                  else "only one-off notes (event, application, note) may be dropped")
        if problem:
            reject("drop", [i], "", problem)
            continue
        delete.add(i)
        used.add(i)
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

    # --- step B: the model proposes, the code checks ---
    if len(remaining) >= 2:
        client = client or get_client()
        report.used_model = True
        try:
            proposal = _ask_model(remaining, client)
        except ModelError as exc:
            proposal, report.model_error = None, str(exc)
        report.model_answer_readable = proposal is not None
        if proposal is not None:
            more_delete, create = _apply_proposal(proposal, {e.id: e for e in remaining}, report)
            delete |= more_delete

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
    client = get_client()
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
    report = consolidate(db, student_id)
    logger.info("event=memory.consolidate student_id=%s before=%s after=%s trace_id=%s",
                student_id, report.before, report.after, env.trace_id)
    return _record_run(db, env, student_id, {"consolidation": report.as_dict()})
