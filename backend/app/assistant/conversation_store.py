"""
Memory layer 3: the current conversation, stored in the `conversations` collection (Lab 2, Part 3).

In Lab 1 a conversation lived in a Python dictionary inside one process. With several assistant pods (Kubernetes) the next
message of a chat could reach a pod that never saw it, and a restart lost everything. Now every message exchange is
saved to MongoDB, so any pod can continue any conversation.

A conversation document:
    _id          the conversation_id (a text token; the one exception to "integer ids", because the browser holds it)
    student_id   whose conversation it is (nobody else can open it)
    messages     the user / assistant / tool messages, without the system prompt
    pending      a save waiting for the student's yes or no, or null
    created_at, updated_at

MongoDB deletes a conversation by itself one day after its last message (TTL index on updated_at, see mongo.INDEXES):
"discarded at session end". Compaction (Part 6) replaces `messages` with a short summary instead.
"""
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from pymongo.database import Database

from .agent import Conversation, PendingAction


def _safe(value):
    """MongoDB field names may not contain '.' or start with '$'. The model chooses the names of tool arguments, so
    clean every key before storing."""
    if isinstance(value, dict):
        return {(("_" + str(k)[1:]) if str(k).startswith("$") else str(k)).replace(".", "_"): _safe(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


def exists(db: Database, conversation_id: str) -> bool:
    return db.conversations.count_documents({"_id": conversation_id}) > 0


def load(db: Database, student_id: int, conversation_id: str) -> Optional[Conversation]:
    """The conversation, or None when it does not exist or belongs to another student."""
    raw = db.conversations.find_one({"_id": conversation_id})
    if raw is None or raw.get("student_id") != student_id:
        return None
    pending = PendingAction(**raw["pending"]) if raw.get("pending") else None
    return Conversation(conversation_id=conversation_id, student_id=student_id,
                        messages=list(raw.get("messages") or []), pending=pending)


def save(db: Database, conversation: Conversation) -> None:
    now = datetime.now()
    db.conversations.update_one(
        {"_id": conversation.conversation_id},
        {"$set": {"student_id": conversation.student_id, "messages": _safe(conversation.messages),
                  "pending": _safe(asdict(conversation.pending)) if conversation.pending else None,
                  "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True)
