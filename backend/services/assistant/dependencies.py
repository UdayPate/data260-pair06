"""
"Can the AI Assistant reach what it needs?" (Lab 2, Part 1.2). GET /health/dependencies on the assistant service checks:

  mongodb        a ping to the database the assistant's tools read
  student, company, job, application, event   each platform service's /health, by its service name and port
                 (http://p06-job:9064/health ...: the same names work in Docker Compose and in Kubernetes)
  kafka          a TCP connection to the broker, when KAFKA_BOOTSTRAP is set (for example p06-kafka:9092)
  ollama         the model server (OLLAMA_URL), which is only needed to answer chat messages

The assistant's own tools read MongoDB directly (the same service functions the website uses), so MongoDB and the
platform services are required ("ok" is true only when all of them answer); Kafka and Ollama are reported separately.
Nothing secret is returned: only names and ok / unreachable.
"""
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

import httpx
from pymongo.errors import PyMongoError

from app import mongo
from app.config import SERVICE_PORTS

TIMEOUT_SECONDS = 3.0


def platform_urls() -> Dict[str, str]:
    """{"student": "http://p06-student:9062/health", ...} for every service except the assistant itself."""
    return {key: f"http://p06-{key}:{port}/health" for key, port in SERVICE_PORTS.items() if key != "assistant"}


def check_http(url: str) -> str:
    try:
        return "ok" if httpx.get(url, timeout=TIMEOUT_SECONDS).status_code == 200 else "unhealthy"
    except httpx.HTTPError:
        return "unreachable"


def check_tcp(host_and_port: str) -> str:
    host, _, port = host_and_port.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=TIMEOUT_SECONDS):
            return "ok"
    except (OSError, ValueError):
        return "unreachable"


def check_mongodb() -> str:
    try:
        mongo.get_database().command("ping")
        return "ok"
    except PyMongoError:
        return "unreachable"


def check_ollama() -> str:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/tags"
    return check_http(url)


def report() -> dict:
    """Run every check at the same time (each can take up to TIMEOUT_SECONDS) and summarise."""
    urls = platform_urls()
    kafka = os.getenv("KAFKA_BOOTSTRAP", "").strip()
    with ThreadPoolExecutor(max_workers=8) as pool:
        mongodb = pool.submit(check_mongodb)
        services = {key: pool.submit(check_http, url) for key, url in urls.items()}
        kafka_result = pool.submit(check_tcp, kafka) if kafka else None
        ollama = pool.submit(check_ollama)
        required = {"mongodb": mongodb.result(), **{key: f.result() for key, f in services.items()}}
        optional = {"kafka": kafka_result.result() if kafka_result else "not configured", "ollama": ollama.result()}
    return {"ok": all(value == "ok" for value in required.values()), "required": required, "optional": optional}
