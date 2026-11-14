"""Memory worker (Lab 2, Part 3): learns notes from finished chats and consolidates a student's memory.

It runs in the Assistant image (the one with the model client) and reads two topics:
  p06.memory.session_ended          learn notes from a chat, then consolidate if the student has many
  p06.memory.consolidate_requested  consolidate now
The slow part (the model call) happens here, never inside a chat request. See app/assistant/memory_consolidation.py.
"""
from app.events import topics
from app.events.consumer import run_worker

if __name__ == "__main__":
    run_worker("memory", [topics.MEMORY_SESSION_ENDED, topics.MEMORY_CONSOLIDATE_REQUESTED])
