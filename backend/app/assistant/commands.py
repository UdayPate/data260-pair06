"""
Chat commands: a message that starts with "/" is handled here instead of by the model (no model call, so it is instant
and cannot be tricked by anything in the database).

    /memory                 show what the assistant remembers about you
    /memory add <text>      add a note yourself ("/memory add I can only work 15 hours a week")
    /memory learn           ask the assistant to learn notes from THIS chat (runs in the background, in a Kafka worker)
    /memory consolidate     tidy your notes: merge duplicates, resolve contradictions (also in the background)
"""
from typing import Optional

from pymongo.database import Database

from ..events import topics
from ..events.publisher import get_publisher, publish_quietly
from ..mongo import Doc
from . import conversation_store, memory

MAX_SHOWN = 60
USAGE = ("Commands: /memory (show what I remember about you), /memory add <note> (remember something), "
         "/memory learn (learn from this chat), /memory consolidate (tidy my notes about you).")


def is_command(message: str) -> bool:
    return message.lstrip().startswith("/")


def run_command(db: Database, student: Doc, message: str, conversation_id: Optional[str] = None,
                trace_id: Optional[str] = None) -> str:
    """Run one command for the logged-in student and return the reply text."""
    name, _, rest = message.strip().partition(" ")
    if name.lower() != "/memory":
        return f"I do not know the command {name}. {USAGE}"
    sub, _, argument = rest.strip().partition(" ")
    sub = sub.lower()
    if sub == "":
        return _show_memory(db, student)
    if sub == "add":
        entry = memory.add_entry(db, student.id, "note", argument, source="user")
        return "Okay, I will remember that." if entry else "Write the note after the command: /memory add <note>."
    if sub == "learn":
        if not conversation_id or not conversation_store.exists(db, conversation_id):
            return "There is no chat to learn from yet. Talk to me first, then use /memory learn."
        return _queue(topics.MEMORY_SESSION_ENDED, student, trace_id,
                      {"student_id": student.id, "conversation_id": conversation_id},
                      "I will learn from this chat")
    if sub == "consolidate":
        return _queue(topics.MEMORY_CONSOLIDATE_REQUESTED, student, trace_id, {"student_id": student.id},
                      "I will tidy my notes about you")
    return USAGE


def _queue(event_type: str, student: Doc, trace_id: Optional[str], payload: dict, what: str) -> str:
    """Publish the event; a worker does the slow part. The chat does not wait for the model."""
    publisher = get_publisher()
    envelope = publish_quietly(publisher, event_type, str(student.id), payload, trace_id)
    if envelope is None:
        return "I could not queue that right now (the message queue is not reachable). Please try again in a moment."
    when = "now (this setup has no message queue, so it ran straight away)" if publisher.mode == "inline" \
        else "in the background; check with /memory in a minute"
    return f"{what} {when}."


def _show_memory(db: Database, student: Doc) -> str:
    entries = memory.list_entries(db, student.id)
    rules = memory.load_rules(db)
    if not entries:
        return (f"I have not saved any notes about you yet. I follow {len(rules)} standing rules. "
                "Add one with /memory add <note>.")
    shown = entries[-MAX_SHOWN:]
    lines = [f"What I remember about you ({len(entries)} notes, oldest first; date | category | note):"]
    if len(entries) > len(shown):
        lines.append(f"(showing the newest {len(shown)})")
    lines += [memory.format_line(e) for e in shown]
    lines.append(f"I follow {len(rules)} standing rules.")
    return "\n".join(lines)
