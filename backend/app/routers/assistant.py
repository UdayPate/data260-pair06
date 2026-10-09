"""
The AI assistant's chat endpoint (students only).

    POST /assistant/chat   send one message, get the assistant's reply and the tools it used

The student comes from the login token, never from the request body, so the assistant can
only ever act for the person who is logged in. The real answering logic lives in
services/assistant.py (Part B).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.deps import require_student
from ..database import get_db
from ..models import Student
from ..schemas.assistant import ChatRequest, ChatResponse
from ..services.assistant import run_assistant

router = APIRouter(prefix="/assistant", tags=["AI assistant"])


@router.post("/chat", response_model=ChatResponse, summary="Send a message to the AI assistant (student only)")
def chat(body: ChatRequest, student: Student = Depends(require_student), db: Session = Depends(get_db)):
    return run_assistant(db, student, body.message, body.conversation_id)
