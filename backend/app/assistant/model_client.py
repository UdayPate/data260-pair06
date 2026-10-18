"""
The ONE place in the application that talks to the language model.

    client = OllamaClient()
    reply = client.complete(messages, tools)
    reply.content     -> the text the model wrote ("" when it only asked for tools)
    reply.tool_calls  -> [ToolRequest(name="search_jobs", arguments={...}), ...]

Nothing else in the app may call Ollama directly. The agent loop only knows about the
ModelClient interface, so the tests can plug in a fake client that needs no model at all.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from ..config import SEED

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
# This laptop runs the model on the CPU, so one model call can take a minute or more.
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))


class ModelError(Exception):
    """The model could not be reached or sent back something we cannot read."""


@dataclass
class ToolRequest:
    """One tool the model asked us to run.

    `arguments` is normally a dict. If the model sent arguments we could not parse,
    `arguments` is {} and `raw_arguments` keeps what it actually sent, so the agent loop
    can report a "malformed arguments" error back to the model.
    """
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: Optional[str] = None


@dataclass
class ModelReply:
    content: str
    tool_calls: List[ToolRequest] = field(default_factory=list)


class ModelClient:
    """The interface every model client implements."""

    def complete(self, messages: List[dict], tools: List[dict]) -> ModelReply:
        raise NotImplementedError


# qwen3 can "think out loud" inside <think>...</think>; the student should never see that.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaClient(ModelClient):
    """Talks to a local Ollama server through its /api/chat endpoint (no API key needed)."""

    def __init__(self, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_URL,
                 timeout: float = OLLAMA_TIMEOUT_SECONDS):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, messages: List[dict], tools: List[dict]) -> ModelReply:
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "think": False,          # qwen3's thinking mode is far too slow on a CPU
            "options": {
                "temperature": 0,    # same question -> same answer, so runs can be compared
                "seed": SEED,
                "num_ctx": 8192,     # room for the system prompt, tool schemas and history
            },
        }
        try:
            response = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
            response.raise_for_status()
            message = response.json()["message"]
        except httpx.HTTPError as exc:
            raise ModelError(f"Could not reach the model at {self.base_url}: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise ModelError(f"The model sent back an unreadable response: {exc}") from exc

        content = _THINK_RE.sub("", message.get("content") or "").strip()
        calls = [_to_tool_request(c) for c in message.get("tool_calls") or []]
        return ModelReply(content=content, tool_calls=calls)


def _to_tool_request(call: dict) -> ToolRequest:
    """Ollama sends {"function": {"name": ..., "arguments": {...}}}. Arguments are usually
    a dict, but some models send a JSON string, or something that is not JSON at all."""
    function = call.get("function") or {}
    name = str(function.get("name") or "")
    args = function.get("arguments")
    if isinstance(args, dict):
        return ToolRequest(name=name, arguments=args)
    if args is None or args == "":
        return ToolRequest(name=name, arguments={})
    try:
        parsed = json.loads(args) if isinstance(args, str) else None
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return ToolRequest(name=name, arguments=parsed)
    return ToolRequest(name=name, arguments={}, raw_arguments=str(args))
