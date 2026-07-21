"""Least-privilege and deletion-consent contracts for Cobuild tools."""

from __future__ import annotations

import asyncio
import inspect
import json
import time

import pytest

from dataiku_mcp import config
from dataiku_mcp.tools import cobuild
from dataiku_mcp.tools.utils import auth


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
        self.client = None
        self._pending_confirmation_id = None
        self.send_calls = []
        self.answer_calls = []
        self.next_send = FakeResponse()
        self.next_answer = FakeResponse(message="confirmed")
        self.answer_delay = 0
        self.answer_error = None

    def send_message(self, message, *, allow_edit_project=False):
        self.send_calls.append(
            {
                "message": message,
                "allow_edit_project": allow_edit_project,
                "client": self.client,
            }
        )
        self._pending_confirmation_id = self.next_send.confirmation_id
        return self.next_send

    def answer_confirmation(self, choice):
        if self._pending_confirmation_id is None:
            raise ValueError("No pending confirmation")
        consumed = self._pending_confirmation_id
        self._pending_confirmation_id = None
        self.answer_calls.append(
            {"choice": choice, "confirmation_id": consumed, "client": self.client}
        )
        if self.answer_delay:
            time.sleep(self.answer_delay)
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
    def __init__(self, conversation=None, label="client"):
        self.conversation = conversation or FakeConversation()
        self.label = label
        self.requested_projects = []

    def get_project(self, project_key):
        self.requested_projects.append(project_key)
        return FakeProject(self.conversation)


class RehydratedConversation(FakeConversation):
    created = []

    def __init__(self, client, project_key, conversation_id):
        super().__init__(conversation_id)
        self.client = client
        self.project_key = project_key
        type(self).created.append(self)


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("DKU_MCP_STATE_DIR", str(tmp_path / "state"))
    with cobuild._registry_lock:
        cobuild._conversations.clear()
    client = FakeClient()
    RehydratedConversation.created.clear()
    binding = ["instance-a", client, "principal-a"]
    monkeypatch.setattr(cobuild, "_capture_binding", lambda: tuple(binding))
    yield binding
    with cobuild._registry_lock:
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


def test_edit_permission_defaults_false_in_schema_and_at_runtime(isolate_registry):
    assert (
        inspect.signature(cobuild.send_cobuild_message)
        .parameters["allow_edit_project"]
        .default
        is False
    )
    start()

    send()

    assert isolate_registry[1].conversation.send_calls[-1]["allow_edit_project"] is False


def test_edit_permission_is_a_per_message_grant(isolate_registry):
    start()

    send(allow_edit_project=True)
    send()

    assert [
        call["allow_edit_project"]
        for call in isolate_registry[1].conversation.send_calls
    ] == [True, False]


def test_confirmation_response_keeps_proposal_and_exact_id_together(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        message="Delete old output?",
        response_type="delete_confirmation_request",
        confirmation_id="confirm-123",
        objects_to_delete=[{"type": "DATASET", "id": "old_output"}],
        deletion_impacts={"recipes": ["downstream"]},
    )
    start()

    result = send(allow_edit_project=True)

    assert result["confirmation_id"] == "confirm-123"
    assert result["objects_to_delete"] == [
        {"type": "DATASET", "id": "old_output"}
    ]
    assert result["deletion_impacts"] == {"recipes": ["downstream"]}


def test_confirmation_without_sdk_id_fails_closed(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        objects_to_delete=[{"type": "DATASET", "id": "old_output"}],
    )
    conversation.next_send.is_confirmation_request = True
    start()

    with pytest.raises(RuntimeError, match="without a confirmation id"):
        send(allow_edit_project=True)


def test_mismatched_confirmation_id_never_reaches_sdk(isolate_registry):
    conversation = isolate_registry[1].conversation
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
def test_exact_confirmation_id_is_consumed_once(isolate_registry, choice):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-once",
    )
    start()
    send(allow_edit_project=True)

    result = answer("confirm-once", choice)

    assert result["message"] == "confirmed"
    assert conversation.answer_calls == [
        {
            "choice": choice,
            "confirmation_id": "confirm-once",
            "client": isolate_registry[1],
        }
    ]
    with pytest.raises(ValueError, match="No pending confirmation"):
        answer("confirm-once", choice)


def test_ambiguous_answer_failure_does_not_rearm_approval(isolate_registry):
    conversation = isolate_registry[1].conversation
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


def test_concurrent_approvals_are_serialized_and_only_one_can_win(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-once",
    )
    conversation.answer_delay = 0.05
    start()
    send(allow_edit_project=True)

    async def race():
        calls = [
            cobuild.answer_cobuild_confirmation(
                "conversation-1",
                "PROJECT",
                "APPROVE",
                "confirm-once",
                DummyContext(),
            )
            for _ in range(2)
        ]
        return await asyncio.gather(*calls, return_exceptions=True)

    outcomes = run(race())

    assert len(conversation.answer_calls) == 1
    assert sum(isinstance(item, ValueError) for item in outcomes) == 1


def test_list_does_not_disclose_approval_token(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
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


def test_different_credential_cannot_discover_or_use_conversation(isolate_registry):
    start()
    isolate_registry[2] = "principal-b"

    listed = json.loads(
        run(cobuild.list_cobuild_conversations("PROJECT", DummyContext()))
    )
    assert listed["conversations"]["rows"] == []

    with pytest.raises(ValueError, match="current credential"):
        send()


def test_project_and_instance_ownership_are_checked(isolate_registry):
    start()

    with pytest.raises(ValueError, match="belongs to project"):
        run(
            cobuild.send_cobuild_message(
                "conversation-1", "OTHER", "inspect", DummyContext()
            )
        )

    isolate_registry[0] = "instance-b"
    with pytest.raises(ValueError, match="belongs to instance"):
        send()


def test_each_request_rebinds_retained_handle_to_current_client(isolate_registry):
    start()
    original_client = isolate_registry[1]
    send()

    replacement = FakeClient(label="replacement")
    isolate_registry[1] = replacement
    send()

    calls = original_client.conversation.send_calls
    assert calls[0]["client"] is original_client
    assert calls[1]["client"] is replacement


def test_start_captures_binding_before_first_await(monkeypatch):
    conversation = FakeConversation()
    captured_client = FakeClient(conversation, label="captured")
    later_client = FakeClient(conversation, label="later")
    calls = []

    def capture():
        calls.append("capture")
        return "instance-a", captured_client, "principal-a"

    class SwitchingContext:
        async def info(self, _message):
            calls.append("await")
            monkeypatch.setattr(
                cobuild,
                "_capture_binding",
                lambda: ("instance-b", later_client, "principal-b"),
            )

    monkeypatch.setattr(cobuild, "_capture_binding", capture)

    run(cobuild.start_cobuild_conversation("PROJECT", SwitchingContext()))

    assert calls == ["capture", "await"]
    assert captured_client.requested_projects == ["PROJECT"]
    assert later_client.requested_projects == []


def test_principal_fingerprint_is_stable_distinct_and_not_the_secret(monkeypatch):
    class Client:
        def __init__(self, _url, _key):
            self._session = type("Session", (), {})()

    monkeypatch.setattr(auth.dataikuapi, "DSSClient", Client)
    first = config.DSSInstance(
        name="one",
        url="https://one",
        api_key="secret-one",
        no_check_certificate=False,
        source="test",
    )
    second = config.DSSInstance(
        name="two",
        url="https://one",
        api_key="secret-two",
        no_check_certificate=False,
        source="test",
    )

    _, fingerprint_a = auth.get_dss_client_and_principal(first)
    _, fingerprint_a_again = auth.get_dss_client_and_principal(first)
    _, fingerprint_b = auth.get_dss_client_and_principal(second)

    assert fingerprint_a == fingerprint_a_again
    assert fingerprint_a != fingerprint_b
    assert "secret-one" not in fingerprint_a
    assert len(fingerprint_a) == 64


def test_conversation_rehydrates_after_process_local_cache_is_lost(
    isolate_registry, monkeypatch
):
    start()
    with cobuild._registry_lock:
        cobuild._conversations.clear()
    replacement_client = FakeClient(label="after-restart")
    isolate_registry[1] = replacement_client
    monkeypatch.setattr(cobuild, "DSSCobuildConversation", RehydratedConversation)

    result = send()

    assert result["message"] == "ok"
    assert len(RehydratedConversation.created) == 1
    restored = RehydratedConversation.created[0]
    assert restored.conversation_id == "conversation-1"
    assert restored.project_key == "PROJECT"
    assert restored.send_calls[0]["client"] is replacement_client


def test_pending_confirmation_can_be_answered_after_rehydration(
    isolate_registry, monkeypatch
):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        message="Delete old output?",
        response_type="delete_confirmation_request",
        confirmation_id="confirm-after-restart",
        objects_to_delete=[{"type": "DATASET", "id": "old_output"}],
        deletion_impacts={"recipes": ["downstream"]},
    )
    start()
    send(allow_edit_project=True)
    with cobuild._registry_lock:
        cobuild._conversations.clear()
    monkeypatch.setattr(cobuild, "DSSCobuildConversation", RehydratedConversation)

    result = answer("confirm-after-restart")

    assert result["message"] == "confirmed"
    assert RehydratedConversation.created[0].answer_calls[0]["confirmation_id"] == (
        "confirm-after-restart"
    )


def test_list_comes_from_durable_state_after_cache_loss(isolate_registry):
    start()
    with cobuild._registry_lock:
        cobuild._conversations.clear()

    payload = json.loads(
        run(cobuild.list_cobuild_conversations("PROJECT", DummyContext()))
    )

    created_at = payload["conversations"]["rows"][0][3]
    assert payload["conversations"]["rows"] == [
        ["conversation-1", "instance-a", "PROJECT", created_at, False]
    ]


def test_unanswered_proposal_blocks_a_new_message(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-first",
        objects_to_delete=[{"id": "old"}],
        deletion_impacts={"count": 1},
    )
    start()
    send(allow_edit_project=True)

    with pytest.raises(ValueError, match="unanswered deletion proposal"):
        send()

    assert len(conversation.send_calls) == 1


def test_proposal_is_not_approvable_when_persistence_fails(
    isolate_registry, monkeypatch
):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-not-durable",
        objects_to_delete=[{"id": "old"}],
        deletion_impacts={"count": 1},
    )
    start()

    def fail_persistence(*_args, **_kwargs):
        raise RuntimeError("disk unavailable")

    monkeypatch.setattr(
        cobuild.ConversationStore,
        "set_pending_confirmation",
        fail_persistence,
    )

    with pytest.raises(RuntimeError, match="disk unavailable"):
        send(allow_edit_project=True)

    assert conversation._pending_confirmation_id is None


def test_wrong_owner_cannot_rehydrate_known_conversation_id(
    isolate_registry, monkeypatch
):
    start()
    with cobuild._registry_lock:
        cobuild._conversations.clear()
    isolate_registry[2] = "principal-b"
    monkeypatch.setattr(cobuild, "DSSCobuildConversation", RehydratedConversation)

    with pytest.raises(ValueError, match="current credential"):
        send()

    assert RehydratedConversation.created == []
