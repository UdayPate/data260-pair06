"""
The worker loop: read messages from Kafka, run the handler, and COMMIT THE OFFSET ONLY AFTER the database write.

    poll -> parse -> handler (up to MAX_ATTEMPTS tries) -> commit

* Commit after the write: Kafka remembers how far a consumer group has read (the "offset"). We store it only when the
  database write is done. If the worker is killed before that, the message is read again after the restart: it is not
  lost, it is reprocessed, and because the handlers are idempotent the second run changes nothing.
* Bounded retries: a handler that fails for a temporary reason is tried again (MAX_ATTEMPTS in total, with a pause).
* Dead-letter topic: a message that can never succeed (invalid, or a PermanentError), or one that still fails after the
  last attempt, is copied to p06.dlq together with the reason, and THEN its offset is committed. The worker moves on, so
  one bad message never blocks the ones behind it.
* If even the dead-letter write fails, the worker stops (the container restarts it) without committing: the message is
  never silently dropped.
"""
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

from pymongo.database import Database

from .. import mongo
from .envelope import parse_envelope
from .errors import InvalidMessage, PermanentError, PublishError
from .handlers import dispatch
from .topics import DLQ_TOPIC, topic_for

logger = logging.getLogger("handshake.worker")

MAX_ATTEMPTS = 3                       # the first try plus two retries
BACKOFF_SECONDS = (1.0, 2.0)           # the pause before retry 1 and retry 2
HEARTBEAT_FILE = os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/p06-worker-heartbeat")


class WorkerFatal(Exception):
    """The worker cannot continue safely (for example the dead-letter write failed)."""


def _text(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    return raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)


class Worker:
    def __init__(self, name: str, group_id: str, consumer: Any, producer: Any, db: Database,
                 sleep: Callable[[float], None] = time.sleep, heartbeat: Optional[Callable[[], None]] = None):
        self.name, self.group_id = name, group_id
        self.consumer, self.producer, self.db = consumer, producer, db
        self.sleep, self.heartbeat = sleep, heartbeat or (lambda: None)
        self.stopping = False

    # ---------------------------------------------------------------- one message
    def process(self, msg: Any) -> str:
        """Handle one message completely and commit it. Returns "processed", "duplicate" or "dead_lettered"."""
        where = f"{msg.topic()}[{msg.partition()}]@{msg.offset()}"
        try:
            env = parse_envelope(msg.value(), msg.headers())
        except InvalidMessage as exc:
            logger.warning("worker=%s event=invalid message=%s error=%s", self.name, where, exc)
            self._dead_letter(msg, None, exc, 0)            # 1. copy it to the dead-letter topic ...
            return self._commit(msg, "dead_lettered")       # 2. ... and only then remember the offset

        attempts, outcome = 0, "dead_lettered"
        while True:
            attempts += 1
            try:
                outcome = dispatch(self.db, env)
                break
            except PermanentError as exc:
                logger.warning("worker=%s event=permanent_error type=%s event_id=%s trace_id=%s error=%s",
                               self.name, env.event_type, env.event_id, env.trace_id, exc)
                self._dead_letter(msg, env, exc, attempts)
                outcome = "dead_lettered"
                break
            except Exception as exc:                          # temporary: MongoDB restarting, a network blip...
                if attempts >= MAX_ATTEMPTS:
                    logger.error("worker=%s event=gave_up type=%s event_id=%s trace_id=%s attempts=%s error=%s",
                                 self.name, env.event_type, env.event_id, env.trace_id, attempts, exc)
                    self._dead_letter(msg, env, exc, attempts)
                    outcome = "dead_lettered"
                    break
                pause = BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
                logger.warning("worker=%s event=retry type=%s event_id=%s trace_id=%s attempt=%s/%s in=%ss error=%s",
                               self.name, env.event_type, env.event_id, env.trace_id, attempts, MAX_ATTEMPTS, pause, exc)
                self.sleep(pause)
        if outcome != "dead_lettered":
            logger.info("worker=%s event=%s type=%s event_id=%s trace_id=%s message=%s",
                        self.name, outcome, env.event_type, env.event_id, env.trace_id, where)
        return self._commit(msg, outcome)                 # the write (or the dead-letter copy) is done: remember the offset

    def _commit(self, msg: Any, outcome: str) -> str:
        """Remember how far we have read. Called ONLY after the database write or the dead-letter copy succeeded."""
        self.consumer.commit(message=msg, asynchronous=False)
        return outcome

    def _dead_letter(self, msg: Any, env: Any, error: Exception, attempts: int) -> None:
        headers: List[Any] = [("original_topic", msg.topic().encode()), ("error_type", type(error).__name__.encode())]
        record = {
            "failed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "consumer_group": self.group_id, "attempts": attempts,
            "error_type": type(error).__name__, "error": str(error),
            "original_topic": msg.topic(), "original_partition": msg.partition(), "original_offset": msg.offset(),
            "original_key": _text(msg.key()), "original_value": _text(msg.value()),
            "event_id": env.event_id if env else None, "trace_id": env.trace_id if env else None,
        }
        if env:
            headers += [("event_id", env.event_id.encode()), ("trace_id", env.trace_id.encode())]
        try:
            self.producer.produce(DLQ_TOPIC, key=msg.key(), value=json.dumps(record).encode(), headers=headers)
            if self.producer.flush(10):
                raise PublishError("the dead-letter message was not delivered")
        except Exception as exc:
            raise WorkerFatal(f"could not write to {DLQ_TOPIC}: {exc}") from exc
        logger.error("worker=%s event=dead_lettered type=%s event_id=%s trace_id=%s attempts=%s message=%s[%s]@%s error=%s",
                     self.name, env.event_type if env else "?", record["event_id"], record["trace_id"], attempts,
                     msg.topic(), msg.partition(), msg.offset(), error)

    # ---------------------------------------------------------------- the loop
    def run(self) -> None:
        logger.info("worker=%s event=started group=%s", self.name, self.group_id)
        try:
            while not self.stopping:
                self.heartbeat()
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.warning("worker=%s event=kafka_error error=%s", self.name, msg.error())
                    continue
                self.process(msg)
        finally:
            self.consumer.close()
            logger.info("worker=%s event=stopped", self.name)


def beat() -> None:
    """Touch the heartbeat file: the Docker/Kubernetes health check looks at how recent it is."""
    with open(HEARTBEAT_FILE, "a"):
        os.utime(HEARTBEAT_FILE, None)


def run_worker(name: str, event_types: List[str]) -> None:
    """Entry point of a worker container: python -m services.<service>.worker"""
    from confluent_kafka import Consumer, Producer
    from .publisher import ensure_topics

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    group_id = f"p06-{name}-worker"
    ensure_topics(bootstrap)
    db = mongo.get_database()
    mongo.ensure_indexes_quietly()
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": group_id, "client.id": f"p06-{name}-worker",
                         "enable.auto.commit": False,          # we commit ourselves, after the database write
                         "auto.offset.reset": "earliest", "session.timeout.ms": 15000,
                         "max.poll.interval.ms": 300000})
    consumer.subscribe([topic_for(t) for t in event_types])
    producer = Producer({"bootstrap.servers": bootstrap, "client.id": f"p06-{name}-worker", "acks": "all",
                         "enable.idempotence": True})
    worker = Worker(name, group_id, consumer, producer, db, heartbeat=beat)

    def stop(*_args):
        worker.stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        worker.run()
    except WorkerFatal as exc:
        logger.critical("worker=%s event=fatal error=%s", name, exc)
        raise SystemExit(1)
