"""
How the APIs hand events to Kafka.

    publisher.publish("application.created", key="12:7", payload={...}, trace_id="...")  ->  the Envelope that was sent

Two implementations:
  KafkaPublisher   the real thing. Used whenever the environment variable KAFKA_BOOTSTRAP is set (for example
                   p06-kafka:9092 in Docker Compose and Kubernetes). It waits until the broker has confirmed the message
                   (acks=all, idempotent producer) and raises PublishError if that does not happen within a few seconds.
  InlinePublisher  used when KAFKA_BOOTSTRAP is NOT set (running one app on a laptop without Kafka, and the tests). It
                   gives the event to the same handler the Kafka worker would run, right away, in the same process.
Either way the API code is identical and the handlers are the same code, so nothing behaves differently between them
except WHEN the handler runs (inline: before the API replies; Kafka: a moment later, in a worker).

The message key decides the partition: events with the same key are delivered in order, to the same worker.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from .envelope import Envelope, new_envelope, parse_envelope
from .errors import PublishError
from .topics import PARTITIONS, TOPICS, topic_for

logger = logging.getLogger("handshake.events")


class Publisher:
    mode = "base"

    def publish(self, event_type: str, key: str, payload: Dict[str, Any], trace_id: Optional[str] = None) -> Envelope:
        raise NotImplementedError


def ensure_topics(bootstrap: str, attempts: int = 30, wait_seconds: float = 2.0) -> None:
    """Create every p06.* topic that does not exist yet (safe to repeat). Waits for the broker to come up."""
    import time
    from confluent_kafka import KafkaException
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": bootstrap})
    for attempt in range(1, attempts + 1):
        try:
            existing = set(admin.list_topics(timeout=5).topics)
            wanted = [NewTopic(name, num_partitions=parts, replication_factor=1)
                      for name, parts in TOPICS.items() if name not in existing]
            for name, future in admin.create_topics(wanted).items() if wanted else []:
                try:
                    future.result()
                except KafkaException as exc:
                    if "TOPIC_ALREADY_EXISTS" not in str(exc):      # another process created it first: fine
                        raise
            return
        except KafkaException as exc:
            if attempt == attempts:
                raise PublishError(f"Kafka at {bootstrap} is not ready: {exc}") from exc
            time.sleep(wait_seconds)


class KafkaPublisher(Publisher):
    mode = "kafka"

    def __init__(self, bootstrap: str, producer_name: str = "p06", flush_seconds: float = 8.0):
        self.bootstrap, self.producer_name, self.flush_seconds = bootstrap, producer_name, flush_seconds
        self._producer = None
        self._topics_ready = False

    def _ready_producer(self):
        from confluent_kafka import Producer                  # imported here: only the images that publish need the library
        if not self._topics_ready:
            ensure_topics(self.bootstrap, attempts=2, wait_seconds=1.0)
            self._topics_ready = True
        if self._producer is None:
            self._producer = Producer({
                "bootstrap.servers": self.bootstrap, "client.id": self.producer_name,
                "acks": "all", "enable.idempotence": True,        # no losses, no duplicates from retries inside the producer
                "message.timeout.ms": int(self.flush_seconds * 1000) - 500,
            })
        return self._producer

    def publish(self, event_type: str, key: str, payload: Dict[str, Any], trace_id: Optional[str] = None) -> Envelope:
        envelope = new_envelope(event_type, payload, trace_id, self.producer_name)
        errors: List[Any] = []
        try:
            producer = self._ready_producer()
            producer.produce(topic_for(event_type), key=key.encode(), value=envelope.to_json().encode(),
                             headers=envelope.headers(), on_delivery=lambda err, _msg: errors.append(err) if err else None)
            not_sent = producer.flush(self.flush_seconds)
        except PublishError:
            raise
        except Exception as exc:                              # BufferError, KafkaException, ...
            raise PublishError(f"could not send {event_type}: {exc}") from exc
        if not_sent or errors:
            raise PublishError(f"Kafka did not confirm {event_type}: {errors[0] if errors else 'timed out'}")
        logger.info("event=published type=%s event_id=%s key=%s trace_id=%s", event_type, envelope.event_id, key,
                    envelope.trace_id)
        return envelope


class InlinePublisher(Publisher):
    mode = "inline"

    def publish(self, event_type: str, key: str, payload: Dict[str, Any], trace_id: Optional[str] = None) -> Envelope:
        from .. import mongo
        from .handlers import dispatch
        envelope = new_envelope(event_type, payload, trace_id, os.getenv("P06_SERVICE", "p06"))
        parse_envelope(envelope.to_json(), envelope.headers())        # same checks a worker would make
        try:
            dispatch(mongo.get_database(), envelope)
        except Exception as exc:
            raise PublishError(f"inline handler for {event_type} failed: {exc}") from exc
        return envelope


_publisher: Optional[Publisher] = None


def get_publisher() -> Publisher:
    """FastAPI dependency (and plain function): the publisher of this process."""
    global _publisher
    if _publisher is None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP", "").strip()
        _publisher = KafkaPublisher(bootstrap, os.getenv("P06_SERVICE", "p06")) if bootstrap else InlinePublisher()
        logger.info("events: %s", f"kafka at {bootstrap}" if bootstrap else "inline (KAFKA_BOOTSTRAP is not set)")
    return _publisher


def use_publisher(publisher: Optional[Publisher]) -> None:
    """The tests call this to plug in their own publisher (None = back to the one chosen by the environment)."""
    global _publisher
    _publisher = publisher


def publish_quietly(publisher: Publisher, event_type: str, key: str, payload: Dict[str, Any],
                    trace_id: Optional[str] = None) -> Optional[Envelope]:
    """For events whose main action is already saved (a status change, a registration, a new job): a Kafka problem is
    logged and the user's request still succeeds. (The notification for that action is then lost: see KAFKA_CONTRACT.md,
    "Known limits".)"""
    try:
        return publisher.publish(event_type, key, payload, trace_id)
    except PublishError as exc:
        logger.error("event=publish_failed type=%s key=%s trace_id=%s error=%s", event_type, key, trace_id, exc)
        return None
