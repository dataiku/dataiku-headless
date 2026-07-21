"""Least-privilege and deletion-consent contracts for Cobuild tools."""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
import threading
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
        self.send_delay = 0
        self.send_started = threading.Event()
        self.send_release = None
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
        self.send_started.set()
        if self.send_release is not None:
            self.send_release.wait(timeout=5)
        if self.send_delay:
            time.sleep(self.send_delay)
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
        cobuild._turns.clear()
    client = FakeClient()
    RehydratedConversation.created.clear()
    binding = ["instance-a", client, "principal-a"]
    monkeypatch.setattr(cobuild, "_capture_binding", lambda: tuple(binding))
    yield binding
    with cobuild._registry_lock:
        cobuild._conversations.clear()
        turns = list(cobuild._turns.values())
    for turn in turns:
        release = getattr(turn.entry.conversation, "send_release", None)
        if release is not None:
            release.set()
        try:
            turn.future.result(timeout=2)
        except TimeoutError:
            pass
        if turn.future.done():
            cobuild._try_finalize(turn)
    with cobuild._registry_lock:
        cobuild._turns.clear()


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

    result = send(allow_edit_project=True)

    assert result["status"] == "error"
    assert result["error_kind"] == "missing_confirmation_id"
    assert "confirmation_id" not in result
    record = cobuild._store().read_owned(
        "conversation-1",
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="principal-a",
    )
    assert record["pending_confirmation_id"] is None

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

    result = answer("confirm-once")

    assert result["status"] == "error"
    assert result["error_kind"] == "transport_outcome_unknown"
    assert "after POST" in result["message"]
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
    payloads = [json.loads(item) for item in outcomes]
    assert {payload["status"] for payload in payloads} == {
        "completed",
        "in_progress",
    }
    assert len({payload["turn_id"] for payload in payloads}) == 1


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
        [
            "conversation-1",
            "instance-a",
            "PROJECT",
            created_at,
            "idle",
            None,
            False,
        ]
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

    original = cobuild.ConversationStore.record_turn_result
    unavailable = True

    def fail_while_unavailable(self, *_args, **_kwargs):
        if unavailable:
            raise RuntimeError("disk unavailable")
        return original(self, *_args, **_kwargs)

    monkeypatch.setattr(
        cobuild.ConversationStore,
        "record_turn_result",
        fail_while_unavailable,
    )

    result = send(allow_edit_project=True)

    assert result["status"] == "finalization_pending"
    assert "confirmation_id" not in result
    record = cobuild._store().read_owned(
        "conversation-1",
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="principal-a",
    )
    assert record["pending_confirmation_id"] is None
    blocked = answer("confirm-not-durable")
    assert blocked["status"] == "in_progress"
    assert isolate_registry[1].conversation.answer_calls == []

    unavailable = False
    persisted = json.loads(
        run(
            cobuild.get_cobuild_turn_status(
                "conversation-1",
                "PROJECT",
                DummyContext(),
                result["turn_id"],
            )
        )
    )
    assert persisted["status"] == "needs_confirmation"
    assert persisted["confirmation_id"] == "confirm-not-durable"
    assert answer("confirm-not-durable")["status"] == "completed"


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


def test_timeout_retains_worker_and_poll_returns_one_terminal_result(
    isolate_registry,
):
    conversation = isolate_registry[1].conversation
    conversation.send_delay = 1.3
    start()

    timed_out = json.loads(
        run(
            cobuild.send_cobuild_message(
                "conversation-1",
                "PROJECT",
                "build once",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=1,
            )
        )
    )

    assert timed_out["status"] == "timeout"
    assert len(conversation.send_calls) == 1
    turn = cobuild._turns["conversation-1"]
    assert turn.turn_id == timed_out["turn_id"]
    assert turn.thread.daemon is True
    assert turn.future.cancel() is False
    assert turn.future.cancelled() is False

    while not turn.future.done():
        time.sleep(0.02)
    completed = json.loads(
        run(
            cobuild.get_cobuild_turn_status(
                "conversation-1",
                "PROJECT",
                DummyContext(),
                timed_out["turn_id"],
            )
        )
    )

    assert completed["status"] == "completed"
    assert completed["turn_id"] == timed_out["turn_id"]
    assert len(conversation.send_calls) == 1


def test_overlapping_send_returns_the_active_turn_without_resending(
    isolate_registry,
):
    conversation = isolate_registry[1].conversation
    conversation.send_release = threading.Event()
    start()

    async def overlap():
        first = asyncio.create_task(
            cobuild.send_cobuild_message(
                "conversation-1",
                "PROJECT",
                "mutate once",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=2,
            )
        )
        while not conversation.send_started.is_set():
            await asyncio.sleep(0.005)
        second = await cobuild.send_cobuild_message(
            "conversation-1",
            "PROJECT",
            "mutate twice",
            DummyContext(),
            allow_edit_project=True,
            timeout_seconds=1,
        )
        conversation.send_release.set()
        return json.loads(await first), json.loads(second)

    first, second = run(overlap())

    assert first["status"] == "completed"
    assert second["status"] == "in_progress"
    assert second["turn_id"] == first["turn_id"]
    assert [call["message"] for call in conversation.send_calls] == ["mutate once"]


def test_waiter_settles_result_even_if_done_callback_is_delayed(
    isolate_registry,
    monkeypatch,
):
    start()
    callback_entered = threading.Event()

    def skipped_callback(_turn, _future):
        callback_entered.set()

    monkeypatch.setattr(cobuild, "_on_turn_done", skipped_callback)
    first = send()
    assert callback_entered.is_set()
    second = send()

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert len(isolate_registry[1].conversation.send_calls) == 2


def test_cancelling_the_client_wait_does_not_cancel_the_worker(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.send_release = threading.Event()
    start()

    async def cancel_wait():
        waiting = asyncio.create_task(
            cobuild.send_cobuild_message(
                "conversation-1",
                "PROJECT",
                "keep working",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=2,
            )
        )
        while not conversation.send_started.is_set():
            await asyncio.sleep(0.005)
        turn = cobuild._turns["conversation-1"]
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert turn.future.cancelled() is False
        conversation.send_release.set()
        return turn

    turn = run(cancel_wait())
    turn.future.result(timeout=2)
    completed = json.loads(
        run(
            cobuild.get_cobuild_turn_status(
                "conversation-1", "PROJECT", DummyContext(), turn.turn_id
            )
        )
    )

    assert completed["status"] == "completed"
    assert len(conversation.send_calls) == 1


def test_poll_rejects_a_stale_or_invented_turn_id(isolate_registry):
    start()
    completed = send()

    with pytest.raises(ValueError, match="not the latest turn"):
        run(
            cobuild.get_cobuild_turn_status(
                "conversation-1",
                "PROJECT",
                DummyContext(),
                "not-the-returned-turn",
            )
        )

    assert completed["turn_id"]


def test_authenticated_poll_recovers_the_complete_durable_proposal(
    isolate_registry,
):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        message="Delete these exact objects?",
        response_type="delete_confirmation_request",
        confirmation_id="confirm-from-disk",
        objects_to_delete=[{"type": "DATASET", "id": "old_output"}],
        deletion_impacts={"recipes": ["downstream"]},
    )
    start()
    proposal = send(allow_edit_project=True)
    with cobuild._registry_lock:
        cobuild._turns.clear()
        cobuild._conversations.clear()

    recovered = json.loads(
        run(
            cobuild.get_cobuild_turn_status(
                "conversation-1",
                "PROJECT",
                DummyContext(),
                proposal["turn_id"],
            )
        )
    )

    assert recovered["status"] == "needs_confirmation"
    assert recovered["confirmation_id"] == "confirm-from-disk"
    assert recovered["objects_to_delete"] == [
        {"type": "DATASET", "id": "old_output"}
    ]
    assert recovered["deletion_impacts"] == {"recipes": ["downstream"]}


def test_sdk_wrapper_values_are_normalized_before_durable_finalization(
    isolate_registry,
):
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-json-safe",
        objects_to_delete=[{"sdk_value": object()}],
    )
    start()

    proposal = send(allow_edit_project=True)

    assert proposal["status"] == "needs_confirmation"
    assert isinstance(proposal["objects_to_delete"][0]["sdk_value"], str)
    record = cobuild._store().read_owned(
        "conversation-1",
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="principal-a",
    )
    assert record["last_turn_status"] == "needs_confirmation"


def test_live_external_turn_is_not_misreported_lost_and_capacity_is_global(
    isolate_registry,
    tmp_path,
):
    start()
    store = cobuild._store()
    store.register(
        "conversation-2",
        {
            "instance_name": "instance-a",
            "project_key": "PROJECT",
            "owner_fingerprint": "principal-a",
            "created_at": "now",
            "pending_confirmation_id": None,
            "last_turn_id": None,
            "last_turn_status": "idle",
            "last_result": None,
        },
    )
    ready_path = tmp_path / "child-ready"
    child_code = """
import sys
from pathlib import Path
from dataiku_mcp.tools.utils.conversation_store import ConversationStore

store = ConversationStore(sys.argv[1])
claim, _ = store.claim_turn(
    "conversation-1",
    "external-turn",
    instance_name="instance-a",
    project_key="PROJECT",
    owner_fingerprint="principal-a",
    kind="message",
    allow_edit_project=True,
    max_concurrent_turns=1,
)
Path(sys.argv[2]).write_text("ready", encoding="utf-8")
sys.stdin.readline()
claim.release()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(store.path), str(ready_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                pytest.fail("child process did not claim its Cobuild turn in time")
            time.sleep(0.02)
        if process.poll() is not None:
            pytest.fail(f"child process failed: {process.stderr.read()}")

        live = json.loads(
            run(
                cobuild.get_cobuild_turn_status(
                    "conversation-1",
                    "PROJECT",
                    DummyContext(),
                    "external-turn",
                )
            )
        )
        assert live["status"] == "in_progress"
        assert live["turn_id"] == "external-turn"

        with pytest.raises(cobuild.ConversationTurnSaturated) as saturated:
            store.claim_turn(
                "conversation-2",
                "second-turn",
                instance_name="instance-a",
                project_key="PROJECT",
                owner_fingerprint="principal-a",
                kind="message",
                allow_edit_project=False,
                max_concurrent_turns=1,
            )
        assert "conversation-1" not in str(saturated.value)

        process.stdin.write("release\n")
        process.stdin.flush()
        process.wait(timeout=5)
        assert process.returncode == 0, process.stderr.read()

        lost = json.loads(
            run(
                cobuild.get_cobuild_turn_status(
                    "conversation-1",
                    "PROJECT",
                    DummyContext(),
                    "external-turn",
                )
            )
        )
        assert lost["status"] == "turn_lost"
        assert lost["error_kind"] == "transport_outcome_unknown"
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_overdue_running_turn_is_never_swept_or_unlocked(isolate_registry):
    conversation = isolate_registry[1].conversation
    conversation.send_release = threading.Event()
    start()
    entry, rehydrated = cobuild._resolve_conversation_entry(
        "conversation-1",
        "PROJECT",
        "instance-a",
        isolate_registry[1],
        "principal-a",
    )
    turn = cobuild._begin_turn(
        entry,
        isolate_registry[1],
        conversation_id="conversation-1",
        kind="message",
        allow_edit_project=True,
        rehydrated=rehydrated,
        message="keep running",
    )
    assert conversation.send_started.wait(timeout=2)
    turn.started_at -= cobuild.MAX_COBUILD_TIMEOUT_SECONDS + 1

    with cobuild._registry_lock:
        cobuild._sweep_settled_locked(time.monotonic())

    assert cobuild._turns["conversation-1"] is turn
    assert turn.claim.released is False
    assert cobuild._progress_payload(turn)["overdue"] is True
    with pytest.raises(cobuild._TurnAlreadyActive):
        cobuild._begin_turn(
            entry,
            isolate_registry[1],
            conversation_id="conversation-1",
            kind="message",
            allow_edit_project=True,
            rehydrated=False,
            message="must not overlap",
        )

    conversation.send_release.set()
    turn.future.result(timeout=2)
    cobuild._try_finalize(turn)
    assert turn.claim.released is True


def test_oversized_deletion_proposal_is_disarmed_not_truncated(
    isolate_registry,
    monkeypatch,
):
    monkeypatch.setattr(cobuild, "_MAX_PERSISTED_RESULT_BYTES", 1_000)
    conversation = isolate_registry[1].conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="must-not-be-approvable",
        objects_to_delete=[{"id": "x" * 10_000}],
        deletion_impacts={"detail": "y" * 10_000},
    )
    start()

    result = send(allow_edit_project=True)

    assert result["status"] == "error"
    assert result["error_kind"] == "confirmation_proposal_too_large"
    assert "confirmation_id" not in result
    assert conversation._pending_confirmation_id is None
    with pytest.raises(ValueError, match="No pending confirmation"):
        answer("must-not-be-approvable")
