"""
The agent loop, the five tools and the confirmation gate, tested with a SCRIPTED fake model
(no Ollama needed). Run from backend/:   python -m pytest tests/test_agent.py -q
"""
from datetime import date, datetime, timedelta

import pytest

from app.assistant.agent import Conversation, run_assistant
from app.assistant.confirm import confirm_action
from app.assistant.model_client import ModelClient, ModelError, ModelReply, ToolRequest, _to_tool_request
from app.assistant.tools import TOOL_SCHEMAS, ToolContext, execute_tool
from app.models import (Company, Event, EventEligibleMajor, Job, JobCategory, JobSkill, PayPeriod,
                        SavedItem, Student, StudentPreference)

TODAY = date(2026, 10, 15)


class ScriptedClient(ModelClient):
    """Returns the prepared replies one by one and remembers what it was sent."""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def complete(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0)


def call(name, **arguments):
    return ModelReply("", [ToolRequest(name, arguments)])


def say(text):
    return ModelReply(text)


@pytest.fixture()
def world(db):
    company = Company(name="Acme Data", email="a@acme.test", password_hash="x", city="San Jose", state="CA")
    student = Student(name="Sam Student", email="s@s.test", password_hash="x", college="SJSU", city="San Jose",
                      major="Computer Science")
    db.add_all([company, student])
    db.flush()
    jobs = [
        Job(company_id=company.id, title="Data Science Intern", description="Build models.", category=JobCategory.internship,
            city="San Jose", state="CA", is_remote=True, salary_min=30, salary_max=40, pay_period=PayPeriod.hourly,
            posting_date=TODAY - timedelta(days=5), deadline=TODAY + timedelta(days=30)),
        Job(company_id=company.id, title="Data Analyst Intern", description="Analyse data.", category=JobCategory.internship,
            city="Sunnyvale", state="CA", is_remote=False, salary_min=20, salary_max=25, pay_period=PayPeriod.hourly,
            posting_date=TODAY - timedelta(days=3), deadline=TODAY + timedelta(days=20)),
    ]
    db.add_all(jobs)
    db.flush()
    db.add_all([JobSkill(job_id=jobs[0].id, skill="Python"), JobSkill(job_id=jobs[1].id, skill="SQL")])
    event = Event(company_id=company.id, name="CS Career Fair", description="Meet employers.",
                  event_datetime=datetime(2026, 11, 10, 14, 0), location="Hall A", city="San Jose")
    db.add(event)
    db.flush()
    db.add(EventEligibleMajor(event_id=event.id, major="Computer Science"))
    db.commit()
    return db, student, jobs, event


def ctx_for(world_):
    db, student, _, _ = world_
    return ToolContext(db=db, student=student, today=TODAY)


def new_conversation(student):
    return Conversation(conversation_id="c1", student_id=student.id)


# ---------------- the tools ----------------
def test_preferences_say_so_when_none_are_saved(world):
    out = execute_tool("get_student_preferences", {}, ctx_for(world))
    assert "NOT saved" in out and "San Jose" in out


def test_preferences_are_listed_when_saved(world):
    db, student, _, _ = world
    db.add(StudentPreference(student_id=student.id, preferred_categories=["internship"],
                             preferred_cities=["San Jose"], min_hourly_rate=25, open_to_remote=True))
    db.commit()
    out = execute_tool("get_student_preferences", {}, ctx_for(world))
    assert "internship" in out and "San Jose" in out and "$25/hr" in out


def test_search_jobs_filters_and_formats(world):
    ctx = ctx_for(world)
    out = execute_tool("search_jobs", {"category": "internship", "remote": True, "skills": ["Python"]}, ctx)
    assert "Data Science Intern" in out and "Data Analyst Intern" not in out
    assert "Acme Data" in out and "$30–$40/hr" in out and "deadline 2026-11-14" in out


def test_search_jobs_ignores_filler_words_in_the_title(world):
    out = execute_tool("search_jobs", {"title": "remote data science internship"}, ctx_for(world))
    assert "Data Science Intern" in out


def test_search_jobs_no_match_is_a_plain_message(world):
    out = execute_tool("search_jobs", {"company": "Nonexistent Corp"}, ctx_for(world))
    assert out.startswith("No jobs match")


def test_search_jobs_salary_sort_and_minimum_pay(world):
    ctx = ctx_for(world)
    out = execute_tool("search_jobs", {"sort": "salary"}, ctx)
    assert out.index("Data Science Intern") < out.index("Data Analyst Intern")
    out = execute_tool("search_jobs", {"min_hourly_pay": 35}, ctx)
    assert "Data Science Intern" in out and "Data Analyst Intern" not in out


def test_get_job_details_and_missing_id(world):
    _, _, jobs, _ = world
    out = execute_tool("get_job_details", {"job_id": jobs[0].id}, ctx_for(world))
    assert "Data Science Intern" in out and "Acme Data" in out and "Other recent postings" in out
    assert execute_tool("get_job_details", {"job_id": 9999}, ctx_for(world)).startswith("Error: there is no job")


def test_search_events_filters_by_date_and_eligibility(world):
    ctx = ctx_for(world)
    out = execute_tool("search_events", {"date_from": "2026-11-01", "date_to": "2026-11-30", "eligible_for_me": True}, ctx)
    assert "CS Career Fair" in out and "open to: Computer Science" in out
    assert "NOT eligible" not in out and "student (" not in out      # a major was searched: no extra "you" clause
    plain = execute_tool("search_events", {}, ctx)                    # no major searched: show the student's eligibility
    assert "student (Computer Science) is eligible" in plain
    out = execute_tool("search_events", {"major": "Marketing"}, ctx)
    assert out.startswith("No upcoming events")
    assert execute_tool("search_events", {"date_from": "next month"}, ctx).startswith("Error: invalid arguments")


@pytest.mark.parametrize("name,args", [
    ("save_job_or_event", {"item_type": "job"}),                       # missing item_id
    ("save_job_or_event", {"item_type": "company", "item_id": 1}),     # not in the enum
    ("search_jobs", {"salary": 5}),                                    # unknown argument
    ("search_jobs", {"remote": "maybe"}),                              # wrong type
    ("get_job_details", {"job_id": "abc"}),                            # not a number
    ("delete_everything", {}),                                         # unknown tool
])
def test_tools_return_error_strings_instead_of_raising(world, name, args):
    out = execute_tool(name, args, ctx_for(world))
    assert isinstance(out, str) and out.startswith("Error:")


def test_a_number_sent_as_text_is_accepted(world):
    _, _, jobs, _ = world
    assert "Data Science Intern" in execute_tool("get_job_details", {"job_id": str(jobs[0].id)}, ctx_for(world))


def test_every_schema_has_description_and_typed_parameters():
    assert len(TOOL_SCHEMAS) == 5
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        assert fn["description"] and fn["parameters"]["type"] == "object"
        for prop in fn["parameters"]["properties"].values():
            assert prop["type"] and prop["description"]


# ---------------- the confirmation gate ----------------
def test_confirm_action_yes_no_and_auto_approve():
    assert confirm_action("save_job_or_event", {"item_id": 1}, ask=lambda q: "yes") is True
    assert confirm_action("save_job_or_event", {"item_id": 1}, ask=lambda q: "No") is False
    assert confirm_action("save_job_or_event", {"item_id": 1}, ask=lambda q: "tell me more") is False
    assert confirm_action("save_job_or_event", {"item_id": 1}, auto_approve=True) is True


def test_confirm_action_treats_an_error_while_asking_as_no():
    def broken(_q):
        raise EOFError
    assert confirm_action("save_job_or_event", {}, ask=broken) is False


# ---------------- the loop ----------------
def test_loop_runs_a_tool_then_answers(world):
    _, student, jobs, _ = world
    client = ScriptedClient(call("search_jobs", category="internship"), say("Here are two internships."))
    logs = []
    result = run_assistant("find internships", new_conversation(student), ctx_for(world), client=client, log=logs.append)
    assert result.reply == "Here are two internships."
    assert [t.name for t in result.tool_calls] == ["search_jobs"]
    assert logs[0].startswith("[tool] search_jobs(") and logs[-1] == "Tool calls this run: 1"
    # the second model call was sent the tool result
    assert client.seen[1][-1]["role"] == "tool" and "Data Science Intern" in client.seen[1][-1]["content"]


def test_loop_stops_at_the_iteration_ceiling(world):
    _, student, _, _ = world
    client = ScriptedClient(*[call("get_student_preferences")] * 10)
    result = run_assistant("loop forever", new_conversation(student), ctx_for(world), client=client,
                           log=lambda _l: None, max_iterations=3)
    assert result.stopped_at_ceiling and result.iterations == 3 and len(result.tool_calls) == 3
    assert len(client.replies) == 7     # exactly 3 model calls were made


def test_unknown_tool_and_bad_arguments_go_back_to_the_model_as_text(world):
    _, student, _, _ = world
    bad_json = ModelReply("", [ToolRequest("search_jobs", {}, raw_arguments="{category: ")])
    client = ScriptedClient(call("hack_the_planet"), bad_json, say("Sorry about that."))
    result = run_assistant("x", new_conversation(student), ctx_for(world), client=client, log=lambda _l: None)
    assert result.tool_calls[0].result.startswith("Error: unknown tool")
    assert "not valid JSON" in result.tool_calls[1].result
    assert result.reply == "Sorry about that."


def test_conversation_history_is_sent_on_follow_ups(world):
    _, student, _, _ = world
    conv = new_conversation(student)
    client = ScriptedClient(say("first answer"), say("second answer"))
    run_assistant("first question", conv, ctx_for(world), client=client, log=lambda _l: None)
    run_assistant("make it higher paying", conv, ctx_for(world), client=client, log=lambda _l: None)
    contents = [m["content"] for m in client.seen[1]]
    assert contents[0].startswith("You are the career assistant") and "first question" in contents and "first answer" in contents


def test_model_failure_gives_a_friendly_reply(world):
    _, student, _, _ = world

    class Down(ModelClient):
        def complete(self, messages, tools):
            raise ModelError("connection refused")

    result = run_assistant("hi", new_conversation(student), ctx_for(world), client=Down(), log=lambda _l: None)
    assert "not reachable" in result.reply


# ---------------- saving, with the terminal-style gate ----------------
def test_save_after_yes(world):
    db, student, jobs, _ = world
    client = ScriptedClient(call("save_job_or_event", item_type="job", item_id=jobs[0].id), say("Saved it."))
    result = run_assistant("save job 1", new_conversation(student), ctx_for(world), client=client,
                           ask=lambda q: "yes", log=lambda _l: None)
    assert result.tool_calls[0].result.startswith("Saved:")
    assert db.query(SavedItem).count() == 1


def test_decline_saves_nothing_and_the_model_is_told_not_to_retry(world):
    db, student, jobs, _ = world
    client = ScriptedClient(call("save_job_or_event", item_type="job", item_id=jobs[0].id), say("OK, I did not save it."))
    result = run_assistant("save job 1", new_conversation(student), ctx_for(world), client=client,
                           ask=lambda q: "no", log=lambda _l: None)
    assert result.tool_calls[0].result.startswith("CANCELLED")
    assert db.query(SavedItem).count() == 0
    assert "Do not try to save it again" in client.seen[1][-1]["content"]
    assert len(result.tool_calls) == 1 and result.reply == "OK, I did not save it."


def test_save_unknown_id_and_duplicate_are_errors_without_asking(world):
    db, student, jobs, _ = world
    asked = []
    ask = lambda q: asked.append(q) or "yes"
    client = ScriptedClient(call("save_job_or_event", item_type="event", item_id=999), say("No such event."),
                            call("save_job_or_event", item_type="job", item_id=jobs[0].id), say("Saved."),
                            call("save_job_or_event", item_type="job", item_id=jobs[0].id), say("Already saved."))
    conv = new_conversation(student)
    first = run_assistant("save event 999", conv, ctx_for(world), client=client, ask=ask, log=lambda _l: None)
    assert first.tool_calls[0].result.startswith("Error: there is no event")
    run_assistant("save job", conv, ctx_for(world), client=client, ask=ask, log=lambda _l: None)
    third = run_assistant("save job again", conv, ctx_for(world), client=client, ask=ask, log=lambda _l: None)
    assert "already in the student's saved list" in third.tool_calls[0].result
    assert len(asked) == 1 and db.query(SavedItem).count() == 1


def test_read_only_tools_are_never_gated(world):
    _, student, _, _ = world
    asked = []
    client = ScriptedClient(call("search_jobs"), say("done"))
    run_assistant("jobs?", new_conversation(student), ctx_for(world), client=client,
                  ask=lambda q: asked.append(q) or "no", log=lambda _l: None)
    assert asked == []


# ---------------- saving, website style (the next chat message is the answer) ----------------
def test_website_confirmation_yes_over_two_messages(world):
    db, student, jobs, _ = world
    conv = new_conversation(student)
    client = ScriptedClient(call("save_job_or_event", item_type="job", item_id=jobs[0].id), say("Saved it for you."))
    first = run_assistant("save job 1", conv, ctx_for(world), client=client, log=lambda _l: None)
    assert "Reply yes" in first.reply and db.query(SavedItem).count() == 0 and conv.pending is not None
    second = run_assistant("yes", conv, ctx_for(world), client=client, log=lambda _l: None)
    assert db.query(SavedItem).count() == 1 and conv.pending is None and second.reply == "Saved it for you."


def test_website_confirmation_no_cancels(world):
    db, student, jobs, _ = world
    conv = new_conversation(student)
    client = ScriptedClient(call("save_job_or_event", item_type="job", item_id=jobs[0].id), say("Okay, not saved."))
    run_assistant("save job 1", conv, ctx_for(world), client=client, log=lambda _l: None)
    second = run_assistant("no thanks", conv, ctx_for(world), client=client, log=lambda _l: None)
    assert db.query(SavedItem).count() == 0 and second.tool_calls[0].result.startswith("CANCELLED")


# ---------------- the model client's parsing ----------------
def test_tool_request_parsing():
    assert _to_tool_request({"function": {"name": "a", "arguments": {"x": 1}}}).arguments == {"x": 1}
    assert _to_tool_request({"function": {"name": "a", "arguments": '{"x": 1}'}}).arguments == {"x": 1}
    broken = _to_tool_request({"function": {"name": "a", "arguments": "{x:"}})
    assert broken.arguments == {} and broken.raw_arguments == "{x:"


# ---------------- through the real endpoint ----------------
def test_endpoint_uses_the_agent_and_keeps_the_conversation(client, student_headers, monkeypatch):
    from app.services import assistant as service
    fake = ScriptedClient(say("Hello from the model."), say("Still here."))
    monkeypatch.setattr(service, "model_client", fake)
    first = client.post("/assistant/chat", json={"message": "hi"}, headers=student_headers).json()
    assert first["reply"] == "Hello from the model."
    again = client.post("/assistant/chat", json={"message": "again", "conversation_id": first["conversation_id"]},
                        headers=student_headers).json()
    assert again["conversation_id"] == first["conversation_id"]
    assert any(m["content"] == "hi" for m in fake.seen[1])
