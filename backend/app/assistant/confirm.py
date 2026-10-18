"""
The confirmation gate (Part C). Every state-changing tool must pass through here first;
read-only tools never do.

    confirm_action("save_job_or_event", {"item_type": "job", "item_id": 12})   -> True / False

How the student is asked:
  * In a terminal run, `ask` is Python's input(), so the question is typed into the console.
  * In the website chat, the question is asked in one chat turn and the student's NEXT
    message is the answer. The agent loop passes that message in as `ask`
    (see agent.py, "pending action"). Same function, same rule, two ways of asking.

Only an explicit yes approves the action. Anything else (no, blank, a new question, an
error while asking) counts as a refusal, so the safe outcome is always "nothing changed".
"""
import json
from typing import Callable, Optional

YES_ANSWERS = {"y", "yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "yes please", "please do", "do it"}


def describe_action(tool_name: str, arguments: dict) -> str:
    """The question shown to the student."""
    return f"The assistant wants to run {tool_name} with {json.dumps(arguments, sort_keys=True)}. Allow it? (yes/no)"


def is_yes(answer: Optional[str]) -> bool:
    text = (answer or "").strip().lower().rstrip(".!")
    return text in YES_ANSWERS


def confirm_action(tool_name: str, arguments: dict, auto_approve: bool = False,
                   ask: Optional[Callable[[str], str]] = None) -> bool:
    """Return True only if this action may go ahead.

    auto_approve  True skips the question (used only by automated tests, never by the website).
    ask           a function that shows the question and returns the student's answer;
                  defaults to input() in a terminal.
    """
    if auto_approve:
        return True
    ask = ask or input
    try:
        answer = ask(describe_action(tool_name, arguments))
    except Exception:  # e.g. no console available: treat as "not confirmed"
        return False
    return is_yes(answer)
