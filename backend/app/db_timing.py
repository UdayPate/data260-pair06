"""
How long a request spent waiting for MongoDB (Lab 2, Part 6: stage timing).

pymongo can tell us, for every command it sends, how long the server took. A `CommandListener` is a small object we hand to
the MongoClient; pymongo calls it after each command. The listener adds that time to a counter that belongs to the
request being served, so a trace can say "this chat request spent 12 ms in the database".

The counter is stored in a ContextVar: a variable with one value per request (per thread of work), so two requests running
at the same time never mix their numbers. Code that is not inside a measured request (a seed script, a test) finds no
counter and the listener does nothing.

  with db_timing.measure() as t:        # one request
      ... run the request ...
  t.db_ms, t.db_calls                    # all MongoDB time and commands during it
  with db_timing.tool_scope():           # inside it: the part where a TOOL ran
      ...                                # t.tool_db_ms counts only MongoDB time spent in here
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional

from pymongo import monitoring


@dataclass
class DbTimer:
    db_ms: float = 0.0          # every MongoDB command during the request
    db_calls: int = 0
    tool_db_ms: float = 0.0     # the part of db_ms that happened while a tool was running
    in_tool: bool = False


_current: ContextVar[Optional[DbTimer]] = ContextVar("p06_db_timer", default=None)


@contextmanager
def measure() -> Iterator[DbTimer]:
    """Start counting MongoDB time for the code inside the `with` block."""
    timer = DbTimer()
    token = _current.set(timer)
    try:
        yield timer
    finally:
        _current.reset(token)


@contextmanager
def tool_scope() -> Iterator[None]:
    """Mark the code inside as 'a tool is running', so its MongoDB time is also counted as tool_db_ms."""
    timer = _current.get()
    if timer is None:
        yield
        return
    timer.in_tool = True
    try:
        yield
    finally:
        timer.in_tool = False


class TimingListener(monitoring.CommandListener):
    """pymongo calls these methods; only `succeeded` and `failed` carry a duration (in microseconds)."""

    def started(self, event):
        pass

    def _add(self, event):
        timer = _current.get()
        if timer is None:
            return
        ms = event.duration_micros / 1000.0
        timer.db_ms += ms
        timer.db_calls += 1
        if timer.in_tool:
            timer.tool_db_ms += ms

    def succeeded(self, event):
        self._add(event)

    def failed(self, event):
        self._add(event)


LISTENER = TimingListener()
