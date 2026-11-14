"""
Lab 2 Part 6: token tracking, context compaction, tracing and stage timing.
Run from backend/:   python -m pytest tests/test_tokens_compaction_tracing.py -q
A scripted fake model reports token counts, so no Ollama is needed.
"""
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import db_timing
from app.assistant import compaction, conversation_store, memory, memory_consolidation as mc, tracing
from app.assistant.agent import Conversation, PendingAction, run_assistant
from app.assistant.model_client import ModelClient, ModelError, ModelReply, ToolRequest
from app.assistant.usage import COMPACT_AT_PERCENT, WARN_AT_PERCENT, Usage, estimate_messages_tokens, estimate_tokens
from app.enums import JobCategory, PayPeriod
from app.events import topics
from app.events.envelope import new_envelope
from app.events.handlers import dispatch
from app.services import assistant as service
from tests.conftest import STUDENT
from tests.factories import make_company, make_event, make_job, make_student
from tests.test_agent import ScriptedClient, TODAY, call, ctx_for, say, world  # noqa: F401  (world is a fixture)


class TokenModel(ModelClient):
    """Scripted replies that also report token counts. `delay` makes the model slow (to test the stage timing)."""

    def __init__(self, *replies, prompt=100, completion=20, delay=0.0):
        self.replies, self.prompt, self.completion, self.delay, self.seen = list(replies), prompt, completion, delay, []

    def complete(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        if self.delay:
            time.sleep(self.delay)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        reply.prompt_tokens, reply.completion_tokens = self.prompt, self.completion
        return reply


def chat(client, headers, message, conversation_id=None, trace_id=None):
    extra = {"X-Trace-ID": trace_id} if trace_id else {}
    return client.post("/assistant/chat", json={"message": message, "conversation_id": conversation_id},
                       headers={**headers, **extra}).json()


def student_id(db):
    return db.students.find_one({"email": STUDENT["email"]})["_id"]


def add_jobs(db):
    company = make_company(db, name="Acme Data", email="a@acme.test", city="San Jose", state="CA")
    today = date.today()
    return [make_job(db, company.id, title=title, description="d", category=JobCategory.internship, city=city, state="CA",
                     is_remote=False, salary_min=30, salary_max=40, pay_period=PayPeriod.hourly, skills=["Python"],
                     posting_date=today - timedelta(days=3), deadline=today + timedelta(days=30))
            for title, city in (("Data Science Intern", "San Jose"), ("Data Analyst Intern", "Sunnyvale"))], company


# ---------------------------------------------------------------- token tracking
def test_usage_counts_every_call_and_the_context_is_the_last_prompt_plus_answer():
    usage = Usage()
    usage.add(ModelReply("a", prompt_tokens=1000, completion_tokens=50))
    usage.add(ModelReply("b", prompt_tokens=1800, completion_tokens=100))
    assert (usage.model_calls, usage.prompt_tokens, usage.completion_tokens) == (2, 2800, 150)
    assert usage.context_tokens == 1900                       # what is in the window NOW: the last call, not the sum
    assert usage.percent(8192) == round(100 * 1900 / 8192, 1)


@pytest.mark.parametrize("tokens,warn,compact", [(0, False, False), (5734, False, False), (5735, True, False),
                                                  (5800, True, False), (6963, True, False), (6964, True, True)])
def test_warning_above_70_percent_and_compaction_at_85(tokens, warn, compact):
    """8192 x 0.70 = 5734.4 and 8192 x 0.85 = 6963.2: the flags flip just above those lines (decided on the exact ratio,
    not on the rounded percent that is shown: 6963 tokens is 84.996 percent, which displays as 85.0)."""
    usage = Usage()
    usage.add(ModelReply("x", prompt_tokens=tokens, completion_tokens=0))
    info = usage.as_dict(8192)
    assert (info["warn"], info["compact_recommended"]) == (warn, compact)
    assert WARN_AT_PERCENT == 70 and COMPACT_AT_PERCENT == 85


def test_the_model_client_reads_ollamas_token_counts(monkeypatch):
    from app.assistant.model_client import OllamaClient

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": "hi"}, "prompt_eval_count": 321, "eval_count": 45}

    monkeypatch.setattr("app.assistant.model_client.httpx.post", lambda *a, **k: Response())
    reply = OllamaClient().complete([{"role": "user", "content": "x"}], [])
    assert (reply.prompt_tokens, reply.completion_tokens) == (321, 45)


def test_the_agent_counts_tokens_after_every_model_call_and_times_the_stages(world):
    model = TokenModel(call("search_jobs", title="data"), say("Found two."), prompt=500, completion=40, delay=0.02)
    conversation = Conversation("c1", ctx_for(world).student.id)
    result = run_assistant("find data jobs", conversation, ctx_for(world), client=model, log=lambda _l: None)
    assert result.usage.model_calls == 2 and result.usage.prompt_tokens == 1000 and result.usage.completion_tokens == 80
    assert conversation.usage.model_calls == 2 and conversation.usage.last_prompt_tokens == 500
    assert result.stages["model_ms"] >= 40 and result.stages["tool_ms"] > 0          # 2 x 20 ms of "inference"; a real tool ran


def test_the_response_shows_tokens_and_context_percent_and_warns_above_70(client, student_headers, monkeypatch):
    monkeypatch.setattr(service, "model_client", TokenModel(say("hi"), prompt=5900, completion=100))
    usage = chat(client, student_headers, "hello")["usage"]
    assert usage["prompt_tokens"] == 5900 and usage["completion_tokens"] == 100
    assert usage["context_percent"] == round(100 * 6000 / 8192, 1) and usage["warn"] is True
    assert usage["compact_recommended"] is False and usage["compactions"] == 0


# ---------------------------------------------------------------- compaction
def test_the_summary_keeps_jobs_companies_events_preferences_applications_and_the_current_request(db):
    me = make_student(db, name="Sam", college="SJSU", city="San Jose", major="Computer Science")
    jobs, company = add_jobs(db)
    event = make_event(db, company.id, name="CS Career Fair", description="d", city="San Jose", location="Hall A",
                       event_datetime=datetime.combine(date.today() + timedelta(days=20), datetime.min.time()),
                       eligible_majors=["Computer Science"])
    from app.assistant.tools import ToolContext, execute_tool
    from tests.factories import make_application
    make_application(db, me.id, jobs[0].id)
    ctx = ToolContext(db=db, student=me)
    messages = [
        {"role": "user", "content": "what are my preferences"},
        {"role": "tool", "tool_name": "get_student_preferences", "content": execute_tool("get_student_preferences", {}, ctx)},
        {"role": "assistant", "content": "You like internships."},
        {"role": "user", "content": "find data internships"},
        {"role": "tool", "tool_name": "search_jobs", "content": execute_tool("search_jobs", {"title": "data"}, ctx)},
        {"role": "assistant", "content": "Here are two internships."},
        {"role": "user", "content": "any career fairs?"},
        {"role": "tool", "tool_name": "search_events", "content": execute_tool("search_events", {}, ctx)},
        {"role": "tool", "tool_name": "save_job_or_event", "content": "Saved: the job 1 (Data Science Intern) is now in the student's saved list."},
        {"role": "assistant", "content": "There is a fair."},
        {"role": "user", "content": "tell me about the first job"},
    ]
    summary = compaction.build_summary(messages, db, me, date(2026, 11, 14))
    assert summary.startswith(compaction.SUMMARY_MARKER)
    for expected in (f"job {jobs[0].id}: Data Science Intern at Acme Data", f"job {jobs[1].id}: Data Analyst Intern",
                     "Companies mentioned: Acme Data", f"event {event.id}: CS Career Fair", "open to Computer Science",
                     "Student's preferences: This student has NOT saved any job or event preferences",
                     "Saved during this conversation: the job 1 (Data Science Intern)",
                     "Applications on file: Data Science Intern (Pending)",
                     "What the student asked before: what are my preferences | find data internships | any career fairs?",
                     "Current request: tell me about the first job"):
        assert expected in summary, expected
    assert "<<<UNTRUSTED_DATABASE_CONTENT" in summary          # the company-written lines stay labelled as data


def test_compaction_replaces_the_history_with_a_summary_and_reports_sizes(db):
    me = make_student(db)
    jobs, _ = add_jobs(db)
    from app.assistant.tools import ToolContext, execute_tool
    big = execute_tool("search_jobs", {"title": "data"}, ToolContext(db=db, student=me))
    conv = Conversation("c1", me.id, messages=[{"role": "user", "content": "find data jobs"},
                                               {"role": "tool", "tool_name": "search_jobs", "content": big * 8},
                                               {"role": "assistant", "content": "Done."}])
    conv.usage.add(ModelReply("x", prompt_tokens=7000, completion_tokens=100))
    report = compaction.compact(conv, db, me)
    assert report["compacted"] and report["messages_before"] == 3 and report["messages_after"] == 2
    assert report["estimated_history_tokens_after"] < report["estimated_history_tokens_before"]
    assert compaction.is_summary(conv.messages[0]) and conv.messages[1]["role"] == "assistant" and conv.compactions == 1
    assert conv.usage.estimated and conv.usage.context_tokens < report["context_tokens_before"]
    assert report["context_tokens_before"] == 7100


def test_compaction_is_skipped_when_a_save_waits_for_an_answer_or_the_chat_is_tiny(db):
    me = make_student(db)
    waiting = Conversation("c1", me.id, messages=[{"role": "user", "content": "a"}] * 5,
                           pending=PendingAction(0, "save_job_or_event", {"item_type": "job", "item_id": 1}))
    assert "waiting" in compaction.compact(waiting, db, me)["skipped"] and len(waiting.messages) == 5
    assert "too short" in compaction.compact(Conversation("c2", me.id, messages=[{"role": "user", "content": "a"}]), db, me)["skipped"]


def test_a_second_compaction_keeps_what_the_first_one_knew(db):
    me = make_student(db)
    conv = Conversation("c1", me.id, messages=[
        {"role": "user", "content": compaction.build_summary([
            {"role": "tool", "tool_name": "search_jobs", "content": "- id 7 | Old Job | OldCo | San Jose, CA | internship | $20/hr | deadline 2027-01-01 | skills: Go"},
            {"role": "user", "content": "first question"}])},
        {"role": "assistant", "content": compaction.ACK},
        {"role": "user", "content": "second question"}, {"role": "assistant", "content": "answer"}])
    compaction.compact(conv, db, me)
    assert "job 7: Old Job at OldCo" in conv.messages[0]["content"] and "Current request: second question" in conv.messages[0]["content"]
    assert conv.compactions == 1


def test_the_summary_never_contains_a_secret(db):
    me = make_student(db)
    text = compaction.build_summary([{"role": "user", "content": "my password: hunter2hunter2 please"},
                                     {"role": "assistant", "content": "ok"}], db, me)
    assert "hunter2hunter2" not in text and "REDACTED" in text


def test_recall_after_compaction_the_next_turn_can_use_an_id_from_the_summary(client, student_headers, db, monkeypatch):
    """Deterministic recall check: after /compact the history is gone, but the model is still told which jobs came up,
    so a follow-up ("tell me more about the first one") can name job N and the real tool answers it."""
    jobs, _ = add_jobs(db)
    first = TokenModel(call("search_jobs", title="data"), say("Here are two internships."))
    monkeypatch.setattr(service, "model_client", first)
    reply = chat(client, student_headers, "find data internships")
    assert "compacted" in chat(client, student_headers, "/compact", reply["conversation_id"])["reply"].lower()
    stored = db.conversations.find_one({"_id": reply["conversation_id"]})
    assert len(stored["messages"]) == 2 and not any(m["role"] == "tool" for m in stored["messages"])      # the history is gone

    class Recaller(TokenModel):
        """Plays a model that reads the summary: finds the first job id in it and asks for that job's details."""
        def complete(self, messages, tools):
            reply = super().complete(messages, tools)
            if not reply.tool_calls and not reply.content:
                summary = next(m["content"] for m in messages if compaction.is_summary(m))
                reply.tool_calls = [ToolRequest("get_job_details", {"job_id": int(re.search(r"job (\d+):", summary).group(1))})]
            return reply

    second = Recaller(ModelReply(""), say("It is the Data Science Intern role."))
    monkeypatch.setattr(service, "model_client", second)
    out = chat(client, student_headers, "give me the details of the first one", reply["conversation_id"])
    assert out["tool_calls"][0]["name"] == "get_job_details"
    assert out["tool_calls"][0]["arguments"]["job_id"] in (jobs[0].id, jobs[1].id)      # an id that only the summary knew
    assert "Data" in out["tool_calls"][0]["result"] and out["usage"]["compactions"] == 1
    assert any(compaction.is_summary(m) for m in second.seen[0])       # the model really was sent the summary


def test_a_follow_up_after_compaction_still_counts_as_a_search_request(world):
    from app.assistant.agent import required_tools
    assert required_tools("make it higher paying", history_has_tools=True) == ["search_jobs"]
    conv = Conversation("c1", ctx_for(world).student.id, messages=[{"role": "user", "content": "[Conversation summary #1]"}], compactions=1)
    model = TokenModel(call("search_jobs", title="data", sort="salary"), say("Done."))
    result = run_assistant("make it higher paying", conv, ctx_for(world), client=model, log=lambda _l: None)
    assert not result.failures                                            # no "you needed a tool" repair was triggered


def test_auto_compaction_at_85_percent_and_the_command(client, student_headers, db, monkeypatch):
    add_jobs(db)
    # A realistic turn: the model searches (a tool result joins the history), then answers: 4 messages, so there is a history to shrink.
    monkeypatch.setattr(service, "model_client", TokenModel(call("search_jobs", title="data"), say("first"), say("second"),
                                                            prompt=7100, completion=100))
    one = chat(client, student_headers, "find data internships")
    # 7200 / 8192 = 87.9 percent: over the line, so this request compacted the stored history by itself
    assert one["usage"]["compactions"] == 1 and one["usage"]["compacted_now"]["messages_after"] == 2
    stored = db.conversations.find_one({"_id": one["conversation_id"]})
    assert compaction.is_summary(stored["messages"][0]) and stored["compactions"] == 1
    assert one["usage"]["context_estimated"] is True and one["usage"]["context_percent"] < 87.9      # the estimate is lower
    two = chat(client, student_headers, "thanks", one["conversation_id"])
    assert two["usage"]["compactions"] == 2 and two["usage"]["compacted_now"]      # still over the line: compacted again


def test_compact_command_reports_before_and_after(client, student_headers, db, monkeypatch):
    add_jobs(db)
    monkeypatch.setattr(service, "model_client", TokenModel(call("search_jobs", title="data"), say("ok"), prompt=3000, completion=100))
    one = chat(client, student_headers, "find data internships")
    reply = chat(client, student_headers, "/compact", one["conversation_id"])
    assert re.search(r"Compacted: 4 messages became 2", reply["reply"]) and "tokens" in reply["reply"]
    assert chat(client, student_headers, "/compact", "unknown-id")["reply"].startswith("There is no chat to compact")
    assert reply["usage"]["compactions"] == 1


def test_stored_conversation_keeps_its_usage_and_compactions(db):
    conv = Conversation("c9", 3, messages=[{"role": "user", "content": "x"}], compactions=2)
    conv.usage.add(ModelReply("a", prompt_tokens=10, completion_tokens=5))
    conversation_store.save(db, conv)
    loaded = conversation_store.load(db, 3, "c9")
    assert (loaded.compactions, loaded.usage.prompt_tokens, loaded.usage.last_completion_tokens) == (2, 10, 5)


def test_the_memory_learner_ignores_a_compaction_summary():
    text = mc.conversation_text([{"role": "user", "content": compaction.SUMMARY_MARKER + " #1] stuff"},
                                 {"role": "assistant", "content": compaction.ACK},
                                 {"role": "user", "content": "I like Go"}])
    assert text == "Student: I like Go"


def test_estimates_are_roughly_a_quarter_of_the_characters():
    assert estimate_tokens("a" * 400) == 100 and estimate_tokens("") == 0
    assert estimate_messages_tokens([{"role": "user", "content": "a" * 40}]) == 14


# ---------------------------------------------------------------- tracing
def test_every_request_gets_a_trace_id_and_a_trace_document_with_stage_times(client, student_headers, db, monkeypatch):
    add_jobs(db)
    monkeypatch.setattr(service, "model_client", TokenModel(call("search_jobs", title="data"), say("Found."), say("hello"), prompt=400, completion=30, delay=0.01))
    out = chat(client, student_headers, "find data internships secret-words", trace_id="trace-demo-1")
    assert out["trace_id"] == "trace-demo-1"
    trace = db.traces.find_one({"trace_id": "trace-demo-1"})
    assert trace["kind"] == "chat" and trace["status"] == "ok" and trace["tools"] == ["search_jobs"]
    assert trace["model_calls"] == 2 and trace["prompt_tokens"] == 800
    s = trace["stages"]
    assert s["model_ms"] >= 20 and s["tool_ms"] > 0 and {"db_ms", "tool_db_ms", "tool_compute_ms", "db_calls"} <= set(s)
    assert trace["total_ms"] >= s["model_ms"] + s["tool_ms"]
    assert "secret-words" not in str(trace)                              # what the student typed is never stored in a trace
    assert chat(client, student_headers, "hello")["trace_id"] != "trace-demo-1"      # no header: a fresh id each request


def test_a_failed_request_leaves_a_failed_trace(client, student_headers, db, monkeypatch):
    monkeypatch.setattr(service, "model_client", TokenModel(ModelError("the model server is down")))
    out = chat(client, student_headers, "find jobs", trace_id="trace-fail-1")
    assert "not reachable" in out["reply"]
    trace = db.traces.find_one({"trace_id": "trace-fail-1"})
    assert trace["status"] == "model_unreachable" and trace["stages"]["model_ms"] >= 0


def test_other_failures_have_their_own_status(world):
    for model, expected in ((TokenModel(*[call("search_jobs", title="data")] * 8), "iteration_ceiling"),):
        result = run_assistant("find data jobs", Conversation("c", ctx_for(world).student.id), ctx_for(world), client=model, log=lambda _l: None)
        assert result.error == expected
    result = run_assistant("find jobs", Conversation("c", 999), ctx_for(world), client=TokenModel(), log=lambda _l: None)
    assert result.error == "not_authorized"


def test_the_trace_id_is_in_the_log_lines(client, student_headers, monkeypatch, caplog):
    monkeypatch.setattr(service, "model_client", TokenModel(say("hi")))
    project_log = logging.getLogger("handshake")        # the app sets propagate=False, so pytest must listen here
    project_log.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="handshake"):
            chat(client, student_headers, "hello", trace_id="trace-log-1")
    finally:
        project_log.removeHandler(caplog.handler)
    lines = [r.getMessage() for r in caplog.records if "trace_id=trace-log-1" in r.getMessage()]
    assert any(l.startswith("event=assistant_chat trace_id=trace-log-1 status=ok total_ms=") for l in lines)
    assert any("model_ms=" in l and "db_ms=" in l and "tool_ms=" in l for l in lines)


def test_the_trace_command_shows_my_last_request_and_never_anyone_elses(client, student_headers, db, monkeypatch):
    monkeypatch.setattr(service, "model_client", TokenModel(say("hi"), say("yo"), delay=0.01))
    assert "no trace for you yet" in chat(client, student_headers, "/trace")["reply"]
    chat(client, student_headers, "hello", trace_id="trace-mine-1")
    shown = chat(client, student_headers, "/trace")["reply"]
    assert "trace-mine-1" in shown and "model_ms=" in shown and "slowest stage" in shown
    token = client.post("/auth/student/signup", json={**STUDENT, "email": "bob@example.com"}).json()["access_token"]
    assert "no trace for you yet" in chat(client, {"Authorization": f"Bearer {token}"}, "/trace")["reply"]


def test_the_trace_id_follows_a_memory_command_into_the_kafka_event_and_the_worker(client, student_headers, db, monkeypatch):
    """chat request -> /memory consolidate -> Kafka envelope (inline here) -> worker handler: one trace id the whole way."""
    monkeypatch.setattr(mc, "model_client", TokenModel(*[ModelReply("{}")] * 8))
    out = chat(client, student_headers, "/memory consolidate", trace_id="trace-kafka-1")
    assert out["trace_id"] == "trace-kafka-1"
    kinds = sorted(d["kind"] for d in db.traces.find({"trace_id": "trace-kafka-1"}))
    assert kinds == ["chat", "memory_worker"]
    run = db.memory_runs.find_one({"trace_id": "trace-kafka-1"})
    assert run is not None and run["event_type"] == "memory.consolidate_requested"


def test_the_worker_trace_measures_the_queue_wait_from_the_envelope_time(db, monkeypatch):
    me = make_student(db)
    memory.add_entry(db, me.id, "skill", "Knows SQL", on=date(2026, 1, 1))
    memory.add_entry(db, me.id, "skill", "Knows SQL well", on=date(2026, 1, 2))
    monkeypatch.setattr(mc, "model_client", TokenModel(ModelReply("{}"), prompt=300, completion=10, delay=0.01))
    env = new_envelope(topics.MEMORY_CONSOLIDATE_REQUESTED, {"student_id": me.id}, "trace-wait-1", "test")
    env.timestamp = (datetime.now(timezone.utc) - timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")   # sent 3 s ago
    dispatch(db, env)
    trace = db.traces.find_one({"trace_id": "trace-wait-1", "kind": "memory_worker"})
    assert 2900 <= trace["stages"]["queue_wait_ms"] <= 6000 and trace["stages"]["model_ms"] >= 10
    assert trace["prompt_tokens"] == 300 and tracing.dominant_stage(trace["stages"]) == "queue wait"


def test_a_failing_worker_leaves_an_error_trace(db, monkeypatch):
    me = make_student(db)
    memory.add_entry(db, me.id, "skill", "Knows SQL", on=date(2026, 1, 1))
    memory.add_entry(db, me.id, "skill", "Knows Go", on=date(2026, 1, 2))

    class Boom(ModelClient):
        def complete(self, messages, tools):
            raise RuntimeError("boom")

    monkeypatch.setattr(mc, "model_client", Boom())
    with pytest.raises(RuntimeError):
        dispatch(db, new_envelope(topics.MEMORY_CONSOLIDATE_REQUESTED, {"student_id": me.id}, "trace-err-1", "test"))
    assert db.traces.find_one({"trace_id": "trace-err-1"})["status"] == "error"


def test_a_trace_that_cannot_be_saved_never_breaks_the_chat(client, student_headers, monkeypatch):
    monkeypatch.setattr(service, "model_client", TokenModel(say("still works")))
    from mongomock.collection import Collection
    original = Collection.insert_one

    def insert_one(self, document, *args, **kwargs):
        if self.name == "traces":
            raise RuntimeError("disk full")              # only the trace write fails
        return original(self, document, *args, **kwargs)

    monkeypatch.setattr(Collection, "insert_one", insert_one)
    assert chat(client, student_headers, "hello")["reply"] == "still works"


# ---------------------------------------------------------------- stage timing helpers
def test_the_database_listener_counts_only_inside_a_measured_request_and_splits_tool_time():
    event = SimpleNamespace(duration_micros=2500)
    db_timing.LISTENER.succeeded(event)                                  # outside a request: ignored, no error
    with db_timing.measure() as timer:
        db_timing.LISTENER.succeeded(event)                              # 2.5 ms outside a tool
        with db_timing.tool_scope():
            db_timing.LISTENER.succeeded(SimpleNamespace(duration_micros=4000))
            db_timing.LISTENER.failed(SimpleNamespace(duration_micros=1000))
        db_timing.LISTENER.succeeded(event)
    assert timer.db_calls == 4 and round(timer.db_ms, 1) == 10.0 and round(timer.tool_db_ms, 1) == 5.0


def test_two_requests_never_mix_their_database_time():
    import concurrent.futures

    def one(ms):
        with db_timing.measure() as timer:
            for _ in range(50):
                db_timing.LISTENER.succeeded(SimpleNamespace(duration_micros=ms * 1000))
                time.sleep(0.0005)
        return round(timer.db_ms)

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        assert list(pool.map(one, (1, 2))) == [50, 100]


def test_stages_and_the_slowest_stage():
    stages = tracing.stages_from(model_ms=900, tool_ms=120, db_ms=60, tool_db_ms=50, db_calls=7)
    assert stages["tool_compute_ms"] == 70 and "queue_wait_ms" not in stages
    assert tracing.dominant_stage(stages) == "model inference"
    assert tracing.dominant_stage(tracing.stages_from(10, 100, 90, 90, 3)) == "database queries"
    assert tracing.dominant_stage(tracing.stages_from(10, 100, 5, 5, 3)) == "tool execution (not database)"
    assert tracing.dominant_stage(tracing.stages_from(10, 0, 0, 0, 0, queue_wait_ms=500)) == "queue wait"
    assert tracing.dominant_stage({}) is None


def test_the_trace_collection_has_its_indexes(db):
    info = db.traces.index_information()
    assert any(v.get("expireAfterSeconds") == 2592000 for v in info.values())
    assert any(v["key"] == [("trace_id", 1)] for v in info.values())
