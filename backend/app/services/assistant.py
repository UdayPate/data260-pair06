"""
The chat endpoint's entry point. The router and the React chat window call ONLY this function:

    run_assistant(db, student, message, conversation_id) -> ChatResponse

It looks up (or starts) the conversation for this student and hands the work to the
hand-built agent loop in app/assistant/agent.py.

Conversations live in memory, so they are lost when the server restarts. That is fine for this
lab: the history only has to last for a chat session.
"""
import uuid
from typing import Dict, Optional

from sqlalchemy.orm import Session

from ..assistant.agent import Conversation, run_assistant as run_agent
from ..assistant.model_client import ModelClient
from ..assistant.tools import ToolContext
from ..models import Student
from ..schemas.assistant import ChatResponse, ToolCall

_CONVERSATIONS: Dict[str, Conversation] = {}
MAX_CONVERSATIONS = 500          # oldest conversations are forgotten beyond this
RESULT_PREVIEW_CHARS = 600       # the chat window only shows a short preview of each tool result

# Tests replace this with a fake model so they never need Ollama.
model_client: Optional[ModelClient] = None


def new_conversation_id() -> str:
    return uuid.uuid4().hex


def _get_conversation(student_id: int, conversation_id: Optional[str]) -> Conversation:
    """An id that belongs to another student (or an unknown id) starts a fresh conversation."""
    existing = _CONVERSATIONS.get(conversation_id) if conversation_id else None
    if existing is not None and existing.student_id == student_id:
        return existing
    conversation = Conversation(conversation_id=conversation_id if existing is None and conversation_id
                                else new_conversation_id(), student_id=student_id)
    if len(_CONVERSATIONS) >= MAX_CONVERSATIONS:
        _CONVERSATIONS.pop(next(iter(_CONVERSATIONS)))
    _CONVERSATIONS[conversation.conversation_id] = conversation
    return conversation


def run_assistant(db: Session, student: Student, message: str,
                  conversation_id: Optional[str] = None) -> ChatResponse:
    conversation = _get_conversation(student.id, conversation_id)
    result = run_agent(message, conversation, ToolContext(db=db, student=student), client=model_client)
    return ChatResponse(
        reply=result.reply,
        conversation_id=conversation.conversation_id,
        tool_calls=[ToolCall(name=r.name, arguments=r.arguments, result=r.result[:RESULT_PREVIEW_CHARS])
                    for r in result.tool_calls],
    )
