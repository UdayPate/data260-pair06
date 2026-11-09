"""
The three Kafka failure demos (Lab 2, Part 2), run against the REAL stack from docker-compose.yml.

    python -m scripts.kafka_demos idempotent   # 1. the same event twice: one application, not two
    python -m scripts.kafka_demos crash        # 2. a worker killed after the database write and before the commit
    python -m scripts.kafka_demos poison       # 3a. messages that can never work go to p06.dlq, the next message still works
    python -m scripts.kafka_demos retries      # 3b. MongoDB unreachable: 3 attempts (1 s and 2 s pauses), then p06.dlq
    python -m scripts.kafka_demos all
    python -m scripts.kafka_demos all ..\\docs\\lab2\\kafka_demos_output.txt   # also saves a clean copy of the output in that file

Needs: the stack running (`docker compose up -d`), the seeded database, and the git-ignored root .env (the MongoDB user and
password are read from it; they are never printed). The script talks to Kafka at localhost:9068 and MongoDB at
localhost:9069, and uses `docker` to read worker logs, arm the crash hook, pause MongoDB and read the dead-letter topic.
Every step prints what it does and what it saw, so the output can be pasted into RUN_LOG.txt as it is.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[2]


def read_env_file() -> dict:
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# The app code reads these when it is imported, so set them before importing anything from app/.
_env = read_env_file()
os.environ["MONGO_URL"] = (f"mongodb://{quote_plus(_env.get('MONGO_USER', 'p06admin'))}:{quote_plus(_env['MONGO_PASSWORD'])}"
                           "@localhost:9069/?authSource=admin")
os.environ.setdefault("MONGO_TIMEOUT_MS", "3000")
sys.path.insert(0, str(ROOT / "backend"))

from confluent_kafka import Producer          # noqa: E402
from app import mongo                         # noqa: E402
from app.events import topics                 # noqa: E402
from app.events.envelope import new_envelope  # noqa: E402

BOOTSTRAP = "localhost:9068"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
CONTAINER = "p06-application-worker"
GROUP = "p06-application-worker"
CRASH_FLAG = "/tmp/p06-crash-before-commit"


# ------------------------------------------------------------------ small helpers
OUT_FILE = None          # set by main() when a file name is given: everything printed with say() is also written there


def say(text: str = "") -> None:
    print(text, flush=True)
    if OUT_FILE:
        OUT_FILE.write(str(text) + "\n")
        OUT_FILE.flush()


def title(text: str) -> None:
    say()
    say("=" * 100)
    say(text)
    say("=" * 100)


def run(*cmd: str, timeout: int = 60) -> str:
    done = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    return (done.stdout + done.stderr).strip()


def shell_say(*cmd: str, timeout: int = 60) -> str:
    say("$ " + " ".join(cmd))
    out = run(*cmd, timeout=timeout)
    say(out)
    return out


def worker_log_since(since: str, container: str = CONTAINER, only: tuple = ()) -> str:
    """Worker log lines since the given time. `only`: keep just the lines that contain one of these texts (for example the
    event_id of this demo), because `docker logs --since` works in whole seconds and may include the end of the previous demo."""
    lines = run("docker", "logs", "--since", since, container).splitlines()
    return "\n".join(line for line in lines if "worker=" in line and (not only or any(text in line for text in only)))


def now_marker() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def producer() -> Producer:
    return Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all", "enable.idempotence": True})


def send_raw(topic: str, key: str, value: bytes, headers=None) -> None:
    p = producer()
    errors = []
    p.produce(topic, key=key.encode(), value=value, headers=headers or None,
              on_delivery=lambda err, _msg: errors.append(err) if err else None)
    if p.flush(10) or errors:
        raise SystemExit(f"Kafka did not confirm the message: {errors[0] if errors else 'timed out'}")


def send_envelope(env, key: str, times: int = 1) -> None:
    """Send the SAME bytes `times` times (same event_id, same key, same headers)."""
    for _ in range(times):
        send_raw(topics.topic_for(env.event_type), key, env.to_json().encode(), env.headers())


def store_pdf(db, name: str):
    return mongo.bucket(db, "resumes").put(PDF, filename=name, content_type="application/pdf")


def fresh_pair(db):
    """A (student, job) pair that has no application yet and a student we can apply for."""
    taken = {(a["student_id"], a["job_id"]) for a in db.applications.find({}, {"student_id": 1, "job_id": 1})}
    for student in db.students.find({}, {"_id": 1}).sort("_id", -1):
        for job in db.jobs.find({}, {"_id": 1}).sort("_id", 1):
            if (student["_id"], job["_id"]) not in taken:
                return student["_id"], job["_id"]
    raise SystemExit("no free (student, job) pair; reseed the database")


def application_event(student_id: int, job_id: int, resume_id, trace_id: str):
    payload = {"student_id": student_id, "job_id": job_id, "resume_file_id": str(resume_id),
               "applied_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")}
    return new_envelope("application.created", payload, trace_id, "p06-demo")


def count_applications(db, student_id: int, job_id: int) -> int:
    return db.applications.count_documents({"student_id": student_id, "job_id": job_id})


def wait_until(check, seconds: float, what: str, every: float = 0.5):
    end = time.time() + seconds
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(every)
    say(f"  (gave up waiting for: {what})")
    return None


def group_lag() -> str:
    return run("docker", "exec", "p06-kafka", "/opt/kafka/bin/kafka-consumer-groups.sh", "--bootstrap-server", "p06-kafka:9092",
               "--describe", "--group", GROUP, timeout=30)


def partition_committed(topic: str, partition: int, offset: int) -> bool:
    """True when the consumer group shows LAG 0 on that partition and its CURRENT-OFFSET is the one after `offset`
    (CURRENT-OFFSET is the next offset to read, so a committed message at offset 4 shows 5)."""
    for line in group_lag().splitlines():
        cols = line.split()
        if len(cols) >= 6 and cols[1] == topic and cols[2] == str(partition):
            return cols[3] == str(offset + 1) and cols[5] == "0"
    return False


def dlq_end() -> int:
    """How many messages p06.dlq holds right now (its end offset). Taken before a demo, so the demo can show only its own records."""
    from confluent_kafka import Consumer, TopicPartition
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"p06-demo-reader-{uuid.uuid4().hex[:8]}"})
    try:
        return consumer.get_watermark_offsets(TopicPartition(topics.DLQ_TOPIC, 0), timeout=10)[1]
    finally:
        consumer.close()


def read_dlq(from_offset: int) -> list:
    """Every dead-letter record from the given offset on (p06.dlq has one partition), read by a short-lived consumer."""
    from confluent_kafka import Consumer, TopicPartition
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"p06-demo-reader-{uuid.uuid4().hex[:8]}",
                         "enable.auto.commit": False})
    records = []
    try:
        consumer.assign([TopicPartition(topics.DLQ_TOPIC, 0, from_offset)])
        quiet_since = time.time()
        while time.time() - quiet_since < 4:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            quiet_since = time.time()
            records.append(json.loads(msg.value()))
    finally:
        consumer.close()
    return records


def show_dlq(records: list) -> None:
    for r in records:
        say(f"  p06.dlq  error_type={r['error_type']} attempts={r['attempts']} event_id={r['event_id']} trace_id={r['trace_id']}")
        say(f"           error={r['error']}")
        say(f"           from {r['original_topic']}[{r['original_partition']}]@{r['original_offset']} key={r['original_key']}"
            f" group={r['consumer_group']}")
        say(f"           original_value={str(r['original_value'])[:110]!r}")


# ------------------------------------------------------------------ demo 1
def demo_idempotent(db) -> None:
    title("DEMO 1  The same event arrives twice (at-least-once delivery): the consumer is idempotent")
    student_id, job_id = fresh_pair(db)
    resume = store_pdf(db, "demo1.pdf")
    trace = "demo1-" + uuid.uuid4().hex[:8]
    env = application_event(student_id, job_id, resume, trace)
    say(f"student={student_id} job={job_id} event_id={env.event_id} trace_id={trace} key={student_id}:{job_id}")
    say(f"applications for this pair before: {count_applications(db, student_id, job_id)}")
    since = now_marker()
    send_envelope(env, f"{student_id}:{job_id}", times=2)
    say("published the identical message twice (same event_id, same key, same headers)")
    wait_until(lambda: worker_log_since(since).count(env.event_id) >= 2, 20, "two log lines for this event")
    say("worker log lines:")
    say(worker_log_since(since))
    say(f"applications for this pair after: {count_applications(db, student_id, job_id)}   (expected 1)")
    say(f"activity-log rows for this event_id: {db.activity_logs.count_documents({'_id': env.event_id + ':application_created'})}   (expected 1)")

    say()
    say("Second case: a DIFFERENT event (new event_id) for the same student and job, as after a double click.")
    resume2 = store_pdf(db, "demo1-second.pdf")
    env2 = application_event(student_id, job_id, resume2, trace)
    since = now_marker()
    send_envelope(env2, f"{student_id}:{job_id}")
    wait_until(lambda: env2.event_id in worker_log_since(since), 20, "the worker log line")
    say(worker_log_since(since, only=(env2.event_id,)))
    say(f"applications for this pair after: {count_applications(db, student_id, job_id)}   (expected still 1; unique index on student+job)")
    say(f"the second PDF was removed again: {not mongo.bucket(db, 'resumes').exists(resume2)}   (expected True)")


# ------------------------------------------------------------------ demo 2
def demo_crash(db) -> None:
    title("DEMO 2  A worker is killed after the database write and BEFORE the offset is committed")
    student_id, job_id = fresh_pair(db)
    resume = store_pdf(db, "demo2.pdf")
    trace = "demo2-" + uuid.uuid4().hex[:8]
    env = application_event(student_id, job_id, resume, trace)
    say(f"student={student_id} job={job_id} event_id={env.event_id} trace_id={trace}")
    started = run("docker", "inspect", "-f", "{{.State.StartedAt}} restarts={{.RestartCount}}", CONTAINER)
    say(f"worker container before: {started}")
    say(f"applications for this pair before: {count_applications(db, student_id, job_id)}")
    shell_say("docker", "exec", CONTAINER, "touch", CRASH_FLAG)
    say("(the crash hook is armed: the next message will kill the worker right after its database write)")
    since = now_marker()
    send_envelope(env, f"{student_id}:{job_id}")

    died = wait_until(lambda: run("docker", "inspect", "-f", "{{.State.Running}}", CONTAINER) == "false"
                      or run("docker", "inspect", "-f", "{{.RestartCount}}", CONTAINER) != started.split("restarts=")[1],
                      30, "the worker to die", every=0.2)
    say(f"worker died: {bool(died)}")
    say("database right after the kill:")
    say(f"  applications for this pair: {count_applications(db, student_id, job_id)}   (1 = the write happened, nothing was lost)")
    say("consumer group right after the kill (the partition that holds the message has NO committed offset, or a LAG of 1: the commit never happened):")
    say(group_lag())

    mine = (env.event_id, "event=started")           # only this demo's lines: the restart and the message with our event_id
    duplicate_line = f"event=duplicate type=application.created event_id={env.event_id}"

    def reprocessed_and_committed() -> bool:
        """The restarted worker logged `duplicate` for OUR event_id, and the group shows LAG 0 on that message's partition."""
        for line in worker_log_since(since, only=mine).splitlines():
            found = re.search(duplicate_line + r".*message=(p06\.[a-z_.]+)\[(\d+)\]@(\d+)", line)
            if found:
                return partition_committed(found.group(1), int(found.group(2)), int(found.group(3)))
        return False

    say("waiting up to 60 s for the restarted worker to read the message again and commit it ...")
    healthy = wait_until(reprocessed_and_committed, 60, "the duplicate line for our event_id AND lag 0 on its partition", every=2.0)
    say(f"worker container after: {run('docker', 'inspect', '-f', '{{.State.StartedAt}} restarts={{.RestartCount}}', CONTAINER)}")
    say("worker log since the kill (only the lines of this demo):")
    say(worker_log_since(since, only=mine))
    time.sleep(2)
    say(f"applications for this pair after the restart: {count_applications(db, student_id, job_id)}   (expected 1: reprocessed, not duplicated)")
    say("consumer group after the restart (the partition that holds the message must show LAG 0 now: committed after the second, no-op run):")
    say(group_lag())
    ok = bool(healthy) and count_applications(db, student_id, job_id) == 1
    say("result: PASS (reprocessed after the restart, committed, still one application)" if ok else
        "result: FAIL (no `duplicate` line for this event_id with LAG 0 within 60 s, or the application count is not 1)")


# ------------------------------------------------------------------ demo 3a
def demo_poison(db) -> None:
    title("DEMO 3a  Messages that can never succeed go to p06.dlq; the pipeline keeps working")
    dlq_before = dlq_end()
    since = now_marker()
    trace = "demo3-" + uuid.uuid4().hex[:8]
    say("1) not JSON at all")
    send_raw(topics.topic_for(topics.APPLICATION_CREATED), "poison:garbage", b"this is not json {{{")
    say("2) a valid envelope for student 999999, who does not exist")
    resume = store_pdf(db, "demo3.pdf")
    bad = application_event(999999, 1, resume, trace)
    send_envelope(bad, "999999:1")
    say("3) a header that disagrees with the body (trace_id)")
    good_shape = application_event(999999, 2, resume, trace)
    send_raw(topics.topic_for(topics.APPLICATION_CREATED), "999999:2", good_shape.to_json().encode(),
             [("event_id", good_shape.event_id.encode()), ("event_type", b"application.created"), ("trace_id", b"some-other-trace")])
    say("4) a good application right after the three bad ones")
    student_id, job_id = fresh_pair(db)
    ok_resume = store_pdf(db, "demo3-good.pdf")
    ok = application_event(student_id, job_id, ok_resume, trace)
    send_envelope(ok, f"{student_id}:{job_id}")
    # all four go to partition keys that may differ, so wait for all of them
    wait_until(lambda: count_applications(db, student_id, job_id) == 1 and worker_log_since(since).count("dead_lettered") >= 3,
               30, "the three dead letters and the good application")
    say("worker log lines:")
    say(worker_log_since(since))
    say(f"the good application was saved: {count_applications(db, student_id, job_id) == 1}   (expected True)")
    say("messages on p06.dlq written during this demo:")
    show_dlq(read_dlq(dlq_before))
    say("consumer group (LAG 0 = the bad messages did not block anything):")
    say(group_lag())
    say(f"no application was created for student 999999: {db.applications.count_documents({'student_id': 999999}) == 0}")


# ------------------------------------------------------------------ demo 3b
def demo_retries(db) -> None:
    title("DEMO 3b  A temporary failure (MongoDB unreachable) is retried 3 times, then dead-lettered; later messages work")
    student_id, job_id = fresh_pair(db)
    resume = store_pdf(db, "demo3b.pdf")
    env = application_event(student_id, job_id, resume, "demo3b-" + uuid.uuid4().hex[:8])
    dlq_before = dlq_end()
    since = now_marker()
    shell_say("docker", "pause", "p06-mongo")
    try:
        send_envelope(env, f"{student_id}:{job_id}")
        say(f"published event_id={env.event_id} while MongoDB is paused")
        wait_until(lambda: "event=gave_up" in worker_log_since(since), 120, "the worker to give up", every=1.0)
    finally:
        shell_say("docker", "unpause", "p06-mongo")
    time.sleep(3)
    say("worker log lines:")
    say(worker_log_since(since))
    say("p06.dlq:")
    show_dlq(read_dlq(dlq_before))
    say(f"applications for this pair (not saved, it is in the dead-letter topic): {count_applications(db, student_id, job_id)}")
    say("MongoDB is back; the next application is processed normally:")
    student2, job2 = fresh_pair(db)
    since = now_marker()
    ok = application_event(student2, job2, store_pdf(db, "demo3b-after.pdf"), "demo3b-after")
    send_envelope(ok, f"{student2}:{job2}")
    wait_until(lambda: count_applications(db, student2, job2) == 1, 30, "the new application")
    say(worker_log_since(since))
    say(f"saved: {count_applications(db, student2, job2) == 1}   (expected True)")


DEMOS = {"idempotent": demo_idempotent, "crash": demo_crash, "poison": demo_poison, "retries": demo_retries}


def main() -> None:
    global OUT_FILE
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if len(sys.argv) > 2:                      # python -m scripts.kafka_demos all docs\\lab2\\kafka_demos_output.txt
        OUT_FILE = open(sys.argv[2], "w", encoding="utf-8", newline="\n")     # a clean copy of the output, no PowerShell wrapping
    if which not in DEMOS and which != "all":
        raise SystemExit(__doc__)
    db = mongo.get_database()
    for name in (list(DEMOS) if which == "all" else [which]):
        DEMOS[name](db)
    say()


if __name__ == "__main__":
    main()
