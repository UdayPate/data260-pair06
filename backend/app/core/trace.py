"""
The trace id of a request: one short token that follows a user's request through the API, Kafka and the workers
(it is in every Kafka message, header and body, and in the workers' log lines). The gateway puts a fresh
X-Request-ID on every request; a caller may also send its own X-Trace-ID. Anything else starts a new trace.
"""
from fastapi import Request

from ..events.envelope import clean_trace_id


def get_trace_id(request: Request) -> str:
    return clean_trace_id(request.headers.get("x-trace-id") or request.headers.get("x-request-id"))
