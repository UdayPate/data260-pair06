"""Event worker: confirms event registrations."""
from app.events import topics
from app.events.consumer import run_worker

if __name__ == "__main__":
    run_worker("event", [topics.EVENT_REGISTRATION_CREATED])
