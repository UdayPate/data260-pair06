"""
THE PLACEHOLDER ASSISTANT.

Part A ships the website and the chat endpoint; Parts B and C (your partner) replace the body
of run_assistant() with the real Ollama agent loop. NOTHING ELSE needs to change: the router,
the schemas and the React chat window already call this one function.

    run_assistant(db, student, message, conversation_id) -> ChatResponse

Inside the real version you can reuse the same code the website uses, so the assistant and the
website can never disagree:
    from .jobs import search_jobs                     # GET /jobs
    from .events import search_events                 # GET /events
    from .preferences import get_student_preferences  # GET /students/me/preferences
"""
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Student
from ..schemas.assistant import ChatResponse


def new_conversation_id() -> str:
    return uuid.uuid4().hex


def run_assistant(db: Session, student: Student, message: str,
                  conversation_id: Optional[str] = None) -> ChatResponse:
    """Placeholder: replace this body with the agent loop (Part B)."""
    return ChatResponse(
        reply=("The AI assistant is not connected yet. "
               f"I received your message ({len(message)} characters) and will be able to search jobs "
               "and events for you once Part B is plugged in."),
        conversation_id=conversation_id or new_conversation_id(),
        tool_calls=[],
    )
