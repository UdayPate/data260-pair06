"""
Lab 2, Part 2: Kafka. No broker is needed here:
  * the message format, the handlers and the publishers are tested directly;
  * the worker loop is tested with a fake consumer and a fake producer that record what happens, in order;
  * the API tests use the "inline" publisher (no KAFKA_BOOTSTRAP): the same handler a worker would run is called at once.
The real broker is tested by hand in Docker Compose (see RUN_LOG.txt).
"""
import json
import uuid
from datetime import date, datetime, timedelta

import pytest
from bson import ObjectId

from app import mongo
from app.events import handlers, publisher as pub, topics
from app.events.consumer import MAX_ATTEMPTS, Worker, WorkerFatal
from app.events.envelope import Envelope, clean_trace_id, new_envelope, parse_envelope
from app.events.errors import InvalidMessage, PermanentError, PublishError
from tests.factories import PDF, make_company, make_event, make_job, make_preferences, make_student, store_resume

STUDENT = {"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123", "college": "SJSU"}
COMPANY = {"name": "Acme Corp", "email": "hr@acme.com", "password": "Secret123", "location": "San Jose"}


# =============================================================== the message format
def test_topics_have_the_pair_prefix_and_a_dead_letter_topic():
    assert topics.topic_for("application.created") == "p06.application.created"
    assert set(topics.TOPICS) == {"p06.application.created", "p06.application.updated", "p06.application.status_changed",
                                  "p06.event.registration_created", "p06.job.created", "p06.dlq"}
    assert topics.DLQ_TOPIC == "p06.dlq" and all(name.startswith("p06.") for name in topics.TOPICS)


def test_a_new_envelope_has_every_required_field_in_body_and_headers():
    env = new_envelope("job.created", {"job_id": 5}, trace_id="trace-abc", producer="p06-job")
    body = json.loads(env.to_json())
    assert set(body) == {"event_id", "event_type", "timestamp", "trace_id", "payload", "producer", "schema_version"}
    assert str(uuid.UUID(body["event_id"])) == body["event_id"] and body["timestamp"].endswith("Z")
    assert body["trace_id"] == "trace-abc" and body["payload"] == {"job_id": 5} and body["producer"] == "p06-job"
    assert dict(env.headers()) == {"event_id": env.event_id.encode(), "event_type": b"job.created", "trace_id": b"trace-abc"}


def test_two_envelopes_never_share_an_event_id():
    assert new_envelope("job.created", {}).event_id != new_envelope("job.created", {}).event_id


@pytest.mark.parametrize("given, kept", [("abc-123_X.y", True), (None, False), ("", False), ("has space", False),
                                         ("x" * 65, False), ("<script>", False)])
def test_trace_ids_are_kept_when_sane_and_replaced_otherwise(given, kept):
    result = clean_trace_id(given)
    assert (result == given) is kept and 1 <= len(result) <= 64


def test_an_envelope_survives_a_round_trip():
    env = new_envelope("application.created", {"student_id": 1, "job_id": 2}, "t-1", "p06-application")
    again = parse_envelope(env.to_json().encode(), env.headers())
    assert again == env


def _good():
    return json.loads(new_envelope("job.created", {"job_id": 1}).to_json())


@pytest.mark.parametrize("make, reason", [
    (lambda: b"this is not json {", "not valid JSON"),
    (lambda: b"[1, 2, 3]", "not a JSON object"),
    (lambda: json.dumps({k: v for k, v in _good().items() if k != "trace_id"}).encode(), "missing field"),
    (lambda: json.dumps({**_good(), "event_id": "12345"}).encode(), "not a UUID"),
    (lambda: json.dumps({**_good(), "event_type": "job.deleted"}).encode(), "unknown event_type"),
    (lambda: json.dumps({**_good(), "trace_id": ""}).encode(), "trace_id is empty"),
    (lambda: json.dumps({**_good(), "payload": [1]}).encode(), "payload is not an object"),
    (lambda: json.dumps({**_good(), "timestamp": "yesterday"}).encode(), "timestamp"),
    (lambda: b"\xff\xfe\x00", "not valid JSON"),
], ids=["not-json", "not-object", "missing-trace", "bad-uuid", "unknown-type", "empty-trace", "payload-list", "bad-time", "binary"])
def test_invalid_messages_are_refused_as_permanent_errors(make, reason):
    with pytest.raises(InvalidMessage, match=reason) as info:
        parse_envelope(make())
    assert isinstance(info.value, PermanentError)            # so a worker never retries it


def test_a_header_that_disagrees_with_the_body_is_refused():
    env = new_envelope("job.created", {})
    with pytest.raises(InvalidMessage, match="header trace_id"):
        parse_envelope(env.to_json(), [("trace_id", b"somebody-elses-trace")])
    parse_envelope(env.to_json(), [("unrelated", b"x"), ("trace_id", env.trace_id.encode())])     # fine


# =============================================================== helpers for the handler tests
def application_event(student_id, job_id, resume_id, event_id=None, **payload):
    env = new_envelope("application.created", {"student_id": student_id, "job_id": job_id, "resume_file_id": str(resume_id),
                                               "applied_at": datetime(2026, 11, 8, 10, 30).isoformat(), **payload}, "trace-app")
    if event_id:
        env.event_id = event_id
    return env


@pytest.fixture()
def people(db):
    company = make_company(db)
    student = make_student(db, name="Ada")
    job = make_job(db, company.id, title="Data Analyst", deadline=date.today() + timedelta(days=20))
    return company, student, job


# =============================================================== application.created
def test_application_created_writes_the_application_and_the_activity_log(db, people):
    _, student, job = people
    resume = store_resume(db, PDF, "cv.pdf")
    env = application_event(student.id, job.id, resume)
    assert handlers.dispatch(db, env) == handlers.PROCESSED
    app = db.applications.find_one({})
    assert (app["student_id"], app["job_id"], app["status"]) == (student.id, job.id, "Pending")
    assert app["resume_file_id"] == resume and app["applied_at"] == datetime(2026, 11, 8, 10, 30)
    assert app["source_event_id"] == env.event_id and app["trace_id"] == "trace-app"
    log = db.activity_logs.find_one({"action": "application_created"})
    assert log["actor_id"] == student.id and log["ref_id"] == app["_id"] and log["_id"] == f"{env.event_id}:application_created"


def test_the_same_event_twice_leaves_exactly_one_application(db, people):
    _, student, job = people
    env = application_event(student.id, job.id, store_resume(db))
    assert handlers.dispatch(db, env) == handlers.PROCESSED
    assert handlers.dispatch(db, env) == handlers.DUPLICATE          # redelivery: nothing changes
    assert handlers.dispatch(db, env) == handlers.DUPLICATE
    assert db.applications.count_documents({}) == 1 and db.activity_logs.count_documents({"action": "application_created"}) == 1
    assert db.counters.find_one({"_id": "applications"})["seq"] == 1       # no id was used up by the duplicates
    assert db["resumes.files"].count_documents({}) == 1                    # a redelivery does not delete the resume


def test_a_double_click_makes_one_application_and_removes_the_extra_pdf(db, people):
    _, student, job = people
    first, second = store_resume(db, PDF, "first.pdf"), store_resume(db, PDF, "second.pdf")
    assert handlers.dispatch(db, application_event(student.id, job.id, first)) == handlers.PROCESSED
    assert handlers.dispatch(db, application_event(student.id, job.id, second)) == handlers.DUPLICATE   # a DIFFERENT event
    assert db.applications.count_documents({}) == 1
    assert db.applications.find_one({})["resume_file_id"] == first
    assert mongo.bucket(db, "resumes").exists(first) and not mongo.bucket(db, "resumes").exists(second)


@pytest.mark.parametrize("bad, why", [
    ({"student_id": 9999}, "student 9999 does not exist"),
    ({"job_id": 9999}, "job 9999 does not exist"),
    ({"resume_file_id": str(ObjectId())}, "resume file is not in the database"),
    ({"resume_file_id": "not-an-object-id"}, "not a file id"),
    ({"student_id": "1"}, "payload.student_id"),
    ({"job_id": None}, "payload.job_id"),
    ({"applied_at": "yesterday"}, "not an ISO time"),
], ids=["no-student", "no-job", "no-resume", "bad-resume-id", "text-student-id", "null-job-id", "bad-time"])
def test_application_created_with_bad_data_is_a_permanent_error(db, people, bad, why):
    _, student, job = people
    good = {"student_id": student.id, "job_id": job.id, "resume_file_id": str(store_resume(db)),
            "applied_at": datetime.now().isoformat()}
    env = new_envelope("application.created", {**good, **bad})
    with pytest.raises(PermanentError, match=why):
        handlers.dispatch(db, env)
    assert db.applications.count_documents({}) == 0


# =============================================================== the other handlers
def test_application_updated_changes_the_resume_and_refuses_other_fields(db, people):
    _, student, job = people
    handlers.dispatch(db, application_event(student.id, job.id, store_resume(db)))
    application_id = db.applications.find_one({})["_id"]
    newer = store_resume(db, PDF, "newer.pdf")
    env = new_envelope("application.updated", {"application_id": application_id, "changes": {"resume_file_id": str(newer)}})
    assert handlers.dispatch(db, env) == handlers.PROCESSED and handlers.dispatch(db, env) == handlers.PROCESSED
    assert db.applications.find_one({"_id": application_id})["resume_file_id"] == newer
    for bad in ({"status": "Declined"}, {"resume_file_id": "x"}):
        with pytest.raises(PermanentError):
            handlers.dispatch(db, new_envelope("application.updated", {"application_id": application_id, "changes": bad}))
    with pytest.raises(PermanentError, match="does not exist"):
        handlers.dispatch(db, new_envelope("application.updated", {"application_id": 99, "changes": {}}))


def test_status_changed_creates_one_notification_even_if_delivered_twice(db, people):
    _, student, _ = people
    env = new_envelope("application.status_changed", {
        "application_id": 7, "student_id": student.id, "job_id": 1, "job_title": "Data Analyst",
        "company_name": "Acme", "old_status": "Pending", "new_status": "Reviewed"}, "trace-1")
    assert handlers.dispatch(db, env) == handlers.PROCESSED and handlers.dispatch(db, env) == handlers.DUPLICATE
    note = db.notifications.find_one({})
    assert db.notifications.count_documents({}) == 1 and note["_id"] == f"{env.event_id}:student:{student.id}"
    assert note["user_id"] == student.id and note["kind"] == "application_status" and note["read"] is False
    assert "from Pending to Reviewed" in note["body"] and note["trace_id"] == "trace-1" and note["ref_id"] == 7


def test_registration_created_confirms_with_one_notification(db, people):
    _, student, _ = people
    env = new_envelope("event.registration_created", {"registration_id": 1, "student_id": student.id, "event_id": 3,
                                                      "event_name": "Career Fair", "event_datetime": "2026-11-20T10:00:00"})
    assert handlers.dispatch(db, env) == handlers.PROCESSED and handlers.dispatch(db, env) == handlers.DUPLICATE
    assert db.notifications.count_documents({"kind": "event_registration", "user_id": student.id}) == 1


def test_job_created_notifies_only_students_whose_preferences_fit(db):
    company = make_company(db)
    fits_city = make_student(db); fits_all = make_student(db); wrong_category = make_student(db)
    wrong_city = make_student(db); remote_only_ok = make_student(db); no_prefs = make_student(db)
    make_preferences(db, fits_city.id, preferred_categories=["internship"], preferred_cities=["San Jose"])
    make_preferences(db, fits_all.id)                                                     # empty lists: anything goes
    make_preferences(db, wrong_category.id, preferred_categories=["full_time"])
    make_preferences(db, wrong_city.id, preferred_cities=["Mountain View"], open_to_remote=False)
    make_preferences(db, remote_only_ok.id, preferred_cities=["Mountain View"], open_to_remote=True)
    env = new_envelope("job.created", {"job_id": 5, "company_id": company.id, "company_name": "Acme", "title": "Data Intern",
                                       "category": "internship", "city": "San Jose", "is_remote": False})
    handlers.dispatch(db, env)
    notified = {n["user_id"] for n in db.notifications.find({"kind": "new_job_match"})}
    assert notified == {fits_city.id, fits_all.id}                  # not the wrong category, the wrong city, or no preferences
    handlers.dispatch(db, env)                                      # delivered again: nothing is added
    assert db.notifications.count_documents({}) == 2
    remote = new_envelope("job.created", {"job_id": 6, "company_id": company.id, "company_name": "Acme", "title": "Remote Intern",
                                          "category": "internship", "city": "Sunnyvale", "is_remote": True})
    handlers.dispatch(db, remote)
    assert remote_only_ok.id in {n["user_id"] for n in db.notifications.find({"ref_id": 6})}   # remote work is OK for them
    assert wrong_city.id not in {n["user_id"] for n in db.notifications.find({"ref_id": 6})}


def test_an_event_type_without_a_handler_is_a_permanent_error(db, monkeypatch):
    monkeypatch.setitem(handlers.HANDLERS, "job.created", None)
    monkeypatch.delitem(handlers.HANDLERS, "job.created")
    with pytest.raises(PermanentError, match="no handler"):
        handlers.dispatch(db, new_envelope("job.created", {}))


# =============================================================== the worker loop, with a fake broker
class FakeMessage:
    def __init__(self, value, topic="p06.application.created", partition=0, offset=0, key=b"1:1", headers=None):
        self._value, self._topic, self._partition, self._offset, self._key = value, topic, partition, offset, key
        self._headers = headers or []

    def value(self): return self._value
    def topic(self): return self._topic
    def partition(self): return self._partition
    def offset(self): return self._offset
    def key(self): return self._key
    def headers(self): return self._headers
    def error(self): return None


def message_for(env, offset=0):
    return FakeMessage(env.to_json().encode(), topics.topic_for(env.event_type), 0, offset, b"k", env.headers())


class FakeConsumer:
    def __init__(self, journal, messages=(), commit_error=None):
        self.journal, self.messages, self.commit_error, self.closed = journal, list(messages), commit_error, False

    def poll(self, _timeout):
        return self.messages.pop(0) if self.messages else None

    def commit(self, message=None, asynchronous=True):
        if self.commit_error:
            raise self.commit_error
        self.journal.append(("commit", message.offset()))

    def close(self):
        self.closed = True


class FakeProducer:
    def __init__(self, journal, remaining=0):
        self.journal, self.remaining, self.sent = journal, remaining, []

    def produce(self, topic, key=None, value=None, headers=None, **_):
        self.sent.append({"topic": topic, "key": key, "value": json.loads(value), "headers": dict(headers or [])})
        self.journal.append(("produce", topic))

    def flush(self, _timeout):
        return self.remaining


@pytest.fixture()
def rig(db, monkeypatch):
    """A worker wired to fakes. `journal` records, in order, what the worker did: handler, produce (dead letter), commit."""
    journal, pauses = [], []
    real_dispatch = handlers.dispatch

    def recording_dispatch(database, env):
        result = real_dispatch(database, env)
        journal.append(("handler", result))
        return result
    monkeypatch.setattr("app.events.consumer.dispatch", recording_dispatch)
    producer = FakeProducer(journal)
    consumer = FakeConsumer(journal)
    worker = Worker("application", "p06-application-worker", consumer, producer, db, sleep=pauses.append)
    return worker, journal, pauses, producer, consumer


def test_the_offset_is_committed_only_after_the_database_write(rig, db, people):
    worker, journal, _, _, _ = rig
    _, student, job = people
    outcome = worker.process(message_for(application_event(student.id, job.id, store_resume(db)), offset=41))
    assert outcome == "processed" and db.applications.count_documents({}) == 1
    assert journal == [("handler", "processed"), ("commit", 41)]          # write first, commit second


def test_a_worker_killed_before_the_commit_loses_nothing_and_does_not_duplicate(db, people, monkeypatch):
    """The write happened, then the worker died before committing. After the restart Kafka delivers the message again:
    it is reprocessed (not lost) and the handler makes it a no-op (no duplicate row)."""
    _, student, job = people
    msg = message_for(application_event(student.id, job.id, store_resume(db)), offset=7)
    dying = Worker("application", "g", FakeConsumer([], commit_error=RuntimeError("killed")), FakeProducer([]), db, sleep=lambda _s: None)
    with pytest.raises(RuntimeError, match="killed"):
        dying.process(msg)
    assert db.applications.count_documents({}) == 1                       # the write had already happened
    journal = []
    restarted = Worker("application", "g", FakeConsumer(journal), FakeProducer(journal), db, sleep=lambda _s: None)
    assert restarted.process(msg) == "duplicate"                          # delivered again ...
    assert db.applications.count_documents({}) == 1                       # ... but still exactly one
    assert journal == [("commit", 7)]


def test_the_same_message_twice_is_processed_once_and_both_are_committed(rig, db, people):
    worker, journal, _, _, _ = rig
    _, student, job = people
    msg = message_for(application_event(student.id, job.id, store_resume(db)))
    assert [worker.process(msg), worker.process(msg)] == ["processed", "duplicate"]
    assert db.applications.count_documents({}) == 1
    assert [e for e in journal if e[0] == "commit"] == [("commit", 0), ("commit", 0)]


def test_a_temporary_failure_is_retried_with_a_pause_and_then_succeeds(rig, db, people, monkeypatch):
    worker, journal, pauses, producer, _ = rig
    _, student, job = people
    calls = {"n": 0}
    real = handlers.dispatch

    def flaky(database, env):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("MongoDB is restarting")
        return real(database, env)
    monkeypatch.setattr("app.events.consumer.dispatch", flaky)
    assert worker.process(message_for(application_event(student.id, job.id, store_resume(db)))) == "processed"
    assert calls["n"] == 3 and pauses == [1.0, 2.0]                       # two retries, with the backoff pauses
    assert producer.sent == [] and db.applications.count_documents({}) == 1


def test_a_message_that_keeps_failing_goes_to_the_dead_letter_topic_after_the_last_attempt(rig, db, people, monkeypatch):
    worker, journal, pauses, producer, _ = rig
    _, student, job = people
    monkeypatch.setattr("app.events.consumer.dispatch", lambda d, e: (_ for _ in ()).throw(ConnectionError("still down")))
    env = application_event(student.id, job.id, store_resume(db))
    assert worker.process(message_for(env, offset=5)) == "dead_lettered"
    assert pauses == [1.0, 2.0] and MAX_ATTEMPTS == 3                      # bounded: 3 attempts, then stop
    assert journal == [("produce", "p06.dlq"), ("commit", 5)]              # dead letter first, then the commit
    record = producer.sent[0]["value"]
    assert record["attempts"] == 3 and record["error_type"] == "ConnectionError" and "still down" in record["error"]
    assert (record["original_topic"], record["original_partition"], record["original_offset"]) == ("p06.application.created", 0, 5)
    assert record["event_id"] == env.event_id and record["trace_id"] == env.trace_id and record["consumer_group"] == "p06-application-worker"
    assert json.loads(record["original_value"])["event_id"] == env.event_id         # the original message can be replayed
    assert producer.sent[0]["headers"]["event_id"] == env.event_id.encode()
    assert db.applications.count_documents({}) == 0


def test_a_permanent_error_is_not_retried(rig, db, people):
    worker, journal, pauses, producer, _ = rig
    _, student, job = people
    env = application_event(9999, job.id, store_resume(db))               # a student that does not exist
    assert worker.process(message_for(env, offset=2)) == "dead_lettered"
    assert pauses == [] and producer.sent[0]["value"]["attempts"] == 1 and "does not exist" in producer.sent[0]["value"]["error"]
    assert journal == [("produce", "p06.dlq"), ("commit", 2)]


def test_a_poison_message_is_isolated_and_the_next_message_is_processed(rig, db, people):
    worker, journal, pauses, producer, consumer = rig
    _, student, job = people
    poison = FakeMessage(b"this is not json {", offset=10)
    good = message_for(application_event(student.id, job.id, store_resume(db)), offset=11)
    consumer.messages = [poison, good]
    beats = []
    worker.heartbeat = lambda: beats.append(1) or (setattr(worker, "stopping", True) if len(beats) > 3 else None)
    worker.run()
    assert [e for e in journal if e[0] != "handler"] == [("produce", "p06.dlq"), ("commit", 10), ("commit", 11)]
    assert producer.sent[0]["value"]["error_type"] == "InvalidMessage" and producer.sent[0]["value"]["event_id"] is None
    assert producer.sent[0]["value"]["original_value"] == "this is not json {"
    assert db.applications.count_documents({}) == 1                       # the pipeline went on
    assert pauses == [] and consumer.closed is True


def test_if_the_dead_letter_write_fails_the_worker_stops_without_committing(db):
    journal = []
    worker = Worker("application", "g", FakeConsumer(journal), FakeProducer(journal, remaining=1), db, sleep=lambda _s: None)
    with pytest.raises(WorkerFatal, match="p06.dlq"):
        worker.process(FakeMessage(b"garbage", offset=3))
    assert ("commit", 3) not in journal                                    # never dropped silently


def test_the_loop_skips_errors_beats_and_closes_the_consumer(db):
    class ErrorMessage(FakeMessage):
        def error(self): return "broker transport failure"
    consumer = FakeConsumer([], [ErrorMessage(b"x")])
    worker = Worker("event", "g", consumer, FakeProducer([]), db)
    beats = []
    worker.heartbeat = lambda: (beats.append(1), setattr(worker, "stopping", len(beats) >= 3))
    worker.run()
    assert len(beats) == 3 and consumer.closed and consumer.messages == []


# =============================================================== the publishers
class FakeKafkaProducer:
    def __init__(self, remaining=0, delivery_error=None):
        self.remaining, self.delivery_error, self.sent = remaining, delivery_error, []

    def produce(self, topic, key=None, value=None, headers=None, on_delivery=None):
        self.sent.append({"topic": topic, "key": key, "value": json.loads(value), "headers": dict(headers)})
        if on_delivery:
            on_delivery(self.delivery_error, None)

    def flush(self, _timeout):
        return self.remaining


def kafka_publisher(producer):
    publisher = pub.KafkaPublisher("p06-kafka:9092", "p06-application")
    publisher._producer, publisher._topics_ready = producer, True
    return publisher


def test_the_kafka_publisher_sends_the_envelope_with_key_and_headers():
    producer = FakeKafkaProducer()
    env = kafka_publisher(producer).publish("application.created", "12:7", {"student_id": 12}, "trace-xyz")
    sent = producer.sent[0]
    assert sent["topic"] == "p06.application.created" and sent["key"] == b"12:7"
    assert sent["value"]["event_id"] == env.event_id and sent["value"]["trace_id"] == "trace-xyz"
    assert sent["value"]["producer"] == "p06-application" and sent["value"]["payload"] == {"student_id": 12}
    assert sent["headers"] == {"event_id": env.event_id.encode(), "event_type": b"application.created", "trace_id": b"trace-xyz"}


@pytest.mark.parametrize("producer", [FakeKafkaProducer(remaining=1), FakeKafkaProducer(delivery_error="Broker: not available")],
                         ids=["timed-out", "delivery-error"])
def test_the_kafka_publisher_fails_loudly_when_the_broker_does_not_confirm(producer):
    with pytest.raises(PublishError):
        kafka_publisher(producer).publish("job.created", "1", {})


def test_publish_quietly_swallows_the_error_but_returns_nothing():
    assert pub.publish_quietly(kafka_publisher(FakeKafkaProducer(remaining=1)), "job.created", "1", {}) is None
    assert pub.publish_quietly(kafka_publisher(FakeKafkaProducer()), "job.created", "1", {}).event_type == "job.created"


def test_the_publisher_is_inline_without_kafka_and_kafka_when_configured(monkeypatch):
    pub.use_publisher(None)
    monkeypatch.delenv("KAFKA_BOOTSTRAP", raising=False)
    assert pub.get_publisher().mode == "inline"
    pub.use_publisher(None)
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "p06-kafka:9092")
    assert pub.get_publisher().mode == "kafka"                           # building it does not connect
    pub.use_publisher(None)


def test_the_inline_publisher_runs_the_handler_and_reports_its_failure(db, people):
    _, student, _ = people
    env = pub.InlinePublisher().publish("event.registration_created", "k", {
        "registration_id": 1, "student_id": student.id, "event_id": 2, "event_name": "Fair", "event_datetime": "2026-11-20T10:00:00"})
    assert db.notifications.count_documents({"source_event_id": env.event_id}) == 1
    with pytest.raises(PublishError, match="inline handler"):
        pub.InlinePublisher().publish("application.created", "k", {"student_id": 1})


# =============================================================== the API publishes events
class Recording(pub.InlinePublisher):
    """The inline publisher that also remembers every event (and can be told to fail)."""
    def __init__(self, fail=False):
        self.events, self.fail = [], fail

    def publish(self, event_type, key, payload, trace_id=None):
        if self.fail:
            raise PublishError("Kafka is down")
        env = super().publish(event_type, key, payload, trace_id)
        self.events.append((event_type, key, env))
        return env


@pytest.fixture()
def recorder():
    recorder = Recording()
    pub.use_publisher(recorder)
    yield recorder
    pub.use_publisher(None)


def headers_for(client, role="student"):
    body = (STUDENT, "/auth/student/signup") if role == "student" else (COMPANY, "/auth/company/signup")
    r = client.post(body[1], json=body[0])
    return {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()["user_id"]


def post_job_api(client, headers, **over):
    body = {"title": "Data Analyst", "description": "Analyze data and build dashboards.", "category": "internship",
            "city": "San Jose", "salary_min": 20, "salary_max": 30, "pay_period": "hourly",
            "deadline": (date.today() + timedelta(days=20)).isoformat(), "skills": ["Python"], **over}
    r = client.post("/jobs", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def apply_api(client, job_id, headers, extra=None):
    return client.post(f"/jobs/{job_id}/apply", headers={**headers, **(extra or {})},
                       files={"resume": ("cv.pdf", PDF, "application/pdf")})


def test_applying_puts_an_application_created_event_on_the_topic_with_the_callers_trace_id(client, db, recorder):
    company, _ = headers_for(client, "company")
    student, student_id = headers_for(client)
    job_id = post_job_api(client, company)
    r = apply_api(client, job_id, student, {"X-Request-ID": "req-123-abc"})
    assert r.status_code == 202
    created = [e for e in recorder.events if e[0] == "application.created"]
    assert len(created) == 1
    _, key, env = created[0]
    assert key == f"{student_id}:{job_id}" and env.trace_id == "req-123-abc" and r.json()["trace_id"] == "req-123-abc"
    assert r.json()["event_id"] == env.event_id
    assert env.payload["student_id"] == student_id and env.payload["job_id"] == job_id
    assert ObjectId(env.payload["resume_file_id"]) and datetime.fromisoformat(env.payload["applied_at"])
    assert db.applications.find_one({})["trace_id"] == "req-123-abc"       # the trace reached the saved application


def test_an_explicit_trace_header_wins_and_a_bad_one_is_replaced(client, recorder):
    company, _ = headers_for(client, "company")
    student, _ = headers_for(client)
    job_id = post_job_api(client, company)
    r = apply_api(client, job_id, student, {"X-Trace-ID": "my-trace-1", "X-Request-ID": "other"})
    assert r.json()["trace_id"] == "my-trace-1"
    other_job = post_job_api(client, company, title="Second Job")
    r2 = apply_api(client, other_job, student, {"X-Trace-ID": "not allowed!!"})
    assert r2.json()["trace_id"] != "not allowed!!" and len(r2.json()["trace_id"]) == 32


def test_if_the_event_cannot_be_queued_the_apply_fails_cleanly(client, db):
    company, _ = headers_for(client, "company")
    student, _ = headers_for(client)
    job_id = post_job_api(client, company)
    pub.use_publisher(Recording(fail=True))
    try:
        r = apply_api(client, job_id, student)
    finally:
        pub.use_publisher(None)
    assert r.status_code == 503 and "could not be queued" in r.json()["detail"]
    assert db["resumes.files"].count_documents({}) == 0 and db.applications.count_documents({}) == 0   # nothing left behind
    assert apply_api(client, job_id, student).status_code == 202            # and a retry works


def test_changing_a_status_publishes_an_event_and_the_student_gets_a_notification(client, db, recorder):
    company, _ = headers_for(client, "company")
    student, student_id = headers_for(client)
    job_id = post_job_api(client, company)
    apply_api(client, job_id, student)
    application_id = db.applications.find_one({})["_id"]
    r = client.patch(f"/applications/{application_id}/status", headers={**company, "X-Request-ID": "trace-status"},
                     json={"status": "Reviewed"})
    assert r.status_code == 200 and r.json()["status"] == "Reviewed"       # the answer is still immediate
    event_type, key, env = [e for e in recorder.events if e[0] == "application.status_changed"][0]
    assert key == str(application_id) and env.trace_id == "trace-status"
    assert env.payload == {"application_id": application_id, "student_id": student_id, "job_id": job_id,
                           "job_title": "Data Analyst", "company_name": "Acme Corp",
                           "old_status": "Pending", "new_status": "Reviewed"}
    note = db.notifications.find_one({"kind": "application_status"})
    assert note["user_id"] == student_id and "Pending to Reviewed" in note["body"]


def test_setting_the_same_status_again_publishes_nothing(client, db, recorder):
    company, _ = headers_for(client, "company")
    student, _ = headers_for(client)
    job_id = post_job_api(client, company)
    apply_api(client, job_id, student)
    application_id = db.applications.find_one({})["_id"]
    assert client.patch(f"/applications/{application_id}/status", headers=company, json={"status": "Pending"}).status_code == 200
    assert not [e for e in recorder.events if e[0] == "application.status_changed"]


def test_a_kafka_problem_does_not_fail_a_status_change_or_a_job_post_or_a_registration(client, db):
    company, company_id = headers_for(client, "company")
    student, _ = headers_for(client)
    job_id = post_job_api(client, company)
    apply_api(client, job_id, student)
    application_id = db.applications.find_one({})["_id"]
    event = make_event(db, company_id, event_datetime=datetime.now() + timedelta(days=5), eligible_majors=["All"])
    pub.use_publisher(Recording(fail=True))
    try:
        assert client.patch(f"/applications/{application_id}/status", headers=company, json={"status": "Declined"}).status_code == 200
        assert post_job_api(client, company, title="Another Job") > job_id
        assert client.post(f"/events/{event.id}/register", headers=student).status_code == 201
    finally:
        pub.use_publisher(None)
    assert db.applications.find_one({})["status"] == "Declined" and db.notifications.count_documents({}) == 0


def test_registering_publishes_an_event_and_confirms_with_a_notification(client, db, recorder):
    _, company_id = headers_for(client, "company")
    student, student_id = headers_for(client)
    event = make_event(db, company_id, name="Career Fair", event_datetime=datetime.now() + timedelta(days=9), eligible_majors=["All"])
    assert client.post(f"/events/{event.id}/register", headers={**student, "X-Request-ID": "trace-reg"}).status_code == 201
    event_type, key, env = [e for e in recorder.events if e[0] == "event.registration_created"][0]
    assert key == f"{student_id}:{event.id}" and env.trace_id == "trace-reg"
    assert env.payload["event_name"] == "Career Fair" and env.payload["student_id"] == student_id
    assert db.notifications.count_documents({"kind": "event_registration", "user_id": student_id}) == 1


def test_posting_a_job_publishes_an_event_and_notifies_matching_students(client, db, recorder):
    company, company_id = headers_for(client, "company")
    student, student_id = headers_for(client)
    other = make_student(db, name="Not Interested")
    make_preferences(db, student_id, preferred_categories=["internship"], preferred_cities=["San Jose"])
    make_preferences(db, other.id, preferred_categories=["full_time"])
    job_id = post_job_api(client, company)
    event_type, key, env = [e for e in recorder.events if e[0] == "job.created"][0]
    assert key == str(job_id) and env.payload["job_id"] == job_id and env.payload["company_name"] == "Acme Corp"
    assert env.payload["category"] == "internship" and env.payload["city"] == "San Jose" and env.payload["is_remote"] is False
    assert {n["user_id"] for n in db.notifications.find({"kind": "new_job_match"})} == {student_id}


def test_the_notifications_collection_has_its_index(db):
    assert "user_role_1_user_id_1_created_at_-1" in db.notifications.index_information()


# =============================================================== application.updated: the new producer (PUT /applications/{id}/resume)
def an_application(db, people, resume_name="first.pdf"):
    _, student, job = people
    first = store_resume(db, PDF, resume_name)
    handlers.dispatch(db, application_event(student.id, job.id, first))
    return db.applications.find_one({}), first


def update_event(application, new_resume, **extra):
    return new_envelope("application.updated", {"application_id": application["_id"], "student_id": application["student_id"],
                                                "changes": {"resume_file_id": str(new_resume)}, **extra})


def test_replacing_the_resume_points_the_application_at_the_new_pdf_and_deletes_the_old_one(db, people):
    application, first = an_application(db, people)
    newer = store_resume(db, PDF + b"newer", "newer.pdf")
    env = update_event(application, newer)
    assert handlers.dispatch(db, env) == handlers.PROCESSED
    assert db.applications.find_one({"_id": application["_id"]})["resume_file_id"] == newer
    assert not mongo.bucket(db, "resumes").exists(first) and mongo.bucket(db, "resumes").exists(newer)
    assert handlers.dispatch(db, env) == handlers.PROCESSED                      # delivered twice: nothing changes
    assert db.applications.find_one({"_id": application["_id"]})["resume_file_id"] == newer
    assert db.activity_logs.count_documents({"action": "application_updated"}) == 1     # logged once


def test_a_resume_that_other_applications_share_is_not_deleted(db, people):
    company, student, job = people
    shared = store_resume(db, PDF, "seed_resume.pdf")                              # like the seeded placeholder
    other_student = make_student(db)
    handlers.dispatch(db, application_event(student.id, job.id, shared))
    handlers.dispatch(db, application_event(other_student.id, job.id, shared))
    mine = db.applications.find_one({"student_id": student.id})
    newer = store_resume(db, PDF + b"mine", "mine.pdf")
    handlers.dispatch(db, update_event(mine, newer))
    assert mongo.bucket(db, "resumes").exists(shared)                              # the other student still needs it
    assert db.applications.find_one({"student_id": other_student.id})["resume_file_id"] == shared


@pytest.mark.parametrize("make, why", [
    (lambda app, new: new_envelope("application.updated", {"application_id": app["_id"], "changes": {"resume_file_id": str(ObjectId())}}),
     "new resume file is not in the database"),
    (lambda app, new: update_event(app, new, student_id=999), "does not belong to student 999"),
    (lambda app, new: new_envelope("application.updated", {"application_id": app["_id"], "changes": {"status": "Declined"}}),
     "may only contain resume_file_id"),
    (lambda app, new: new_envelope("application.updated", {"application_id": 4242, "changes": {}}), "does not exist"),
], ids=["new-file-missing", "wrong-student", "other-field", "no-application"])
def test_a_bad_application_updated_event_is_a_permanent_error_and_changes_nothing(db, people, make, why):
    application, first = an_application(db, people)
    with pytest.raises(PermanentError, match=why):
        handlers.dispatch(db, make(application, store_resume(db, PDF + b"x", "x.pdf")))
    assert db.applications.find_one({"_id": application["_id"]})["resume_file_id"] == first


def test_putting_a_new_resume_through_the_api_publishes_application_updated(client, db, recorder):
    company, _ = headers_for(client, "company")
    student, student_id = headers_for(client)
    job_id = post_job_api(client, company)
    apply_api(client, job_id, student)
    application = db.applications.find_one({})
    old_file = application["resume_file_id"]
    new_pdf = PDF + b"% the second version\n"
    r = client.put(f"/applications/{application['_id']}/resume", headers={**student, "X-Request-ID": "trace-put"},
                   files={"resume": ("v2.pdf", new_pdf, "application/pdf")})
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True and body["application_id"] == application["_id"] and body["trace_id"] == "trace-put"
    event_type, key, env = [e for e in recorder.events if e[0] == "application.updated"][0]
    assert key == str(application["_id"]) and env.event_id == body["event_id"] and env.trace_id == "trace-put"
    assert env.payload["application_id"] == application["_id"] and env.payload["student_id"] == student_id
    assert client.get(f"/applications/{application['_id']}/resume", headers=student).content == new_pdf   # the worker (inline) did it
    assert not mongo.bucket(db, "resumes").exists(old_file)
    assert db["resumes.files"].count_documents({}) == 1


def test_only_the_applicant_can_replace_a_resume_and_only_while_pending(client, db, recorder):
    company, _ = headers_for(client, "company")
    student, _ = headers_for(client)
    stranger = make_student(db)                                                    # a second student (no login needed here)
    job_id = post_job_api(client, company)
    apply_api(client, job_id, student)
    application_id = db.applications.find_one({})["_id"]
    url = f"/applications/{application_id}/resume"
    pdf = {"resume": ("v2.pdf", PDF, "application/pdf")}
    assert client.put(url, files=pdf).status_code == 401
    assert client.put(url, headers=company, files=pdf).status_code == 403                    # companies cannot
    other = client.post("/auth/student/signup", json={**STUDENT, "email": "other@example.com", "name": "Other"}).json()["access_token"]
    assert client.put(url, headers={"Authorization": f"Bearer {other}"}, files=pdf).status_code == 404   # someone else's: not found
    assert client.put("/applications/99999/resume", headers=student, files=pdf).status_code == 404
    client.patch(url.replace("/resume", "/status"), headers=company, json={"status": "Reviewed"})
    late = client.put(url, headers=student, files=pdf)
    assert late.status_code == 409 and "Pending" in late.json()["detail"]
    assert not [e for e in recorder.events if e[0] == "application.updated"]               # nothing was published


def test_a_bad_or_unqueueable_new_resume_changes_nothing(client, db):
    company, _ = headers_for(client, "company")
    student, _ = headers_for(client)
    job_id = post_job_api(client, company)
    apply_api(client, job_id, student)
    application = db.applications.find_one({})
    url = f"/applications/{application['_id']}/resume"
    assert client.put(url, headers=student, files={"resume": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 415
    assert db["resumes.files"].count_documents({}) == 1                                     # still only the original
    pub.use_publisher(Recording(fail=True))
    try:
        r = client.put(url, headers=student, files={"resume": ("v2.pdf", PDF, "application/pdf")})
    finally:
        pub.use_publisher(None)
    assert r.status_code == 503 and "could not be queued" in r.json()["detail"]
    assert db["resumes.files"].count_documents({}) == 1                                     # the new file was removed again
    assert db.applications.find_one({"_id": application["_id"]})["resume_file_id"] == application["resume_file_id"]


# =============================================================== the demo hook: a worker killed after the write, before the commit
def test_the_demo_hook_kills_the_worker_after_the_write_and_before_the_commit_only_when_armed(db, people, tmp_path, monkeypatch):
    from app.events import consumer
    _, student, job = people
    flag = tmp_path / "crash-flag"
    monkeypatch.setattr(consumer, "CRASH_FLAG", str(flag))
    exits = []

    def fake_exit(code):
        exits.append(code)
        raise SystemExit(code)
    monkeypatch.setattr(consumer.os, "_exit", fake_exit)
    msg = message_for(application_event(student.id, job.id, store_resume(db)), offset=9)
    journal = []
    worker = Worker("application", "g", FakeConsumer(journal), FakeProducer(journal), db, sleep=lambda _s: None)

    other = message_for(application_event(make_student(db).id, job.id, store_resume(db)), offset=8)
    assert worker.process(other) == "processed" and exits == []                  # not armed: nothing happens, offset committed
    assert journal == [("commit", 8)]

    flag.write_text("armed")
    with pytest.raises(SystemExit):
        worker.process(msg)
    assert exits == [137] and not flag.exists()                                   # killed once, and the flag is gone
    assert db.applications.count_documents({"student_id": student.id}) == 1       # the write had happened ...
    assert ("commit", 9) not in journal                                           # ... the offset had not been committed
    assert worker.process(msg) == "duplicate" and journal[-1] == ("commit", 9)    # after the "restart": reprocessed, no duplicate
    assert db.applications.count_documents({"student_id": student.id}) == 1
