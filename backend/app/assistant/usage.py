"""
Token tracking (Lab 2, Part 6).

A TOKEN is the unit a language model reads and writes: roughly three quarters of an English word. The model has a CONTEXT
WINDOW, the most tokens it can hold at once (prompt + answer); here 8192 (CONTEXT_WINDOW in model_client.py). When a chat
grows, the prompt (system prompt + tool descriptions + the whole history) gets longer on every message, so we show the
student how full the window is, warn at 70 percent, and compact the history at 85 percent (see compaction.py).

After EVERY model call the agent loop calls Usage.add(reply) with the counts Ollama reported. The numbers are the model's
own, not our estimate, except in estimate_tokens() below, which is used only to compare history sizes when compacting.
"""
import math
from dataclasses import dataclass
from typing import Iterable, List

from .model_client import CONTEXT_WINDOW

WARN_AT_PERCENT = 70        # the chat window shows a warning above this
COMPACT_AT_PERCENT = 85     # the history is compacted automatically above this


@dataclass
class Usage:
    model_calls: int = 0
    prompt_tokens: int = 0            # all tokens read, summed over the calls counted here
    completion_tokens: int = 0        # all tokens written
    last_prompt_tokens: int = 0       # the most recent call: its prompt is what is "in the window" right now
    last_completion_tokens: int = 0
    estimated: bool = False           # True right after a compaction: the "last" numbers are an estimate until the next call

    def add(self, reply) -> None:
        """Count one model call."""
        self.estimated = False        # a real measurement replaces any estimate
        self.model_calls += 1
        self.prompt_tokens += reply.prompt_tokens
        self.completion_tokens += reply.completion_tokens
        self.last_prompt_tokens = reply.prompt_tokens
        self.last_completion_tokens = reply.completion_tokens

    @property
    def context_tokens(self) -> int:
        """How much of the window the conversation fills after the last call: what it read plus what it wrote."""
        return self.last_prompt_tokens + self.last_completion_tokens

    def exact_percent(self, window: int = CONTEXT_WINDOW) -> float:
        """The exact share of the window in use. The warning and compaction decisions use THIS, never the rounded number."""
        return 100.0 * self.context_tokens / window if window else 0.0

    def percent(self, window: int = CONTEXT_WINDOW) -> float:
        """The same, rounded to one decimal, for showing to the student."""
        return round(self.exact_percent(window), 1)

    def as_dict(self, window: int = CONTEXT_WINDOW) -> dict:
        """The shape sent to the website and stored in a trace."""
        percent, exact = self.percent(window), self.exact_percent(window)
        return {
            "model_calls": self.model_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "context_tokens": self.context_tokens,
            "context_window": window,
            "context_percent": percent,
            "context_estimated": self.estimated,
            "warn": exact > WARN_AT_PERCENT,
            "compact_recommended": exact >= COMPACT_AT_PERCENT,
        }


def estimate_tokens(text: str) -> int:
    """A rough count (one token per four characters) for when no model call is available, such as comparing the size of a
    history before and after compaction. English text averages about four characters per token; the model's own count is
    used everywhere else."""
    return math.ceil(len(text or "") / 4)


def estimate_messages_tokens(messages: Iterable[dict]) -> int:
    """Estimated tokens of a message list: the text, any tool calls, and a few tokens of overhead per message."""
    total = 0
    for m in messages:
        total += 4 + estimate_tokens(m.get("content") or "")
        for call in m.get("tool_calls") or []:
            total += estimate_tokens(str(call))
    return total
