"""
The chat endpoint (with a fake model): who may call it, what it accepts, and its answer shape.
Run from backend/:   python -m pytest -q
"""
import pytest

from app.assistant.model_client import ModelReply
from app.services import assistant as assistant_service

URL = "/assistant/chat"


class EchoModel:
    """A fake model that always answers in text, so these tests never need Ollama."""
    def complete(self, messages, tools):
        return ModelReply("fake reply")


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(assistant_service, "model_client", EchoModel())


def test_chat_needs_a_student_login(client, company_headers):
    assert client.post(URL, json={"message": "hi"}).status_code == 401
    assert client.post(URL, json={"message": "hi"}, headers=company_headers).status_code == 403


def test_chat_answers_with_the_agreed_shape(client, student_headers):
    r = client.post(URL, json={"message": "find me an internship"}, headers=student_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"reply", "conversation_id", "tool_calls"}
    assert body["reply"] and body["conversation_id"] and body["tool_calls"] == []


def test_a_new_conversation_gets_an_id_and_an_existing_one_is_kept(client, student_headers):
    first = client.post(URL, json={"message": "hello"}, headers=student_headers).json()
    again = client.post(URL, json={"message": "and now?", "conversation_id": first["conversation_id"]},
                        headers=student_headers).json()
    assert again["conversation_id"] == first["conversation_id"]
    other = client.post(URL, json={"message": "hello"}, headers=student_headers).json()
    assert other["conversation_id"] != first["conversation_id"]


def test_the_message_is_trimmed(client, student_headers):
    r = client.post(URL, json={"message": "   hi there   "}, headers=student_headers)
    assert r.status_code == 200


@pytest.mark.parametrize("message", ["", "   ", "x" * 2001], ids=["empty", "blank", "too-long"])
def test_bad_messages_are_rejected(client, student_headers, message):
    assert client.post(URL, json={"message": message}, headers=student_headers).status_code == 422


@pytest.mark.parametrize("body", [{}, {"message": 5}, {"message": "hi", "student_id": 9}, {"message": "hi", "conversation_id": "x" * 65}],
                         ids=["missing", "not-text", "unknown-field", "id-too-long"])
def test_malformed_requests_are_rejected(client, student_headers, body):
    assert client.post(URL, json=body, headers=student_headers).status_code == 422


def test_the_service_function_can_be_called_directly(db):
    """The router and website only call this function."""
    from app.models import Student
    from app.services.assistant import run_assistant
    student = Student(name="T", email="t@t.test", password_hash="x", college="SJSU")
    db.add(student)
    db.commit()
    out = run_assistant(db, student=student, message="hello", conversation_id="abc")
    assert out.conversation_id == "abc" and out.reply == "fake reply"
