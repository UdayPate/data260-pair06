"""
Chat commands: a message that starts with "/" is handled here instead of by the model (no model call, so it is instant
and cannot be tricked by anything in the database).

    /memory               show what the assistant remembers about you
    /memory add <text>    add a note yourself ("/memory add I can only work 15 hours a week")
"""
from pymongo.database import Database

from ..mongo import Doc
from . import memory

MAX_SHOWN = 60
USAGE = "Commands: /memory (show what I remember about you), /memory add <note> (remember something)."


def is_command(message: str) -> bool:
    return message.lstrip().startswith("/")


def run_command(db: Database, student: Doc, message: str) -> str:
    """Run one command for the logged-in student and return the reply text."""
    name, _, rest = message.strip().partition(" ")
    if name.lower() != "/memory":
        return f"I do not know the command {name}. {USAGE}"
    sub, _, argument = rest.strip().partition(" ")
    if sub == "":
        return _show_memory(db, student)
    if sub.lower() == "add":
        entry = memory.add_entry(db, student.id, "note", argument, source="user")
        return "Okay, I will remember that." if entry else "Write the note after the command: /memory add <note>."
    return USAGE


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
