"""Least-privilege edit opt-in and deletion-consent contracts for Cobuild tools."""

from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from dataiku_mcp import config
from dataiku_mcp.tools import cobuild


class DummyContext:
    async def info(self, _message):
        return None


class FakeResponse:
    def __init__(
        self,
        *,
        message="ok",
        response_type="answer",
        confirmation_id=None,
        objects_to_delete=None,
        deletion_impacts=None,
        is_error=False,
    ):
        self.message = message
        self.type = response_type
        self.is_error = is_error
        self.is_confirmation_request = confirmation_id is not None
        self.confirmation_id = confirmation_id
        self.objects_to_delete = objects_to_delete
        self.deletion_impacts = deletion_impacts


class FakeConversation:
    def __init__(self, conversation_id="conversation-1"):
        self.conversation_id = conversation_id
        self._pending_confirmation_id = None
        self.send_calls = []
        self.answer_calls = []
        self.next_send = FakeResponse()
        self.next_answer = FakeResponse(message="confirmed")
        self.answer_error = None

    def send_message(self, message, *, allow_edit_project=False):
        self.send_calls.append(
            {"message": message, "allow_edit_project": allow_edit_project}
        )
        self._pending_confirmation_id = self.next_send.confirmation_id
        return self.next_send

    def answer_confirmation(self, choice):
        if self._pending_confirmation_id is None:
            raise ValueError("No pending confirmation")
        consumed = self._pending_confirmation_id
        self._pending_confirmation_id = None
        self.answer_calls.append({"choice": choice, "confirmation_id": consumed})
        if self.answer_error is not None:
            raise self.answer_error
        self._pending_confirmation_id = self.next_answer.confirmation_id
        return self.next_answer


class FakeProject:
    def __init__(self, conversation):
        self.conversation = conversation

    def new_cobuild_conversation(self):
        return self.conversation


class FakeClient:
    def __init__(self, conversation=None):
        self.conversation = conversation or FakeConversation()
        self.requested_projects = []

    def get_project(self, project_key):
        self.requested_projects.append(project_key)
        return FakeProject(self.conversation)


@pytest.fixture(autouse=True)
def cobuild_env(monkeypatch):
    cobuild._conversations.clear()
    client = FakeClient()
    state = {"instance": "instance-a"}
    monkeypatch.setattr(cobuild, "get_dss_client", lambda *a, **k: client)
    monkeypatch.setattr(config, "get_current_instance_name", lambda: state["instance"])
    yield client, state
    cobuild._conversations.clear()


def run(coroutine):
    return asyncio.run(coroutine)


def start(project_key="PROJECT"):
    return json.loads(run(cobuild.start_cobuild_conversation(project_key, DummyContext())))


def send(*, allow_edit_project=None):
    kwargs = {}
    if allow_edit_project is not None:
        kwargs["allow_edit_project"] = allow_edit_project
    return json.loads(
        run(
            cobuild.send_cobuild_message(
                "conversation-1",
                "PROJECT",
                "inspect or build",
                DummyContext(),
                **kwargs,
            )
        )
    )


def answer(confirmation_id, choice="APPROVE"):
    return json.loads(
        run(
            cobuild.answer_cobuild_confirmation(
                "conversation-1",
                "PROJECT",
                choice,
                confirmation_id,
                DummyContext(),
            )
        )
    )


def test_edit_permission_defaults_false_in_schema_and_at_runtime(cobuild_env):
    client, _ = cobuild_env
    assert (
        inspect.signature(cobuild.send_cobuild_message)
        .parameters["allow_edit_project"]
        .default
        is False
    )
    start()

    send()

    assert client.conversation.send_calls[-1]["allow_edit_project"] is False


def test_edit_permission_is_a_per_message_grant(cobuild_env):
    client, _ = cobuild_env
    start()

    send(allow_edit_project=True)
    send()

    assert [
        call["allow_edit_project"] for call in client.conversation.send_calls
    ] == [True, False]


def test_confirmation_response_keeps_proposal_and_exact_id_together(cobuild_env):
    client, _ = cobuild_env
    client.conversation.next_send = FakeResponse(
        message="Delete old output?",
        response_type="delete_confirmation_request",
        confirmation_id="confirm-123",
        objects_to_delete=[{"type": "DATASET", "id": "old_output"}],
        deletion_impacts={"recipes": ["downstream"]},
    )
    start()

    result = send(allow_edit_project=True)

    assert result["confirmation_id"] == "confirm-123"
    assert result["objects_to_delete"] == [{"type": "DATASET", "id": "old_output"}]
    assert result["deletion_impacts"] == {"recipes": ["downstream"]}


def test_mismatched_confirmation_id_never_reaches_sdk(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-right",
    )
    start()
    send(allow_edit_project=True)

    with pytest.raises(ValueError, match="does not match"):
        answer("confirm-wrong")

    assert conversation.answer_calls == []
    assert conversation._pending_confirmation_id == "confirm-right"


@pytest.mark.parametrize("choice", ["APPROVE", "CANCEL"])
def test_exact_confirmation_id_is_consumed_once(cobuild_env, choice):
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-once",
    )
    start()
    send(allow_edit_project=True)

    result = answer("confirm-once", choice)

    assert result["message"] == "confirmed"
    assert conversation.answer_calls == [
        {"choice": choice, "confirmation_id": "confirm-once"}
    ]
    with pytest.raises(ValueError, match="No pending confirmation"):
        answer("confirm-once", choice)


def test_ambiguous_answer_failure_does_not_rearm_approval(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-once",
    )
    conversation.answer_error = ConnectionError("connection dropped after POST")
    start()
    send(allow_edit_project=True)

    with pytest.raises(ConnectionError, match="after POST"):
        answer("confirm-once")
    with pytest.raises(ValueError, match="No pending confirmation"):
        answer("confirm-once")


def test_list_does_not_disclose_approval_token(cobuild_env):
    client, _ = cobuild_env
    client.conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="never-list-this-token",
    )
    start()
    send(allow_edit_project=True)

    payload = json.loads(
        run(cobuild.list_cobuild_conversations("PROJECT", DummyContext()))
    )
    rendered = json.dumps(payload)

    assert "never-list-this-token" not in rendered
    assert payload["conversations"]["columns"][-1] == "has_pending_confirmation"
    assert payload["conversations"]["rows"][0][-1] is True


def test_project_and_instance_ownership_are_checked(cobuild_env):
    _client, state = cobuild_env
    start()

    with pytest.raises(ValueError, match="belongs to project"):
        run(
            cobuild.send_cobuild_message(
                "conversation-1", "OTHER", "inspect", DummyContext()
            )
        )

    state["instance"] = "instance-b"
    with pytest.raises(ValueError, match="belongs to instance"):
        send()
