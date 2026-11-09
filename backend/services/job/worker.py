"""Job worker: when a job is posted, notifies the students whose saved preferences match it."""
from app.events import topics
from app.events.consumer import run_worker

if __name__ == "__main__":
    run_worker("job", [topics.JOB_CREATED])
