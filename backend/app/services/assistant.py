"""
The chat endpoint's entry point. The router and the React chat window call ONLY this function:

    run_assistant(db, student, message, conversation_id) -> ChatResponse

It opens (or starts) the conversation for this student, hands the work to the hand-built agent loop in
app/assistant/agent.py, and saves the conversation again. A message that starts with "/" is a command (/memory) and
never reaches the model.

Lab 2: conversations are stored in MongoDB (collection `conversations`, see assistant/conversation_store.py), so any
assistant pod can continue any chat and a restart loses nothing. Memory layers 1 and 2 (the standing rules and the notes
learned about this student) are read from MongoDB for every message and added to the system prompt.
"""
import uuid
from typing import Optional

from pymongo.database import Database

from ..assistant import commands, conversation_store, memory
from ..assistant.agent import Conversation, run_assistant as run_agent
from ..assistant.model_client import ModelClient
from ..assistant.tools import ToolContext
from ..mongo import Doc
from ..schemas.assistant import ChatResponse, ToolCall

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


def run_assistant(db: Database, student: Doc, message: str,
                  conversation_id: Optional[str] = None) -> ChatResponse:
    if commands.is_command(message):
        reply = commands.run_command(db, student, message)
        return ChatResponse(reply=reply, conversation_id=conversation_id or new_conversation_id(), tool_calls=[])

    conversation = _open_conversation(db, student.id, conversation_id)
    memory.ensure_default_rules(db)
    ctx = ToolContext(db=db, student=student, rules=memory.load_rules(db),
                      memory_lines=memory.prompt_lines(memory.list_entries(db, student.id)))
    result = run_agent(message, conversation, ctx, client=model_client)
    conversation_store.save(db, conversation)
    return ChatResponse(
        reply=result.reply,
        conversation_id=conversation.conversation_id,
        tool_calls=[ToolCall(name=r.name, arguments=r.arguments, result=r.result[:RESULT_PREVIEW_CHARS])
                    for r in result.tool_calls],
    )
