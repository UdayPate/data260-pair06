"""
The shape of the chat endpoint. This is the CONTRACT between the website (Part A) and the AI
assistant (Parts B and C), so both partners can work at the same time:

    POST /assistant/chat
    request : { "message": "find me an internship in my city", "conversation_id": null }
    response: { "reply": "...", "conversation_id": "…", "tool_calls": [ {name, arguments, result} ] }

Send back the same conversation_id on the next message to continue the same conversation.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(description="What the student typed")
    conversation_id: Optional[str] = Field(None, max_length=64,
                                           description="Empty for a new conversation; echo it back to continue one")

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Type a message first")
        if len(v) > 2000:
            raise ValueError("Messages can be at most 2000 characters")
        return v


class ToolCall(BaseModel):
    """One tool the assistant used while answering, shown to the student as 'Tools used'."""
    name: str = Field(description="e.g. search_jobs")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = Field(None, description="A short summary or the raw result")


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
