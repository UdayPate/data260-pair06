"""Event service (port 9066): events, registrations."""
from app.routers import events
from services.common import create_service_app

app = create_service_app(
    "event",
    "Post, search and view events; register students; list registrations.",
    routers=[events.router],
)
