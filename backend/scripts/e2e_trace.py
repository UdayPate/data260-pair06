"""
One real end-to-end trace through the running Docker Compose stack (Lab 2, Part 6; report section 13).

    docker compose up -d                          (the stack must be running; the real model, Ollama, must be reachable)
    python -m scripts.e2e_trace                   (from backend/; takes a few minutes on a CPU)

What it does, in order (everything it sees is printed and written to docs/lab2/e2e_trace_output.txt):
  1. signs in as the demo student through the gateway (port 9060),
  2. asks the assistant a real question (the real model answers; tools run; one answer),
  3. asks for "/trace": the stage times (model, database, tool) of that request,
  4. sends "/memory learn": the API publishes a Kafka message and answers at once; the memory worker (a Kafka consumer)
     reads it and runs the slow part with the model, in the background,
  5. waits until the worker has finished, then collects the evidence of the SAME trace id from every place it must appear:
       the API response, the Kafka message (header AND body), the assistant log, the worker log, and the MongoDB `traces`
       and `memory_runs` documents.
Nothing is invented: the script only prints what the system returned. The MongoDB password comes from the git-ignored .env
and is never printed.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "lab2" / "e2e_trace_output.txt"
GATEWAY = os.getenv("GATEWAY", "http://localhost:9060")
QUESTION = os.getenv("E2E_QUESTION", "Find a data internship")
LINES = []


def say(text: str = ""):
    print(text, flush=True)
    LINES.append(text)


def sh(command: list, timeout=120) -> str:
    """Run a command and return its output (used for docker exec / docker logs)."""
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return (done.stdout + done.stderr).strip()


def read_env() -> dict:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def lines_with(text: str, needle: str, limit=12) -> str:
    found = [line for line in text.splitlines() if needle in line]
    return "\n".join(found[:limit]) if found else f"(no line with {needle} found)"


def main() -> int:
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    say(f"End-to-end trace, run on {started}. Real Ollama model, real Kafka, real MongoDB (Docker Compose, project p06-handshake).")
    client = httpx.Client(base_url=GATEWAY, timeout=httpx.Timeout(900.0, connect=10.0))

    say("\n== 1. sign in (demo student)")
    login = client.post("/auth/login", json={"email": "demo.student@sjsu.edu", "password": "Password123!", "role": "student"})
    say(f"POST /auth/login -> HTTP {login.status_code}")
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}

    say(f'\n== 2. ask the assistant: "{QUESTION}"  (the real model answers; this takes a while on a CPU)')
    t0 = time.time()
    chat = client.post("/assistant/chat", json={"message": QUESTION, "conversation_id": None}, headers=headers)
    body = chat.json()
    trace_chat, conversation_id = body.get("trace_id"), body.get("conversation_id")
    say(f"POST /assistant/chat -> HTTP {chat.status_code} after {time.time() - t0:.1f} s")
    say(f"  trace_id        : {trace_chat}")
    say(f"  conversation_id : {conversation_id}")
    say(f"  tools called    : {[c['name'] for c in body.get('tool_calls', [])]}")
    say(f"  usage           : {body.get('usage')}")
    say(f"  reply (first 400 characters): {str(body.get('reply'))[:400]!r}")

    say("\n== 3. /trace: where the time of that request went")
    trace_reply = client.post("/assistant/chat", json={"message": "/trace", "conversation_id": conversation_id}, headers=headers).json()
    say(trace_reply.get("reply", ""))

    say('\n== 4. "/memory learn": the API queues a Kafka message and answers at once')
    t0 = time.time()
    learn = client.post("/assistant/chat", json={"message": "/memory learn", "conversation_id": conversation_id}, headers=headers)
    learn_body = learn.json()
    trace_learn = learn_body.get("trace_id")
    say(f"POST /assistant/chat '/memory learn' -> HTTP {learn.status_code} after {time.time() - t0:.2f} s (the model is NOT waited for)")
    say(f"  trace_id : {trace_learn}")
    say(f"  reply    : {learn_body.get('reply')}")

    say("\n== 5. wait for the memory worker (a Kafka consumer) to finish its work with this trace id")
    deadline, worker_log = time.time() + 1500, ""
    while time.time() < deadline:
        worker_log = sh(["docker", "logs", "p06-memory-worker"])
        if trace_learn in worker_log and "processed" in lines_with(worker_log, trace_learn, 50).lower():
            break
        time.sleep(15)
    say(f"worker finished after about {time.time() - t0:.0f} s" if trace_learn in worker_log else "WORKER DID NOT FINISH IN TIME")

    say(f"\n== 6. the same trace id ({trace_learn}) in every place")
    say("-- (a) the Kafka message on p06.memory.session_ended: headers and body (kafka-console-consumer)")
    kafka = sh(["docker", "exec", "p06-kafka", "/opt/kafka/bin/kafka-console-consumer.sh", "--bootstrap-server", "p06-kafka:9092",
                "--topic", "p06.memory.session_ended", "--from-beginning", "--timeout-ms", "8000",
                "--property", "print.headers=true", "--property", "print.key=true"], timeout=60)
    say(lines_with(kafka, trace_learn, 3))
    say("-- (b) the assistant service log (the API side)")
    say(lines_with(sh(["docker", "logs", "p06-assistant"]), trace_learn))
    say("-- (c) the memory worker log (the consumer side)")
    say(lines_with(worker_log, trace_learn, 20))
    say("-- (d) the gateway access log (the request that carried it in)")
    say(lines_with(sh(["docker", "logs", "p06-gateway"]), "/assistant/chat", 4) + "\n   (the gateway log has no trace id of its own; it shows the requests)")

    say("-- (e) MongoDB: the documents saved with the trace id (the `traces` and `memory_runs` collections)")
    from pymongo import MongoClient
    env = read_env()
    mongo = MongoClient(f"mongodb://{env['MONGO_USER']}:{env['MONGO_PASSWORD']}@localhost:9069/?authSource=admin")
    db = mongo["p06_handshake"]
    for collection in ("traces", "memory_runs"):
        for trace in (trace_chat, trace_learn):
            for doc in db[collection].find({"trace_id": trace}, {"_id": 0}):
                say(f"   {collection} where trace_id={trace}:")
                say("   " + json.dumps(doc, default=str, ensure_ascii=False)[:900])
    say(f"\nDone. Chat trace {trace_chat}; Kafka trace {trace_learn}.")
    OUTPUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
