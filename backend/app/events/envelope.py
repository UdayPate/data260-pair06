"""
The message format every Kafka message in this project uses (the "envelope"). The message VALUE is this JSON object:

    {"event_id": "<uuid>",            unique per event: the key to idempotency (processing it twice changes nothing)
     "event_type": "application.created",
     "timestamp": "2026-11-08T18:44:50.123456Z",   when the event was created (UTC)
     "trace_id": "<id>",              follows one user request through the API, Kafka and the workers
     "producer": "p06-application",   which service made it
     "schema_version": 1,
     "payload": {...}}                the event's own data (see KAFKA_CONTRACT.md)

and the Kafka HEADERS repeat the three things a consumer may want before it parses the body:
    event_id, event_type, trace_id
(headers are text bytes). If a header and the body disagree, the message is rejected as invalid.
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .errors import InvalidMessage
from .topics import EVENT_TYPES

REQUIRED = ("event_id", "event_type", "timestamp", "trace_id", "payload")
_TRACE_OK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def clean_trace_id(value: Optional[str]) -> str:
    """Use the caller's trace id when it is a sane short token, otherwise start a new trace."""
    return value if value and _TRACE_OK.match(value) else uuid.uuid4().hex


@dataclass
class Envelope:
    event_id: str
    event_type: str
    timestamp: str
    trace_id: str
    payload: Dict[str, Any]
    producer: str = ""
    schema_version: int = 1

    def to_json(self) -> str:
        return json.dumps(self.__dict__, separators=(",", ":"), default=str)

    def headers(self) -> List[Tuple[str, bytes]]:
        return [("event_id", self.event_id.encode()), ("event_type", self.event_type.encode()),
                ("trace_id", self.trace_id.encode())]


def new_envelope(event_type: str, payload: Dict[str, Any], trace_id: Optional[str] = None,
                 producer: str = "") -> Envelope:
    return Envelope(event_id=str(uuid.uuid4()), event_type=event_type, timestamp=utc_timestamp(),
                    trace_id=clean_trace_id(trace_id), payload=payload, producer=producer)


def parse_envelope(value: Any, headers: Optional[List[Tuple[str, Any]]] = None) -> Envelope:
    """Bytes (or text) from a topic -> Envelope. Raises InvalidMessage for anything that is not a valid envelope."""
    try:
        text = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else value
        body = json.loads(text)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise InvalidMessage(f"the message is not valid JSON ({exc})") from None
    if not isinstance(body, dict):
        raise InvalidMessage("the message is not a JSON object")
    missing = [name for name in REQUIRED if name not in body]
    if missing:
        raise InvalidMessage(f"missing field(s): {', '.join(missing)}")
    try:
        uuid.UUID(str(body["event_id"]))
    except ValueError:
        raise InvalidMessage("event_id is not a UUID") from None
    if not isinstance(body["event_type"], str) or body["event_type"] not in EVENT_TYPES:
        raise InvalidMessage(f"unknown event_type {body['event_type']!r}")
    if not isinstance(body["trace_id"], str) or not body["trace_id"]:
        raise InvalidMessage("trace_id is empty")
    if not isinstance(body["payload"], dict):
        raise InvalidMessage("payload is not an object")
    try:
        datetime.fromisoformat(str(body["timestamp"]).replace("Z", "+00:00"))
    except ValueError:
        raise InvalidMessage("timestamp is not an ISO 8601 time") from None
    for name, raw in (headers or []):                       # headers must agree with the body
        if name in ("event_id", "event_type", "trace_id") and raw is not None:
            if (raw.decode() if isinstance(raw, (bytes, bytearray)) else raw) != body[name]:
                raise InvalidMessage(f"header {name} does not match the message body")
    return Envelope(event_id=str(body["event_id"]), event_type=body["event_type"], timestamp=str(body["timestamp"]),
                    trace_id=body["trace_id"], payload=body["payload"], producer=str(body.get("producer", "")),
                    schema_version=int(body.get("schema_version", 1)))
