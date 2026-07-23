"""Process-local retained-turn, edit opt-in, and deletion-consent contracts.

Everything here is single-process. There is no durable store, no cross-process
coordination, and no subprocess tests — a retained turn is a daemon thread plus
an in-memory Future, and a conversation is an in-memory handle.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
import threading
import time

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
        self.client = None
        self._pending_confirmation_id = None
        self.send_calls = []
        self.answer_calls = []
        self.next_send = FakeResponse()
        self.next_answer = FakeResponse(message="confirmed")
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
    def __init__(self, conversation=None):
        self.conversation = conversation or FakeConversation()
        self.requested_projects = []

    def get_project(self, project_key):
        self.requested_projects.append(project_key)
        return FakeProject(self.conversation)


@pytest.fixture(autouse=True)
def cobuild_env(monkeypatch):
    with cobuild._registry_lock:
        cobuild._conversations.clear()
        cobuild._turns.clear()
    client = FakeClient()
    state = {"instance": "instance-a"}
    monkeypatch.setattr(cobuild, "get_dss_client", lambda *a, **k: client)
    monkeypatch.setattr(config, "get_current_instance_name", lambda: state["instance"])
    # _capture_binding derives name AND client from one config.get_current_instance()
    # snapshot; return a fresh DSSInstance reflecting the current state so a test
    # can flip the active instance to exercise the ownership guard.
    monkeypatch.setattr(
        config,
        "get_current_instance",
        lambda: config.DSSInstance(
            name=state["instance"],
            url=f"https://{state['instance']}.invalid",
            api_key="test-key",
            no_check_certificate=False,
            source="test",
        ),
    )
    # A fresh capacity per test so one test's saturation can't leak into another.
    monkeypatch.setattr(
        cobuild,
        "_turn_semaphore",
        threading.BoundedSemaphore(cobuild.MAX_CONCURRENT_COBUILD_TURNS),
    )
    yield client, state
    # Drain any turn a test left in flight so daemon threads do not outlive it.
    with cobuild._registry_lock:
        turns = list(cobuild._turns.values())
    for turn in turns:
        release = getattr(turn.entry.conversation, "send_release", None)
        if release is not None:
            release.set()
        try:
            turn.future.result(timeout=2)
        except (concurrent.futures.TimeoutError, Exception):
            pass
        cobuild._settle_turn(turn)
    with cobuild._registry_lock:
        cobuild._conversations.clear()
        cobuild._turns.clear()


def run(coroutine):
    return asyncio.run(coroutine)


def start(project_key="PROJECT"):
    return json.loads(
        run(cobuild.start_cobuild_conversation(project_key, DummyContext()))
    )


def send(*, allow_edit_project=None, timeout_seconds=None):
    kwargs = {}
    if allow_edit_project is not None:
        kwargs["allow_edit_project"] = allow_edit_project
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
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


def poll(turn_id, *, project_key="PROJECT", conversation_id="conversation-1"):
    return json.loads(
        run(
            cobuild.get_cobuild_turn_status(
                conversation_id, project_key, DummyContext(), turn_id
            )
        )
    )


def list_conversations(project_key="PROJECT"):
    payload = json.loads(
        run(cobuild.list_cobuild_conversations(project_key, DummyContext()))
    )
    columns = payload["conversations"]["columns"]
    rows = [
        dict(zip(columns, row)) for row in payload["conversations"]["rows"]
    ]
    return payload, rows


class FreshConversationClient:
    """A client whose projects mint a new conversation per start call."""

    def __init__(self):
        self.conversations = []

    def get_project(self, project_key):
        outer = self

        class _Project:
            def new_cobuild_conversation(self):
                conversation = FakeConversation(f"conv-{len(outer.conversations)}")
                outer.conversations.append(conversation)
                return conversation

        return _Project()


# --------------------------------------------------------------------------- #
# Edit opt-in and deletion consent (least-privilege contract)
# --------------------------------------------------------------------------- #


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

    assert result["status"] == "needs_confirmation"
    assert result["confirmation_id"] == "confirm-123"
    assert result["objects_to_delete"] == [{"type": "DATASET", "id": "old_output"}]
    assert result["deletion_impacts"] == {"recipes": ["downstream"]}


def test_confirmation_without_sdk_id_fails_closed(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
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
    assert conversation._pending_confirmation_id is None


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
def test_needs_confirmation_then_answer_completes(cobuild_env, choice):
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="confirm-once",
    )
    start()
    proposal = send(allow_edit_project=True)
    assert proposal["status"] == "needs_confirmation"

    result = answer("confirm-once", choice)

    assert result["status"] == "completed"
    assert result["message"] == "confirmed"
    assert conversation.answer_calls == [
        {"choice": choice, "confirmation_id": "confirm-once", "client": client}
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

    result = answer("confirm-once")

    assert result["status"] == "error"
    assert result["error_kind"] == "transport_outcome_unknown"
    assert "after POST" in result["message"]
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

    payload, rows = list_conversations()
    rendered = json.dumps(payload)

    assert "never-list-this-token" not in rendered
    assert rows[0]["has_pending_confirmation"] is True
    # The listing exposes the latest turn and its coarse status for recovery,
    # but never the approval token itself.
    assert rows[0]["last_turn_status"] == "needs_confirmation"
    assert rows[0]["last_turn_id"]


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


# --------------------------------------------------------------------------- #
# Retained turns: capture-at-entry, timeout/poll, busy, capacity
# --------------------------------------------------------------------------- #


def test_get_cobuild_turn_status_is_a_registered_coroutine_tool():
    assert inspect.iscoroutinefunction(cobuild.get_cobuild_turn_status)
    assert "turn_id" in inspect.signature(cobuild.get_cobuild_turn_status).parameters


def test_turn_runs_with_the_client_captured_at_tool_entry(cobuild_env):
    client, _ = cobuild_env
    start()

    send(allow_edit_project=True)

    assert client.conversation.send_calls[-1]["client"] is client


def test_capture_binding_cannot_split_name_and_client_under_switch(monkeypatch):
    """A concurrent switch_instance between the two reads must not split the pair.

    Forced interleaving: reading the active instance flips the underlying registry
    to a *different* instance as a side effect (as a real switch_instance would,
    landing right after the snapshot is taken). Because _capture_binding derives
    both the name and the client from ONE get_current_instance() snapshot, the pair
    stays on instance A. A regression to two separate reads — name from A, then a
    no-arg get_dss_client() that re-reads the registry — would return a B client.
    """
    instance_a = config.DSSInstance(
        name="a", url="https://a.invalid", api_key="ka",
        no_check_certificate=False, source="test",
    )
    instance_b = config.DSSInstance(
        name="b", url="https://b.invalid", api_key="kb",
        no_check_certificate=False, source="test",
    )
    registry = {"current": instance_a}

    def racing_get_current_instance():
        # The switch lands immediately after this snapshot is captured.
        snapshot = registry["current"]
        registry["current"] = instance_b
        return snapshot

    def instance_aware_get_dss_client(instance=None):
        # A no-arg (regressed) call re-reads the now-flipped registry -> B.
        source = instance if instance is not None else registry["current"]
        return {"name": source.name, "url": source.url}

    monkeypatch.setattr(config, "get_current_instance", racing_get_current_instance)
    monkeypatch.setattr(cobuild, "get_dss_client", instance_aware_get_dss_client)

    name, client = cobuild._capture_binding()

    assert name == "a"
    assert client == {"name": "a", "url": "https://a.invalid"}


def test_timeout_returns_pollable_turn_and_worker_is_retained(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.send_release = threading.Event()  # worker blocks until released
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
    assert timed_out["conversation_id"] == "conversation-1"
    turn_id = timed_out["turn_id"]
    assert len(conversation.send_calls) == 1
    turn = cobuild._turns[turn_id]
    assert turn.thread.daemon is True
    # The wait timing out must not cancel the authoritative worker.
    assert turn.future.cancel() is False
    assert turn.future.cancelled() is False

    conversation.send_release.set()
    turn.future.result(timeout=2)
    completed = poll(turn_id)

    assert completed["status"] == "completed"
    assert completed["turn_id"] == turn_id
    assert len(conversation.send_calls) == 1  # never resent


def test_overlapping_send_is_busy_and_never_duplicates(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
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
    assert second["status"] == "busy"
    assert second["turn_id"] == first["turn_id"]
    assert [call["message"] for call in conversation.send_calls] == ["mutate once"]


def test_concurrent_approvals_are_serialized_and_only_one_can_win(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
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
    assert {payload["status"] for payload in payloads} == {"completed", "busy"}
    assert len({payload["turn_id"] for payload in payloads}) == 1


def test_global_capacity_saturation_refuses_a_new_turn(cobuild_env, monkeypatch):
    client, _ = cobuild_env
    monkeypatch.setattr(cobuild, "MAX_CONCURRENT_COBUILD_TURNS", 1)
    monkeypatch.setattr(cobuild, "_turn_semaphore", threading.BoundedSemaphore(1))
    conversation = client.conversation
    conversation.send_release = threading.Event()
    start()

    # Occupy the single global slot with one in-flight turn.
    first = send(allow_edit_project=True, timeout_seconds=1)
    assert first["status"] == "timeout"

    # A different conversation cannot get a slot: saturated, not busy.
    other = FakeConversation("conversation-2")
    with cobuild._registry_lock:
        cobuild._conversations["conversation-2"] = cobuild._CobuildConversationEntry(
            instance_name="instance-a",
            project_key="PROJECT",
            conversation=other,
            created_at="now",
        )
    saturated = json.loads(
        run(
            cobuild.send_cobuild_message(
                "conversation-2",
                "PROJECT",
                "no slot available",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=1,
            )
        )
    )

    assert saturated["status"] == "error"
    assert saturated["error_kind"] == "saturated"
    assert saturated["capacity"] == 1
    assert other.send_calls == []  # never started

    conversation.send_release.set()


def test_cancelling_the_client_wait_does_not_cancel_the_worker(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
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
        turn = next(iter(cobuild._turns.values()))
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert turn.future.cancelled() is False
        conversation.send_release.set()
        return turn

    turn = run(cancel_wait())
    turn.future.result(timeout=2)
    completed = poll(turn.turn_id)

    assert completed["status"] == "completed"
    assert len(conversation.send_calls) == 1


def test_cancelled_send_is_recoverable_via_public_surface_only(cobuild_env):
    """A real MCP client that never received the turn_id can still recover it.

    The client's wait is cancelled before the send returns, so the client holds
    NO reference to the turn. Recovery uses only public tools: list the
    conversations, read last_turn_id and its status, observe that a retry is
    refused as busy with that same id, then poll the latest turn to its real
    outcome. The mutation runs exactly once.
    """
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.send_release = threading.Event()
    start()

    async def scenario():
        waiting = asyncio.create_task(
            cobuild.send_cobuild_message(
                "conversation-1",
                "PROJECT",
                "mutate exactly once",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=5,
            )
        )
        while not conversation.send_started.is_set():
            await asyncio.sleep(0.005)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting

        # Recovery step 1: the listing exposes the orphaned turn.
        listing = json.loads(
            await cobuild.list_cobuild_conversations("PROJECT", DummyContext())
        )
        columns = listing["conversations"]["columns"]
        row = dict(zip(columns, listing["conversations"]["rows"][0]))
        assert row["last_turn_id"]
        assert row["last_turn_status"] == "in_progress"

        # Recovery step 2: a blind retry is refused as busy with the same id.
        retry = json.loads(
            await cobuild.send_cobuild_message(
                "conversation-1",
                "PROJECT",
                "mutate exactly once",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=1,
            )
        )
        assert retry["status"] == "busy"
        assert retry["turn_id"] == row["last_turn_id"]

        conversation.send_release.set()
        return row["last_turn_id"]

    recovered_turn_id = run(scenario())

    # Recovery step 3: poll the conversation's latest turn (no turn_id passed)
    # until it settles; the recovered id and the latest turn agree.
    deadline = time.monotonic() + 2
    while True:
        outcome = json.loads(
            run(
                cobuild.get_cobuild_turn_status(
                    "conversation-1", "PROJECT", DummyContext()
                )
            )
        )
        if outcome["status"] != "in_progress":
            break
        assert time.monotonic() < deadline, "turn never settled"
        time.sleep(0.01)

    assert outcome["status"] == "completed"
    assert outcome["turn_id"] == recovered_turn_id
    assert [call["message"] for call in conversation.send_calls] == [
        "mutate exactly once"
    ]

    # After settlement the orphaned turn stays discoverable in the listing.
    _payload, rows = list_conversations()
    assert rows[0]["last_turn_id"] == recovered_turn_id
    assert rows[0]["last_turn_status"] == "completed"


def test_waiter_settles_result_even_if_done_callback_is_delayed(
    cobuild_env, monkeypatch
):
    client, _ = cobuild_env
    start()
    monkeypatch.setattr(cobuild, "_on_turn_done", lambda *_a: None)

    first = send()
    second = send()

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert len(client.conversation.send_calls) == 2


def test_poll_rejects_unknown_and_mismatched_turn_id(cobuild_env):
    start()
    completed = send()
    turn_id = completed["turn_id"]
    assert turn_id

    with pytest.raises(ValueError, match="Unknown Cobuild turn_id"):
        poll("not-a-real-turn")

    with pytest.raises(ValueError, match="does not match"):
        poll(turn_id, project_key="OTHER")

    polled = poll(turn_id)
    assert polled["status"] == "completed"
    assert polled["turn_id"] == turn_id


# --------------------------------------------------------------------------- #
# Terminal payload bound (flat check in the worker; disarm, never truncate a
# deletion proposal)
# --------------------------------------------------------------------------- #


def test_oversized_deletion_proposal_is_disarmed_not_truncated(
    cobuild_env, monkeypatch
):
    monkeypatch.setattr(cobuild, "_MAX_TERMINAL_RESULT_BYTES", 1_000)
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="must-not-be-approvable",
        objects_to_delete=[{"id": "x" * 10_000}],
        deletion_impacts={"detail": "y" * 10_000},
    )
    start()

    result = send(allow_edit_project=True)

    assert result["status"] == "error"
    assert result["error_kind"] == "response_too_large"
    assert result["cancelled_confirmation"] is True
    assert "confirmation_id" not in result
    assert conversation._pending_confirmation_id is None
    with pytest.raises(ValueError, match="No pending confirmation"):
        answer("must-not-be-approvable")


def test_oversized_completed_response_is_clipped_with_metadata(
    cobuild_env, monkeypatch
):
    monkeypatch.setattr(cobuild, "_MAX_TERMINAL_RESULT_BYTES", 1_000)
    client, _ = cobuild_env
    client.conversation.next_send = FakeResponse(message="z" * 10_000)
    start()

    result = send()

    assert result["status"] == "error"
    assert result["error_kind"] == "response_too_large"
    assert result["truncated"] is True
    assert result["original_bytes"] > 1_000
    assert len(result["message"]) <= cobuild._TRUNCATED_MESSAGE_CHARS
    assert "cancelled_confirmation" not in result


def test_oversized_result_is_bounded_before_retention(cobuild_env, monkeypatch):
    # The bound is applied in the worker thread, before the payload is retained,
    # so the registry never stores the oversized original and a later poll
    # returns the same bounded payload.
    monkeypatch.setattr(cobuild, "_MAX_TERMINAL_RESULT_BYTES", 1_000)
    client, _ = cobuild_env
    client.conversation.next_send = FakeResponse(message="z" * 10_000)
    start()

    result = send()
    turn_id = result["turn_id"]

    retained = cobuild._turns[turn_id].result_payload
    assert retained["error_kind"] == "response_too_large"
    # The retained payload is the bounded one (clipped message plus metadata),
    # never the 10 KB original.
    assert cobuild._json_size(retained) < 4_000
    assert poll(turn_id)["error_kind"] == "response_too_large"


# --------------------------------------------------------------------------- #
# Process-local lifecycle and sweep
# --------------------------------------------------------------------------- #


def test_conversation_is_process_local_and_lost_on_restart(cobuild_env):
    start()
    assert send()["status"] == "completed"

    # Simulate a server restart: process-local state is gone.
    with cobuild._registry_lock:
        cobuild._conversations.clear()
        cobuild._turns.clear()

    with pytest.raises(ValueError, match="Unknown Cobuild conversation_id"):
        send()


def test_overdue_running_turn_is_never_swept(cobuild_env):
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.send_release = threading.Event()
    start()

    entry = cobuild._resolve_conversation_entry(
        "conversation-1", "PROJECT", "instance-a"
    )
    turn = cobuild._begin_turn(
        entry,
        client,
        conversation_id="conversation-1",
        kind="message",
        allow_edit_project=True,
        message="keep running",
    )
    assert conversation.send_started.wait(timeout=2)
    turn.started_at -= cobuild.MAX_COBUILD_TIMEOUT_SECONDS + 1

    with cobuild._registry_lock:
        cobuild._sweep_settled_locked(time.monotonic())

    assert cobuild._turns[turn.turn_id] is turn
    assert entry.active_turn_id == turn.turn_id
    assert cobuild._progress_payload(turn, status="in_progress")["overdue"] is True
    with pytest.raises(cobuild._TurnAlreadyActive):
        cobuild._begin_turn(
            entry,
            client,
            conversation_id="conversation-1",
            kind="message",
            allow_edit_project=True,
            message="must not overlap",
        )

    conversation.send_release.set()
    turn.future.result(timeout=2)
    cobuild._settle_turn(turn)
    assert turn.semaphore_released is True
    assert entry.active_turn_id is None


def _make_settled_turn(turn_id, *, settled_ago, created_at="2026-01-01T00:00:00+00:00"):
    """Build a synthetic already-settled turn for retention-sweep tests."""
    entry = cobuild._CobuildConversationEntry(
        instance_name="instance-a",
        project_key="PROJECT",
        conversation=FakeConversation(f"conv-{turn_id}"),
        created_at=created_at,
    )
    future: concurrent.futures.Future = concurrent.futures.Future()
    future.set_result({"status": "completed"})
    turn = cobuild._RetainedTurn(
        turn_id=turn_id,
        conversation_id=f"conv-{turn_id}",
        project_key="PROJECT",
        instance_name="instance-a",
        kind="message",
        allow_edit_project=False,
        entry=entry,
        client=None,
        future=future,
        started_at=0.0,
    )
    turn.result_payload = {"status": "completed"}
    turn.settled_at = time.monotonic() - settled_ago
    turn.semaphore_released = True
    return turn


def test_sweep_evicts_expired_and_over_cap_settled_turns(cobuild_env):
    with cobuild._registry_lock:
        cobuild._turns.clear()
        cobuild._turns["expired"] = _make_settled_turn(
            "expired", settled_ago=cobuild._SETTLED_TURN_TTL_SECONDS + 10
        )
        for i in range(cobuild._MAX_SETTLED_TURNS + 2):
            cobuild._turns[f"t{i}"] = _make_settled_turn(f"t{i}", settled_ago=i)
        cobuild._sweep_settled_locked(time.monotonic())
        remaining = set(cobuild._turns)

    # TTL-expired turns are gone and the count cap is enforced.
    assert "expired" not in remaining
    assert len(remaining) == cobuild._MAX_SETTLED_TURNS


def test_settlement_sweeps_expired_settled_turns(cobuild_env):
    # A settled turn beyond the TTL must be swept when the next turn settles, not
    # only when a new turn starts.
    with cobuild._registry_lock:
        cobuild._turns["expired"] = _make_settled_turn(
            "expired", settled_ago=cobuild._SETTLED_TURN_TTL_SECONDS + 10
        )
    start()
    result = send(allow_edit_project=True)  # runs to completion -> settles -> sweeps

    assert result["status"] == "completed"
    with cobuild._registry_lock:
        assert "expired" not in cobuild._turns


def _seed_idle_conversations(count, *, armed_index=None):
    cobuild._conversations.clear()
    for i in range(count):
        conversation = FakeConversation(f"conv-{i}")
        if armed_index is not None and i == armed_index:
            conversation._pending_confirmation_id = "armed"
        cobuild._conversations[f"conv-{i}"] = cobuild._CobuildConversationEntry(
            instance_name="instance-a",
            project_key="PROJECT",
            conversation=conversation,
            created_at=f"2026-01-01T00:00:00.{i:04d}+00:00",
        )


def test_idle_conversations_are_evicted_oldest_first_beyond_cap(cobuild_env):
    with cobuild._registry_lock:
        _seed_idle_conversations(cobuild._MAX_CONVERSATIONS + 5)
        cobuild._evict_conversations_locked()
        remaining = set(cobuild._conversations)

    assert len(remaining) == cobuild._MAX_CONVERSATIONS
    assert "conv-0" not in remaining  # oldest evicted
    assert f"conv-{cobuild._MAX_CONVERSATIONS + 4}" in remaining  # newest kept


def test_eviction_never_drops_a_conversation_with_pending_confirmation(cobuild_env):
    with cobuild._registry_lock:
        _seed_idle_conversations(cobuild._MAX_CONVERSATIONS + 1, armed_index=0)
        cobuild._evict_conversations_locked()
        remaining = set(cobuild._conversations)

    # The armed oldest conversation is protected; the next-oldest idle one goes.
    assert "conv-0" in remaining
    assert "conv-1" not in remaining
    assert len(remaining) == cobuild._MAX_CONVERSATIONS


def test_sweep_never_evicts_an_armed_deletion_proposal(cobuild_env):
    """An armed needs_confirmation turn survives TTL and count sweeps.

    While the proposal is armed, its settled turn is the only place the exact
    confirmation_id (with objects_to_delete and deletion_impacts) can be
    re-read, so the sweep pins it: neither the TTL nor 64+ newer settled turns
    can evict it, and it stays pollable and answerable. Once answered it
    becomes an ordinary settled turn and is sweepable again.
    """
    client, _ = cobuild_env
    conversation = client.conversation
    conversation.next_send = FakeResponse(
        response_type="delete_confirmation_request",
        confirmation_id="keep-me-armed",
        objects_to_delete=[{"type": "DATASET", "id": "old_output"}],
    )
    start()
    proposal = send(allow_edit_project=True)
    assert proposal["status"] == "needs_confirmation"
    proposal_turn_id = proposal["turn_id"]

    with cobuild._registry_lock:
        # Age the armed proposal past the TTL and crowd it with 64+ newer
        # settled turns, then sweep.
        cobuild._turns[proposal_turn_id].settled_at = time.monotonic() - (
            cobuild._SETTLED_TURN_TTL_SECONDS + 100
        )
        for i in range(cobuild._MAX_SETTLED_TURNS + 5):
            cobuild._turns[f"t{i}"] = _make_settled_turn(f"t{i}", settled_ago=i)
        cobuild._sweep_settled_locked(time.monotonic())

    # The armed proposal survived; its exact id is still retrievable...
    revisited = poll(proposal_turn_id)
    assert revisited["status"] == "needs_confirmation"
    assert revisited["confirmation_id"] == "keep-me-armed"

    # ...and still answerable.
    result = answer("keep-me-armed")
    assert result["status"] == "completed"

    # Once answered, the proposal turn is no longer pinned and sweeps normally.
    # (The answer's own settlement sweep may already have evicted the aged turn.)
    with cobuild._registry_lock:
        lingering = cobuild._turns.get(proposal_turn_id)
        if lingering is not None:
            lingering.settled_at = time.monotonic() - (
                cobuild._SETTLED_TURN_TTL_SECONDS + 100
            )
            cobuild._sweep_settled_locked(time.monotonic())
        assert proposal_turn_id not in cobuild._turns


# --------------------------------------------------------------------------- #
# Conversation registry cap on the public path
# --------------------------------------------------------------------------- #


def test_conversation_cap_is_enforced_by_start_tool(cobuild_env, monkeypatch):
    factory = FreshConversationClient()
    monkeypatch.setattr(cobuild, "get_dss_client", lambda *a, **k: factory)

    for _ in range(cobuild._MAX_CONVERSATIONS + 1):
        run(cobuild.start_cobuild_conversation("PROJECT", DummyContext()))

    with cobuild._registry_lock:
        remaining = set(cobuild._conversations)
    assert len(remaining) == cobuild._MAX_CONVERSATIONS
    assert "conv-0" not in remaining  # oldest idle conversation evicted
    assert f"conv-{cobuild._MAX_CONVERSATIONS}" in remaining  # newest kept


def test_start_refuses_when_no_conversation_is_evictable(cobuild_env, monkeypatch):
    monkeypatch.setattr(cobuild, "_MAX_CONVERSATIONS", 2)
    factory = FreshConversationClient()
    monkeypatch.setattr(cobuild, "get_dss_client", lambda *a, **k: factory)

    for _ in range(2):
        run(cobuild.start_cobuild_conversation("PROJECT", DummyContext()))
    # Arm both retained conversations: nothing is evictable now.
    for conversation in factory.conversations:
        conversation._pending_confirmation_id = "armed"

    with pytest.raises(ValueError, match="registry is full"):
        run(cobuild.start_cobuild_conversation("PROJECT", DummyContext()))

    with cobuild._registry_lock:
        assert len(cobuild._conversations) == 2  # nothing was dropped


def test_sending_on_oldest_conversation_does_not_evict_it_mid_use(
    cobuild_env, monkeypatch
):
    """Admitting a new conversation mid-turn evicts an idle entry, never the
    conversation whose turn is in flight, even when it is the oldest."""
    monkeypatch.setattr(cobuild, "_MAX_CONVERSATIONS", 2)
    factory = FreshConversationClient()
    monkeypatch.setattr(cobuild, "get_dss_client", lambda *a, **k: factory)

    run(cobuild.start_cobuild_conversation("PROJECT", DummyContext()))
    run(cobuild.start_cobuild_conversation("PROJECT", DummyContext()))
    oldest = factory.conversations[0]
    oldest.send_release = threading.Event()

    async def scenario():
        waiting = asyncio.create_task(
            cobuild.send_cobuild_message(
                "conv-0",
                "PROJECT",
                "use the oldest conversation",
                DummyContext(),
                allow_edit_project=True,
                timeout_seconds=5,
            )
        )
        while not oldest.send_started.is_set():
            await asyncio.sleep(0.005)
        # A third conversation is admitted while conv-0's turn is in flight:
        # the idle conv-1 must be evicted, never the in-use conv-0.
        await cobuild.start_cobuild_conversation("PROJECT", DummyContext())
        oldest.send_release.set()
        return json.loads(await waiting)

    result = run(scenario())

    assert result["status"] == "completed"
    with cobuild._registry_lock:
        remaining = set(cobuild._conversations)
    assert "conv-0" in remaining  # in-use conversation kept
    assert "conv-1" not in remaining  # idle one evicted instead
    assert "conv-2" in remaining
    assert [call["message"] for call in oldest.send_calls] == [
        "use the oldest conversation"
    ]
