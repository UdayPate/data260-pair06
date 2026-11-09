# Kafka contract (Pair 06, Lab 2)

How the services and workers talk through Kafka: the topics, the message format, who produces and consumes what, and the
rules every producer and consumer must follow. This is the reference for the assistant work (Part 3 memory consolidation,
Part 6 tracing): if you add a producer or a consumer, follow section 5.

Kafka runs as one broker in KRaft mode (no ZooKeeper): container `p06-kafka`, address `p06-kafka:9092` inside Docker Compose
and Kubernetes, `localhost:9068` from this machine. Code: `backend/app/events/`.

## 1. Topics

Every topic name starts with the pair prefix `p06.` followed by the **event type**. They are created automatically (3 partitions,
replication factor 1; `p06.dlq` has 1) by the first service or worker that needs them (`ensure_topics`); automatic topic creation
by Kafka itself is switched off, so a misspelled topic name fails instead of silently creating a new topic.

| Topic | Event type | Produced by | Consumed by (group) | Message key | What the consumer does |
|---|---|---|---|---|---|
| `p06.application.created` | `application.created` | Application API, `POST /jobs/{id}/apply` | Application worker (`p06-application-worker`) | `<student_id>:<job_id>` | Writes the application (status Pending) and an activity-log entry. Idempotent. |
| `p06.application.updated` | `application.updated` | **nothing yet** (reserved: no API edits an application except its status) | Application worker | `<application_id>` | Replaces the application's resume file. |
| `p06.application.status_changed` | `application.status_changed` | Application API, `PATCH /applications/{id}/status` (after the status is saved) | Application worker | `<application_id>` | Writes a notification for the student. Idempotent. |
| `p06.event.registration_created` | `event.registration_created` | Event API, `POST /events/{id}/register` (after the registration is saved) | Event worker (`p06-event-worker`) | `<student_id>:<event_id>` | Writes a confirmation notification. Idempotent. |
| `p06.job.created` | `job.created` | Job API, `POST /jobs` (after the job is saved) | Job worker (`p06-job-worker`) | `<job_id>` | Writes a notification for every student whose saved preferences match the job. Idempotent. |
| `p06.dlq` | *(see section 4)* | any worker | nobody (a person reads it) | the original key | The dead-letter topic: messages that failed for good. |

The key decides the partition, so events with the same key are delivered **in order** to the same worker.
Which flows write the main data through Kafka: **only applications**. `POST /jobs/{id}/apply` answers **202 Accepted** and the
worker saves the application a moment later. The other three flows save their data in the API first and use Kafka for what
follows (notifications), so their endpoints keep answering as before.

## 2. The message (the "envelope")

The message **value** is this JSON object; the Kafka **headers** repeat three of its fields.

```json
{
  "event_id": "0b6f3d0e-6c0c-4a53-9f0a-2c7c1e4a8d11",
  "event_type": "application.created",
  "timestamp": "2026-11-08T18:44:50.123456Z",
  "trace_id": "b5d4a0f1c2e34d6f9a1b3c5d7e9f0a12",
  "producer": "p06-application",
  "schema_version": 1,
  "payload": { "student_id": 12, "job_id": 7, "resume_file_id": "672e5c1b8d2f4a0012a3b4c5", "applied_at": "2026-11-08T18:44:49.987654" }
}
```
Headers: `event_id`, `event_type`, `trace_id` (text). Message key: see the table.

| Field | Rule |
|---|---|
| `event_id` | A UUID, new for every event. **The key to idempotency**: a consumer must be able to receive the same `event_id` twice and change nothing the second time. |
| `event_type` | One of the five types above. Anything else is rejected as invalid. |
| `timestamp` | When the event was created, ISO 8601, UTC, ends in `Z`. |
| `trace_id` | 1 to 64 characters from `A-Z a-z 0-9 . _ -`. It is the same value in the **Kafka header** `trace_id` and in the **message body**; a message whose header and body disagree is rejected. It comes from the request that caused the event (header `X-Trace-ID`, else the `X-Request-ID` the gateway adds to every request, else a new one). Anything that follows from an event (a log line, a notification, a follow-up event) must carry the same `trace_id`. |
| `producer` | The service that sent it (`p06-application`, `p06-event`, `p06-job`). |
| `schema_version` | `1`. Raise it when a payload changes in a way old consumers cannot read. |
| `payload` | The event's data (section 3). Always a JSON object. |

### The payloads

```
application.created            { student_id: int, job_id: int, resume_file_id: str (GridFS id, 24 hex characters), applied_at: ISO time }
application.updated            { application_id: int, changes: { resume_file_id: str } }
application.status_changed     { application_id: int, student_id: int, job_id: int, job_title: str, company_name: str,
                                 old_status: str, new_status: str }
event.registration_created     { registration_id: int, student_id: int, event_id: int, event_name: str, event_datetime: ISO time, company_id: int }
job.created                    { job_id: int, company_id: int, company_name: str, title: str, category: str, city: str, is_remote: bool }
```
The `resume_file_id` points at a PDF already stored in MongoDB (GridFS bucket `resumes`): the API stores the file *before* it
publishes, so a message never carries the file itself.

## 3. Delivery guarantees, and what makes them true

Kafka delivers **at least once**. The code makes the *effect* happen once:

| Rule | How |
|---|---|
| The producer does not lose or duplicate a message | `acks=all` and an idempotent producer; the API waits (up to 8 s) until the broker has confirmed the message. If it cannot, `POST /jobs/{id}/apply` answers **503** and removes the stored PDF. For the other three flows the API has already saved its data, so a failure is logged and the request still succeeds. |
| A worker commits an offset **only after** its database write | The offset is Kafka's bookmark. A worker killed after the write but before the commit gets the message again after the restart: it was **not lost**, it is **reprocessed**, and the handler turns the second run into a no-op. |
| Handlers are idempotent | `application.created`: the application's natural key is (student, job) and has a unique index; a second event for the same pair (the same event again, or a double click) creates nothing, and a duplicate's extra PDF is deleted. Notifications and activity-log entries written by a worker have an `_id` made from the `event_id`, so the same event cannot write them twice. |
| Retries are bounded | A temporary failure (MongoDB restarting) is tried again: 3 attempts in all, pausing 1 s and then 2 s. |
| A bad message does not block the others | A message that can never succeed (invalid JSON, unknown type, a student that does not exist) is copied to `p06.dlq` **without retrying**; one that still fails after the 3rd attempt is copied there too. Only then is its offset committed, so the worker moves on. |
| A message is never silently dropped | If the copy to `p06.dlq` itself fails, the worker stops without committing (Docker restarts it) and the message is read again. |

## 4. The dead-letter topic `p06.dlq`

Message value (JSON), key = the original key, headers `original_topic`, `error_type` and (when known) `event_id`, `trace_id`:

```json
{ "failed_at": "2026-11-08T18:50:01.000000Z", "consumer_group": "p06-application-worker", "attempts": 1,
  "error_type": "PermanentError", "error": "student 9999 does not exist",
  "original_topic": "p06.application.created", "original_partition": 2, "original_offset": 14,
  "original_key": "9999:7", "original_value": "<the original message, as text>",
  "event_id": "<uuid or null>", "trace_id": "<id or null>" }
```
`attempts` is 0 for a message that is not even a valid envelope. `original_value` is the exact text, so it can be fixed and
published again. Read it with:
`docker exec p06-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server p06-kafka:9092 --topic p06.dlq --from-beginning --timeout-ms 5000`

## 5. Adding a producer or a consumer (for the assistant work)

1. Add the event type to `backend/app/events/topics.py` (`EVENT_TYPES`); the topic `p06.<type>` and its creation follow.
2. **Producer**: `get_publisher().publish("<type>", key="<entity key>", payload={...}, trace_id=trace_id)` (the API gets
   `trace_id` with `Depends(get_trace_id)`). Use `publish_quietly(...)` when the action is already saved and Kafka is
   only for what follows; call `publish(...)` and handle `PublishError` when the event *is* the action.
3. **Consumer**: write a handler `def handle_x(db, envelope) -> "processed" | "duplicate"` in `backend/app/events/handlers.py`
   and register it in `HANDLERS`. It **must be idempotent** (use a natural unique key, or an `_id` built from `envelope.event_id`).
   Raise `PermanentError` for a message that can never succeed; let any other exception escape for a retry.
4. Make a worker entry point like `backend/services/application/worker.py` (`run_worker("<name>", [event types])`; group id
   `p06-<name>-worker`) and add a container to `docker-compose.yml` with `command: ["python", "-m", "services.<service>.worker"]`
   and the worker health check. A memory-consolidation consumer must be a consumer like this, never run inside a user request.
5. Put the `trace_id` in your log lines (`trace_id=%s`) and copy it into anything the handler writes or publishes.

Without `KAFKA_BOOTSTRAP` (one app on a laptop, and all the unit tests) the publisher is **inline**: it calls the same handler
at once, in the same process, so the website works without Kafka. In Docker Compose and Kubernetes `KAFKA_BOOTSTRAP` is set.

## 6. Known limits (honest list)

* **Producing is not atomic with the database write.** For status changes, registrations and new jobs the API saves first and then
  publishes; if Kafka is down at that moment the data is saved but the notification is lost (a log line says so). The clean fix is
  an "outbox" collection with a relay, which this lab does not build.
* One broker, replication factor 1: the data survives a container restart (it is on a volume), not the loss of the disk.
* While a worker retries a failing message it does not read the messages behind it in that partition (at most about 3 s of pause).
* Notifications are stored in the `notifications` collection (see `MONGO_SCHEMA.md`); there is no endpoint or page that shows them.
* `application.updated` has a consumer but no producer yet.
