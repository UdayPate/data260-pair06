"""Application worker: turns application.created into a saved application, and tells the student about status changes."""
from app.events import topics
from app.events.consumer import run_worker

if __name__ == "__main__":
    run_worker("application", [topics.APPLICATION_CREATED, topics.APPLICATION_UPDATED, topics.APPLICATION_STATUS_CHANGED])
