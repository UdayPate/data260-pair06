"""AI Assistant service (port 9067): the chat endpoint and the hand-built agent loop."""
from app.routers import assistant
from services.common import create_service_app

app = create_service_app(
    "assistant",
    "POST /assistant/chat: the hand-built agent loop with five tools (calls Ollama through one client).",
    routers=[assistant.router],
)
