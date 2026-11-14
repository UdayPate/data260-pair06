"""
The chat endpoint's entry point. The router and the React chat window call ONLY this function:

    run_assistant(db, student, message, conversation_id, trace_id) -> ChatResponse

It opens (or starts) the conversation for this student, hands the work to the hand-built agent loop in
app/assistant/agent.py, and saves the conversation again. A message that starts with "/" is a command (/memory, /compact,
/trace) and never reaches the model.

Lab 2:
  * conversations are stored in MongoDB (assistant/conversation_store.py), so any assistant pod can continue any chat;
  * the standing rules and the notes learned about this student (memory layers 1 and 2) are added to the system prompt;
  * every request gets a trace id, is timed stage by stage, and leaves one trace document and one log line
    (assistant/tracing.py); the response carries the trace id and the token usage;
  * when the context window is 85 percent full the history is compacted into a summary (assistant/compaction.py).
"""
import logging
import time
import uuid
from typing import Optional

from pymongo.database import Database

from .. import db_timing
from ..assistant import commands, compaction, conversation_store, memory, tracing
from ..assistant.agent import Conversation, run_assistant as run_agent
from ..assistant.model_client import ModelClient
from ..assistant.tools import ToolContext
from ..assistant.usage import COMPACT_AT_PERCENT
from ..events.envelope import clean_trace_id
from ..mongo import Doc
from ..schemas.assistant import ChatResponse, ToolCall

logger = logging.getLogger("handshake.assistant")

RESULT_PREVIEW_CHARS = 600       # the chat window only shows a short preview of each tool result

# Tests replace this with a fake model so they never need Ollama.
model_client: Optional[ModelClient] = None


def new_conversation_id() -> str:
    return uuid.uuid4().hex


def _open_conversation(db: Database, student_id: int, conversation_id: Optional[str]) -> Conversation:
    """The student's stored conversation. An unknown id starts a new conversation under that id; an id that belongs
    to another student is never reused (the student gets a fresh conversation with a new id)."""
    if conversation_id:
        mine = conversation_store.load(db, student_id, conversation_id)
        if mine is not None:
            return mine
        if not conversation_store.exists(db, conversation_id):
            return Conversation(conversation_id=conversation_id, student_id=student_id)
    return Conversation(conversation_id=new_conversation_id(), student_id=student_id)


def _usage_of(db: Database, student_id: int, conversation_id: Optional[str]) -> Optional[dict]:
    """The usage numbers of a stored conversation (for the reply to a command)."""
    stored = conversation_store.load(db, student_id, conversation_id) if conversation_id else None
    if stored is None:
        return None
    return {**stored.usage.as_dict(), "compactions": stored.compactions}


def run_assistant(db: Database, student: Doc, message: str,
                  conversation_id: Optional[str] = None, trace_id: Optional[str] = None) -> ChatResponse:
    trace_id = clean_trace_id(trace_id)                       # a missing or odd id becomes a fresh, valid one
    began = time.perf_counter()
    with db_timing.measure() as timer:                        # counts the time MongoDB takes during this request
        response, info = _handle(db, student, message, conversation_id, trace_id)
    total_ms = (time.perf_counter() - began) * 1000
    stages = tracing.stages_from(info["model_ms"], info["tool_ms"], timer.db_ms, timer.tool_db_ms, timer.db_calls)
    tracing.record(db, trace_id=trace_id, kind="chat", student_id=student.id, status=info["status"], total_ms=total_ms,
                   stages=stages, usage=info["usage"], tools=info["tools"], detail=info["detail"])
    response.trace_id = trace_id
    return response


def _handle(db: Database, student: Doc, message: str, conversation_id: Optional[str], trace_id: str):
    """Do the work; returns (the response, what the trace needs to know)."""
    info = {"model_ms": 0.0, "tool_ms": 0.0, "status": "ok", "usage": None, "tools": [], "detail": None}

    if commands.is_command(message):
        reply = commands.run_command(db, student, message, conversation_id, trace_id)
        info["detail"] = "command " + message.strip().split(" ", 1)[0].lower()
        usage = _usage_of(db, student.id, conversation_id)
        return ChatResponse(reply=reply, conversation_id=conversation_id or new_conversation_id(), tool_calls=[],
                            usage=usage), info

    conversation = _open_conversation(db, student.id, conversation_id)
    memory.ensure_default_rules(db)
    ctx = ToolContext(db=db, student=student, rules=memory.load_rules(db),
                      memory_lines=memory.prompt_lines(memory.list_entries(db, student.id)))
    result = run_agent(message, conversation, ctx, client=model_client,
                       log=lambda line: logger.info("assistant trace_id=%s %s", trace_id, line))

    compacted = None
    if conversation.usage.exact_percent() >= COMPACT_AT_PERCENT:   # the window is nearly full: replace the history by a summary
        compacted = compaction.compact(conversation, db, student)
    conversation_store.save(db, conversation)

    usage = {**conversation.usage.as_dict(), "compactions": conversation.compactions}
    if compacted and compacted.get("compacted"):
        usage["compacted_now"] = {k: compacted[k] for k in (
            "messages_before", "messages_after", "estimated_history_tokens_before", "estimated_history_tokens_after")}
    info.update(model_ms=result.stages.get("model_ms", 0.0), tool_ms=result.stages.get("tool_ms", 0.0),
                status=result.error or "ok", usage=result.usage.as_dict(), tools=[r.name for r in result.tool_calls])
    return ChatResponse(
        reply=result.reply,
        conversation_id=conversation.conversation_id,
        tool_calls=[ToolCall(name=r.name, arguments=r.arguments, result=r.result[:RESULT_PREVIEW_CHARS])
                    for r in result.tool_calls],
        usage=usage,
    ), info
