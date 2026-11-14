"""
The assistant's guardrails (Lab 2, Part 6). One place for the safety rules that are not part of the tools themselves.

The eight guardrails and where each one lives:

  1  Tool allowlist            agent.classify_call() rejects any name that is not in tools.TOOL_FUNCTIONS
  2  Schema validation         tools.check_arguments() rejects unknown, missing and wrongly typed arguments
  3  Authorization             authorize() below (signed in, owns the conversation, may use the tool)
  4  Read/write control        confirm.confirm_action() + the pending-action flow in agent.py
  5  Prompt-injection defense  tools.mark_untrusted() wraps database text; looks_like_injection() flags it for the log
  6  Privacy and secrets       redact_secrets() and hide_other_students() below
  7  Bounded execution         MAX_ITERATIONS, the request deadline (REQUEST_TIMEOUT_SECONDS) and one retry of a
                               failed read-only tool (is_recoverable_error()) in agent.py
  8  Reliable answers          ungrounded_ids() below: an id in the answer must appear in a tool result

This module has no database or model code of its own, so the live assistant and the test harness run exactly the
same functions. Every function is small on purpose: the human has to be able to explain each one.
"""
import os
import re
from typing import Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Guardrail 7: how long one student message may take in total.
# The model client has its own timeout for ONE model call; this is the limit for the whole message
# (all model calls and tool calls together). It is checked before every new step.
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT_SECONDS = float(os.getenv("ASSISTANT_REQUEST_TIMEOUT_SECONDS", "900"))
TIMEOUT_REPLY = ("This request took longer than the time limit, so I stopped. "
                 "Please try a simpler or more specific question.")


def is_recoverable_error(result: str) -> bool:
    """A read-only tool that CRASHED (a database hiccup) returns 'Error: <name> failed (<ExceptionType>)...'.
    That kind of error may go away on a second try. Bad arguments and unknown ids will not, so they never match."""
    return result.startswith("Error:") and " failed (" in result


# ---------------------------------------------------------------------------
# Guardrail 3: authorization.
# The student always comes from the login token (the router needs a student token), never from the model.
# So the three things left to check are: someone is signed in, the conversation is theirs, the tool is allowed.
# ---------------------------------------------------------------------------
def authorize(student, conversation_student_id: Optional[int], tool_name: Optional[str],
              allowed_tools: Iterable[str]) -> Optional[str]:
    """Return None when the action may go ahead, otherwise a short reason."""
    if student is None or getattr(student, "id", None) is None:
        return "not signed in as a student"
    if conversation_student_id != student.id:
        return "this conversation belongs to another student"
    if tool_name is not None and tool_name not in set(allowed_tools):
        return f"the student role may not use '{tool_name}'"
    return None


# ---------------------------------------------------------------------------
# Guardrail 6: secrets and other people's private data.
# ---------------------------------------------------------------------------
# Each pair is (what to look for, what to put instead). Order matters: the specific shapes (JWT, key prefixes)
# run before the generic "word = value" rule.
_SECRET_PATTERNS = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"), "[REDACTED_TOKEN]"),   # a JWT
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{8,}"), "[REDACTED_KEY]"),                                  # sk-... API keys
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_KEY]"),                                           # an AWS access key id
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_ -]?key|access[_ -]?key|token)\b((?:\s+is)?\s*[:=]\s*)(\S+)"),
     r"\1\2[REDACTED]"),
]


def redact_secrets(text: str) -> Tuple[str, int]:
    """Replace passwords, tokens and keys with a marker. Returns (clean text, how many replacements)."""
    count = 0
    for pattern, replacement in _SECRET_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def hide_other_students(text: str, own_student_id: int, find_student_by_email) -> Tuple[str, int]:
    """Remove the email address of any OTHER student from an answer.
    find_student_by_email(email) returns the student record or None (the caller supplies the database lookup).
    A company's contact email is not a student, so it is left alone."""
    count = 0

    def hide(match):
        nonlocal count
        student = find_student_by_email(match.group(0))
        if student is not None and student.id != own_student_id:
            count += 1
            return "[email hidden: another student's private data]"
        return match.group(0)

    return _EMAIL.sub(hide, text), count


# ---------------------------------------------------------------------------
# Guardrail 5 (logging side): tell the log when database text looks like it is giving orders.
# The real defense is the wrapper that labels the text as data. This check only makes attacks visible.
# ---------------------------------------------------------------------------
_INJECTION_HINTS = re.compile(
    r"ignore (all |any |your |the )?(previous |prior |above )?(instructions|rules)|"
    r"disregard (your|the) (rules|instructions)|you are now|system prompt|"
    r"(call|run|use) (the )?save_job_or_event|save (this )?job (for the student )?without|reveal (your|the) (rules|prompt)",
    re.IGNORECASE)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_HINTS.search(text))


# ---------------------------------------------------------------------------
# Guardrail 8: an answer may only name ids that a tool really returned.
# ---------------------------------------------------------------------------
_CLAIMED_ID = re.compile(r"\b(?:id|job|event|posting)\s*#?:?\s*(\d+)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+\b")
UNGROUNDED_REPLY = ("I could not match some details in my answer to the database, so I am not showing them. "
                    "Please ask again, or ask me to search for it.")


def ungrounded_ids(reply: str, tool_texts: Iterable[str]) -> List[str]:
    """Ids the answer mentions that appear in NO tool result of this conversation (so the model made them up)."""
    seen: Set[str] = set()
    for text in tool_texts:
        seen.update(_NUMBER.findall(text))
    return sorted({m for m in _CLAIMED_ID.findall(reply) if m not in seen})
