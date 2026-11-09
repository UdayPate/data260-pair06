"""AI Assistant service (port 9067): the chat endpoint and the hand-built agent loop."""
from app.routers import assistant
from services.assistant import dependencies
from services.common import create_service_app

app = create_service_app(
    "assistant",
    "POST /assistant/chat: the hand-built agent loop with five tools (calls Ollama through one client).",
    routers=[assistant.router],
)


@app.get("/health/dependencies", tags=["Health"],
         summary="Can the assistant reach MongoDB, the platform services, Kafka and the model server?")
def health_dependencies():
    return dependencies.report()
