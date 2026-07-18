"""Tests for the Cobuild conversation tools.

These never touch the network: ``get_dss_client`` is replaced by a fake client
whose ``_perform_json`` returns canned raw dicts, so the *real*
``DSSCobuildConversation`` SDK object drives the turn (exercising its actual
confirmation-id plumbing) against a fake backend. The durable store is pointed
at a per-test ``tmp_path`` via ``DKU_MCP_STATE_DIR``.
"""

import asyncio
import concurrent.futures
import contextvars
import inspect
import json
import stat
import threading
import time

import pytest
import requests

from dataikuapi.dss.cobuild import DSSCobuildConversation
from dataikuapi.utils import DataikuException
from dataiku_mcp.tools import cobuild


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeBackend:
    """Records DSS POSTs and answers Cobuild turns from a queue.

    ``gate`` (a ``threading.Event``) lets a test hold a turn open to exercise the
    timeout / overlap paths; conversation creation never waits on it.
    """

    def __init__(self, conversation_id="conv-1"):
        self.conversation_id = conversation_id
        self.turn_responses = []
        self.calls = []
        self.gate = None

    def perform(self, method, path, body=None):
        self.calls.append((method, path, dict(body or {})))
        if path.endswith("/cobuild/conversations"):
            return {"conversationId": self.conversation_id}
        if self.gate is not None:
            self.gate.wait()
        if not self.turn_responses:
            raise AssertionError(f"No queued Cobuild response for {path}")
        item = self.turn_responses.pop(0)
        # A queued exception simulates a transport/DSS failure on the turn POST.
        if isinstance(item, BaseException):
            raise item
        return item


class FakeProject:
    def __init__(self, client, key):
        self.client = client
        self.project_key = key

    def new_cobuild_conversation(self):
        # Mirrors dataikuapi.dss.project.DSSProject.new_cobuild_conversation.
        raw = self.client._perform_json(
            "POST", f"/projects/{self.project_key}/cobuild/conversations", body={}
        )
        return DSSCobuildConversation(self.client, self.project_key, raw["conversationId"])


class FakeClient:
    def __init__(self, backend):
        self._backend = backend

    def _perform_json(self, method, path, body=None):
        return self._backend.perform(method, path, body)

    def get_project(self, key):
        return FakeProject(self, key)


class FakeCtx:
    def __init__(self):
        self.infos = []
        self.progress = []

    async def info(self, message, **kwargs):
        self.infos.append(message)

    async def report_progress(self, progress=None, total=None, message=None):
        self.progress.append((progress, total))


# --------------------------------------------------------------------------- #
# Raw response builders + helpers
# --------------------------------------------------------------------------- #


def assistant(message):
    return {"type": "assistant_message", "message": message}


def confirmation(message, confirmation_id, objects, impacts):
    return {
        "type": "delete_confirmation_request",
        "message": message,
        "confirmationId": confirmation_id,
        "objectsToDelete": objects,
        "deletionImpacts": impacts,
    }


def error_response(message):
    return {"type": "error", "error": True, "message": message}


def run(coro):
    return asyncio.run(coro)


def last_message_body(backend):
    for _method, path, body in reversed(backend.calls):
        if path.endswith("/messages"):
            return body
    raise AssertionError("no /messages POST recorded")


def start(project_key="PROJ"):
    return json.loads(run(cobuild.start_cobuild_conversation(project_key, FakeCtx())))[
        "conversation_id"
    ]


def send(cid, message, project_key="PROJ", **kwargs):
    return json.loads(
        run(cobuild.send_cobuild_message(cid, project_key, message, FakeCtx(), **kwargs))
    )


def answer(cid, choice, confirmation_id, project_key="PROJ", **kwargs):
    # confirmation_id is a required argument on the tool (proof-of-inspection).
    return json.loads(
        run(
            cobuild.answer_cobuild_confirmation(
                cid, project_key, choice, confirmation_id, FakeCtx(), **kwargs
            )
        )
    )


def poll_status(cid, project_key="PROJ", tries=200):
    for _ in range(tries):
        res = json.loads(
            run(cobuild.get_cobuild_turn_status(cid, project_key, FakeCtx()))
        )
        if res["status"] != "in_progress":
            return res
        time.sleep(0.02)
    raise AssertionError("turn did not settle")


def read_store(env):
    return json.loads((env.tmp_path / "conversations.json").read_text())


# --------------------------------------------------------------------------- #
# Fixture
# --------------------------------------------------------------------------- #


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DKU_MCP_STATE_DIR", str(tmp_path))
    holder = {"instance": "inst-a"}

    def _fake_instance():
        from dataiku_mcp import config

        return config.DSSInstance(
            name=holder["instance"],
            url="http://fake-dss",
            api_key="fake-key",
            no_check_certificate=False,
            source="test",
        )

    monkeypatch.setattr(
        "dataiku_mcp.config.get_current_instance_name", lambda: holder["instance"]
    )
    # The tools snapshot the instance object at entry (_resolve_client_and_instance).
    monkeypatch.setattr(
        "dataiku_mcp.config.get_current_instance", _fake_instance
    )
    cobuild._conversations.clear()
    cobuild._in_flight.clear()

    class _Env:
        def __init__(self):
            self.tmp_path = tmp_path

        def set_client(self, backend):
            # get_dss_client is now called with the captured instance snapshot.
            monkeypatch.setattr(
                cobuild, "get_dss_client", lambda *a, **k: FakeClient(backend)
            )

        def set_instance(self, name):
            holder["instance"] = name

    e = _Env()
    yield e
    cobuild._conversations.clear()
    cobuild._in_flight.clear()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_allow_edit_project_defaults_to_false(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    backend.turn_responses = [assistant("inspected")]
    send(cid, "what datasets are here?")
    assert last_message_body(backend)["allowEditProject"] is False

    backend.turn_responses = [assistant("built")]
    send(cid, "build the recipe", allow_edit_project=True)
    assert last_message_body(backend)["allowEditProject"] is True

    default = inspect.signature(cobuild.send_cobuild_message).parameters[
        "allow_edit_project"
    ].default
    assert default is False


def test_confirmation_id_surfaced_and_persisted(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    obj = {"projectKey": "PROJ", "type": "DATASET", "id": "orders", "displayName": "orders"}
    backend.turn_responses = [
        confirmation("Delete orders?", "cid-9", [obj], {"recipes": ["compute_orders"]})
    ]
    res = send(cid, "delete the orders dataset")

    assert res["status"] == "needs_confirmation"
    assert res["confirmation_id"] == "cid-9"
    assert res["objects_to_delete"] == [obj]
    assert res["deletion_impacts"] == {"recipes": ["compute_orders"]}

    assert read_store(env)[cid]["pending_confirmation_id"] == "cid-9"


def test_rehydration_after_simulated_restart(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    backend.turn_responses = [assistant("first")]
    send(cid, "hello")

    # Simulate a restart: drop the in-memory hot cache, keep the store file.
    cobuild._conversations.clear()
    cobuild._in_flight.clear()

    backend.turn_responses = [assistant("after restart")]
    res = send(cid, "still there?")

    assert res["status"] == "completed"
    assert res["message"] == "after restart"
    assert res.get("rehydrated") is True


def test_answer_confirmation_with_explicit_id_post_restart(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    obj = {"projectKey": "PROJ", "type": "DATASET", "id": "tmp", "displayName": "tmp"}
    backend.turn_responses = [confirmation("Delete tmp?", "cid-42", [obj], {})]
    send(cid, "delete tmp")

    cobuild._conversations.clear()
    cobuild._in_flight.clear()

    backend.turn_responses = [assistant("deleted tmp")]
    res = answer(cid, "APPROVE", "cid-42")

    assert res["status"] == "completed"
    assert res.get("rehydrated") is True
    assert any("/confirmation/cid-42" in path for _m, path, _b in backend.calls)
    assert read_store(env)[cid]["pending_confirmation_id"] is None


def test_answer_confirmation_restores_pending_from_store(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    obj = {"projectKey": "PROJ", "type": "DATASET", "id": "old", "displayName": "old"}
    backend.turn_responses = [confirmation("Delete old?", "cid-77", [obj], {})]
    send(cid, "delete old")

    cobuild._conversations.clear()
    cobuild._in_flight.clear()

    backend.turn_responses = [assistant("deleted old")]
    # confirmation_id is required, but after a restart the live handle is empty;
    # it must be validated/restored against the durable store.
    res = answer(cid, "APPROVE", "cid-77")

    assert res["status"] == "completed"
    assert any("/confirmation/cid-77" in path for _m, path, _b in backend.calls)


def test_timeout_retains_turn_and_status_settles(env):
    backend = FakeBackend()
    gate = threading.Event()
    backend.gate = gate
    backend.turn_responses = [assistant("done building")]
    env.set_client(backend)
    cid = start()

    res = send(cid, "a long build", timeout_seconds=1)
    assert res["status"] == "timeout"
    assert "get_cobuild_turn_status" in res["next_action"]
    assert cid in cobuild._in_flight  # future retained, not dropped

    gate.set()
    settled = poll_status(cid)
    assert settled["status"] == "completed"
    assert settled["message"] == "done building"
    assert cid not in cobuild._in_flight


def test_overlap_guard_does_not_double_send(env):
    backend = FakeBackend()
    gate = threading.Event()
    backend.gate = gate
    backend.turn_responses = [assistant("finished")]
    env.set_client(backend)
    cid = start()

    first = send(cid, "build one", timeout_seconds=1)
    assert first["status"] == "timeout"
    calls_before = len(backend.calls)

    second = send(cid, "build two", timeout_seconds=1)
    assert second["status"] == "in_progress"
    assert len(backend.calls) == calls_before  # no second turn POST

    gate.set()
    poll_status(cid)
    message_posts = [c for c in backend.calls if c[1].endswith("/messages")]
    assert len(message_posts) == 1


def test_instance_mismatch_guard(env):
    backend = FakeBackend()
    backend.turn_responses = [assistant("ok")]
    env.set_client(backend)
    cid = start()

    env.set_instance("inst-b")
    with pytest.raises(ValueError, match="belongs to instance"):
        send(cid, "hi")

    # Same guard on the rehydration path (in-memory cache cleared).
    cobuild._conversations.clear()
    with pytest.raises(ValueError, match="belongs to instance"):
        send(cid, "hi")


def test_project_mismatch_guard(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    with pytest.raises(ValueError, match="belongs to project"):
        send(cid, "hi", project_key="OTHER")


def test_store_write_is_atomic_and_0600(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    store_file = env.tmp_path / "conversations.json"
    assert store_file.exists()
    assert stat.S_IMODE(store_file.stat().st_mode) == 0o600

    record = read_store(env)[cid]
    assert record["project_key"] == "PROJ"
    assert record["instance_name"] == "inst-a"
    assert record["pending_confirmation_id"] is None
    assert "created_at" in record

    # Atomic write leaves no partial temp files behind.
    assert list(env.tmp_path.glob(".conversations-*.tmp")) == []


def test_fail_closed_on_unknown_response_type(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    backend.turn_responses = [{"type": "some_future_type", "message": "hmm"}]
    res = send(cid, "do a thing")
    assert res["status"] == "error"
    assert "some_future_type" in res["message"]

    backend.turn_responses = [{"message": "no type field"}]
    res2 = send(cid, "do another thing")
    assert res2["status"] == "error"


def test_permission_error_hints_retry_with_allow_edit(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    backend.turn_responses = [error_response("Permission denied: cannot edit project")]
    res = send(cid, "build a recipe")  # allow_edit_project defaults to False
    assert res["status"] == "error"
    assert "allow_edit_project=true" in res["next_action"]


def test_list_survives_restart_from_store(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    cobuild._conversations.clear()  # nothing in memory anymore
    listed = json.loads(run(cobuild.list_cobuild_conversations("PROJ", FakeCtx())))
    table = listed["conversations"]
    assert cid in [row[0] for row in table["rows"]]


# --------------------------------------------------------------------------- #
# Finding 1: confirmation_id is required proof-of-inspection
# --------------------------------------------------------------------------- #


OBJ = {"projectKey": "PROJ", "type": "DATASET", "id": "x", "displayName": "x"}


def test_confirmation_id_is_required_argument():
    # confirmation_id is a required positional on the tool signature (no default).
    param = inspect.signature(cobuild.answer_cobuild_confirmation).parameters[
        "confirmation_id"
    ]
    assert param.default is inspect.Parameter.empty


def test_confirmation_id_rejected_when_empty(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    backend.turn_responses = [confirmation("Delete x?", "cid-1", [OBJ], {})]
    send(cid, "delete x")

    with pytest.raises(ValueError, match="confirmation_id"):
        answer(cid, "APPROVE", "")


def test_stale_confirmation_id_cannot_approve_different_deletion(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    # The live pending confirmation is cid-NEW.
    backend.turn_responses = [confirmation("Delete new?", "cid-NEW", [OBJ], {})]
    send(cid, "delete the new dataset")

    # Caller passes a STALE id from some earlier confirmation.
    with pytest.raises(ValueError, match="does not match"):
        answer(cid, "APPROVE", "cid-STALE")

    # Nothing was approved: no POST to the confirmation endpoint.
    assert not any("/confirmation/" in path for _m, path, _b in backend.calls)
    # The live pending id is untouched.
    entry = cobuild._get_live(cid)
    assert entry.conversation._pending_confirmation_id == "cid-NEW"


def test_matching_confirmation_id_approves(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    backend.turn_responses = [confirmation("Delete x?", "cid-9", [OBJ], {})]
    send(cid, "delete x")

    backend.turn_responses = [assistant("deleted x")]
    res = answer(cid, "APPROVE", "cid-9")
    assert res["status"] == "completed"
    assert any("/confirmation/cid-9" in path for _m, path, _b in backend.calls)


# --------------------------------------------------------------------------- #
# Finding 2: request-scoped ContextVars survive the thread boundary
# --------------------------------------------------------------------------- #


def test_run_blocking_propagates_contextvars():
    marker = contextvars.ContextVar("cobuild_marker", default="unset")
    marker.set("request-scoped")

    async def go():
        return await cobuild.run_blocking(marker.get)

    # run_in_executor threads do NOT inherit ContextVars unless we copy+run.
    assert run(go()) == "request-scoped"


def test_spawn_blocking_propagates_contextvars():
    marker = contextvars.ContextVar("cobuild_marker2", default="unset")
    marker.set("bearer-token")

    future = cobuild._spawn_blocking(marker.get)
    # The daemon-thread turn must see the caller's request-scoped context.
    assert future.result(timeout=5) == "bearer-token"


# --------------------------------------------------------------------------- #
# Finding 3: switch_instance never retargets an in-flight turn
# --------------------------------------------------------------------------- #


def test_switch_instance_does_not_retarget_in_flight_turn(env):
    backend_a = FakeBackend()
    gate = threading.Event()
    backend_a.gate = gate
    backend_a.turn_responses = [assistant("built on A")]
    env.set_client(backend_a)
    cid = start()  # created on inst-a

    res = send(cid, "a long build", timeout_seconds=1)
    assert res["status"] == "timeout"

    # Switch the active instance and repoint the client factory mid-flight.
    backend_b = FakeBackend(conversation_id="conv-B")
    backend_b.turn_responses = [assistant("built on B")]
    env.set_instance("inst-b")
    env.set_client(backend_b)

    gate.set()
    # Polling now verifies instance ownership, so switch back to the conversation's
    # original instance to settle it (per the documented switch-back requirement);
    # the turn itself already ran against the entry-time backend_a.
    env.set_instance("inst-a")
    settled = poll_status(cid)
    assert settled["status"] == "completed"
    assert settled["message"] == "built on A"
    assert settled["instance_name"] == "inst-a"
    # The turn targeted the entry-time backend, never the post-switch one.
    assert any(path.endswith("/messages") for _m, path, _b in backend_a.calls)
    assert not any(path.endswith("/messages") for _m, path, _b in backend_b.calls)


# --------------------------------------------------------------------------- #
# Finding 4: settled/lost turn outcomes are persisted honestly
# --------------------------------------------------------------------------- #


def _wait_store_terminal(env, cid, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rec = read_store(env).get(cid, {})
        if rec.get("last_result_status") not in (None, "in_flight"):
            return rec
        time.sleep(0.02)
    raise AssertionError("terminal outcome was not persisted to the store")


def test_settled_turn_outcome_persisted_and_reported_from_store(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    backend.turn_responses = [confirmation("Delete x?", "cid-x", [OBJ], {})]
    res = send(cid, "delete x")
    assert res["status"] == "needs_confirmation"

    # last_result_status is only ever written by the done-callback, so seeing a
    # terminal value proves the callback persisted the outcome (not a poll).
    rec = _wait_store_terminal(env, cid)
    assert rec["last_result_status"] == "needs_confirmation"
    assert rec["pending_confirmation_id"] == "cid-x"

    # Simulate the retained turn being swept/lost, then poll: the store answers.
    cobuild._in_flight.clear()
    reported = json.loads(run(cobuild.get_cobuild_turn_status(cid, "PROJ", FakeCtx())))
    assert reported["status"] == "needs_confirmation"
    assert reported["confirmation_id"] == "cid-x"


def test_turn_lost_reported_after_restart(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    # A turn was in flight when the process died: the marker is persisted but no
    # terminal callback ever ran (the daemon thread did not survive).
    cobuild._store().mark_in_flight(cid)
    cobuild._conversations.clear()
    cobuild._in_flight.clear()

    res = json.loads(run(cobuild.get_cobuild_turn_status(cid, "PROJ", FakeCtx())))
    assert res["status"] == "turn_lost"
    assert "restart" in res["message"].lower()
    assert "inspect" in res["next_action"].lower()


# --------------------------------------------------------------------------- #
# Finding 5: retained turns are bounded (cap + TTL sweep)
# --------------------------------------------------------------------------- #


def _pending_turn(cid):
    future = concurrent.futures.Future()
    future.set_running_or_notify_cancel()
    return cobuild._InFlightTurn(
        future=future,
        conversation_id=cid,
        project_key="PROJ",
        instance_name="inst-a",
        handle=object(),
        started_at=time.monotonic(),
        kind="send",
        allow_edit_project=False,
    )


def test_saturation_cap_blocks_new_turn(env, monkeypatch):
    monkeypatch.setattr(cobuild, "MAX_CONCURRENT_COBUILD_TURNS", 2)
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    # Two other conversations with never-settling turns saturate the cap.
    cobuild._in_flight["busy-1"] = _pending_turn("busy-1")
    cobuild._in_flight["busy-2"] = _pending_turn("busy-2")

    backend.turn_responses = [assistant("should not run")]
    res = send(cid, "please build")
    assert res["status"] == "error"
    assert res["error_kind"] == "saturated"
    assert "busy-1" in res["message"]
    assert "busy-2" in res["message"]
    # The new turn was never sent.
    assert not any(path.endswith("/messages") for _m, path, _b in backend.calls)


def test_sweep_evicts_expired_settled_turns(env):
    future = concurrent.futures.Future()
    future.set_result(None)
    turn = _pending_turn("old")
    turn.future = future
    cobuild._in_flight["old"] = turn

    # First sweep stamps settled_at but retains (within TTL).
    with cobuild._lock:
        cobuild._sweep_in_flight()
    assert "old" in cobuild._in_flight
    assert turn.settled_at is not None

    # Backdate beyond the TTL: the next sweep evicts it.
    turn.settled_at = time.monotonic() - cobuild.RETAINED_TURN_TTL_SECONDS - 1
    with cobuild._lock:
        cobuild._sweep_in_flight()
    assert "old" not in cobuild._in_flight


# --------------------------------------------------------------------------- #
# Finding 7: transport failures are outcome-unknown, DSS errors are definitive
# --------------------------------------------------------------------------- #


def test_transport_failure_marks_outcome_unknown(env):
    backend = FakeBackend()
    backend.turn_responses = [requests.exceptions.ConnectionError("Connection refused")]
    env.set_client(backend)
    cid = start()

    res = send(cid, "build something")
    assert res["status"] == "error"
    assert res["error_kind"] == "transport_outcome_unknown"
    assert "not" in res["next_action"].lower()  # "do NOT blindly resend"


def test_dss_definitive_error_is_not_outcome_unknown(env):
    backend = FakeBackend()
    backend.turn_responses = [DataikuException("PermissionError: forbidden (403)")]
    env.set_client(backend)
    cid = start()

    res = send(cid, "build something")
    assert res["status"] == "error"
    # A real DSS response is definitive: no transport_outcome_unknown marker.
    assert res.get("error_kind") != "transport_outcome_unknown"


# --------------------------------------------------------------------------- #
# Wave-2 Finding 11: a DataikuException carrying a 5xx is outcome-unknown
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    ["Internal Server Error (500)", "DSS error: 503 Service Unavailable", "boom 502"],
)
def test_dss_5xx_error_is_outcome_unknown(env, text):
    backend = FakeBackend()
    backend.turn_responses = [DataikuException(text)]
    env.set_client(backend)
    cid = start()

    res = send(cid, "build something")
    assert res["status"] == "error"
    # A 5xx may have mutated state before failing → treat the outcome as unknown.
    assert res["error_kind"] == "transport_outcome_unknown"


def test_dss_unclassifiable_error_stays_definitive(env):
    backend = FakeBackend()
    # No transport signature, no 5xx: a structured DSS error stays definitive.
    backend.turn_responses = [DataikuException("Recipe validation failed: bad SQL")]
    env.set_client(backend)
    cid = start()

    res = send(cid, "build something")
    assert res["status"] == "error"
    assert res.get("error_kind") != "transport_outcome_unknown"


# --------------------------------------------------------------------------- #
# Wave-2 Finding 1: only the single authoritative pending id can be approved
# --------------------------------------------------------------------------- #


def test_stale_store_pending_cannot_override_live(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    # The live handle holds cid-NEW (the deletion the caller actually saw).
    backend.turn_responses = [confirmation("Delete new?", "cid-NEW", [OBJ], {})]
    send(cid, "delete the new dataset")

    # Corrupt the durable store to hold a DIVERGENT, stale id.
    cobuild._store().set_pending_confirmation(cid, "cid-STALE")
    entry = cobuild._get_live(cid)
    assert entry.conversation._pending_confirmation_id == "cid-NEW"

    # The stale store id must NOT be accepted (no union with the live id).
    with pytest.raises(ValueError, match="does not match"):
        answer(cid, "APPROVE", "cid-STALE")
    assert not any("/confirmation/" in path for _m, path, _b in backend.calls)
    # The live id was never overwritten by the supplied stale one.
    assert entry.conversation._pending_confirmation_id == "cid-NEW"

    # And the true live id still approves.
    backend.turn_responses = [assistant("deleted new")]
    res = answer(cid, "APPROVE", "cid-NEW")
    assert res["status"] == "completed"
    assert any("/confirmation/cid-NEW" in path for _m, path, _b in backend.calls)


# --------------------------------------------------------------------------- #
# Wave-2 Finding 2: begin-turn is atomic — a second caller cannot rebind the
# first caller's client, and never raises an uncaught RuntimeError.
# --------------------------------------------------------------------------- #


def test_begin_turn_overlap_does_not_rebind_client(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    entry = cobuild._get_live(cid)
    client_a = object()
    entry.conversation.client = client_a

    # Caller A already reserved the slot.
    cobuild._in_flight[cid] = _pending_turn(cid)

    # Caller B tries to begin a turn with a DIFFERENT client.
    client_b = object()
    with pytest.raises(cobuild._CobuildInProgress) as excinfo:
        cobuild._begin_turn(
            cid,
            entry,
            lambda: None,
            kind="send",
            allow_edit_project=False,
            rehydrated=False,
            client=client_b,
        )
    assert excinfo.value.turn is cobuild._in_flight[cid]
    # The shared handle's client was NOT rebound to B's client: the overlap check
    # and the client bind happen atomically under one lock, in that order.
    assert entry.conversation.client is client_a


def test_send_overlap_returns_in_progress_not_exception(env, monkeypatch):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    cobuild._in_flight[cid] = _pending_turn(cid)
    # Bypass the early fast-path check to force the atomic _begin_turn overlap
    # branch — the real concurrent-race path a second HTTP caller would hit.
    monkeypatch.setattr(cobuild, "_get_in_flight", lambda _cid: None)

    res = send(cid, "second build")
    assert res["status"] == "in_progress"  # structured, not a raised RuntimeError
    assert not any(p.endswith("/messages") for _m, p, _b in backend.calls)


# --------------------------------------------------------------------------- #
# Wave-2 Finding 3: a callback exception still leaves the store terminal
# --------------------------------------------------------------------------- #


def test_callback_exception_still_persists_terminal(env, monkeypatch):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    from dataiku_mcp.tools.utils import conversation_store as cs

    real = cs.ConversationStore.record_outcome
    calls = {"n": 0}

    def flaky(self, conversation_id, status, pending, token=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated store failure on first terminal write")
        return real(self, conversation_id, status, pending, token=token)

    monkeypatch.setattr(cs.ConversationStore, "record_outcome", flaky)

    backend.turn_responses = [assistant("done")]
    res = send(cid, "build")
    assert res["status"] == "completed"

    # Despite the first record_outcome raising, the store must NOT linger at
    # in_flight: the minimal terminal retry (or the other settle path) wrote it.
    rec = _wait_store_terminal(env, cid)
    assert rec["last_result_status"] == "completed"


# --------------------------------------------------------------------------- #
# Wave-2 Finding 4: status polling verifies instance ownership (both paths)
# --------------------------------------------------------------------------- #


def test_status_poll_rejects_wrong_instance_live(env):
    backend = FakeBackend()
    gate = threading.Event()
    backend.gate = gate
    backend.turn_responses = [assistant("done")]
    env.set_client(backend)
    cid = start()
    assert send(cid, "long build", timeout_seconds=1)["status"] == "timeout"

    env.set_instance("inst-b")
    with pytest.raises(ValueError, match="belongs to instance"):
        run(cobuild.get_cobuild_turn_status(cid, "PROJ", FakeCtx()))

    # Cleanup: settle on the owning instance.
    gate.set()
    env.set_instance("inst-a")
    poll_status(cid)


def test_status_poll_rejects_wrong_instance_store(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    backend.turn_responses = [confirmation("Delete x?", "cid-x", [OBJ], {})]
    send(cid, "delete x")
    _wait_store_terminal(env, cid)
    cobuild._in_flight.clear()  # force the store-backed polling path

    env.set_instance("inst-b")
    with pytest.raises(ValueError, match="belongs to instance"):
        run(cobuild.get_cobuild_turn_status(cid, "PROJ", FakeCtx()))


# --------------------------------------------------------------------------- #
# Wave-2 Finding 5: retained registry is bounded (settled cap + hung sweep)
# --------------------------------------------------------------------------- #


def test_settled_eviction_bounds_retained_entries(env, monkeypatch):
    monkeypatch.setattr(cobuild, "MAX_SETTLED_RETAINED", 3)
    now = time.monotonic()
    for i in range(6):
        f = concurrent.futures.Future()
        f.set_result(None)
        turn = _pending_turn(f"s-{i}")
        turn.future = f
        turn.settled_at = now - (100 - i)  # smaller i => older
        cobuild._in_flight[f"s-{i}"] = turn

    with cobuild._lock:
        cobuild._sweep_in_flight(now=now)

    # Only the newest MAX_SETTLED_RETAINED settled turns are retained.
    assert set(cobuild._in_flight) == {"s-3", "s-4", "s-5"}


def test_hung_turn_evicted_and_abandoned(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()  # registers the conversation in the store

    turn = _pending_turn(cid)  # unfinished future
    turn.started_at = time.monotonic() - cobuild.HUNG_TURN_CEILING_SECONDS - 1
    cobuild._in_flight[cid] = turn

    with cobuild._lock:
        cobuild._sweep_in_flight()

    assert cid not in cobuild._in_flight
    assert read_store(env)[cid]["last_result_status"] == "abandoned"


def test_hung_turn_eviction_frees_capacity(env, monkeypatch):
    monkeypatch.setattr(cobuild, "MAX_CONCURRENT_COBUILD_TURNS", 1)
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    # A wedged turn occupies the only concurrency slot.
    hung = _pending_turn("hung")
    hung.started_at = time.monotonic() - cobuild.HUNG_TURN_CEILING_SECONDS - 1
    cobuild._in_flight["hung"] = hung

    # A new send sweeps the hung turn (freeing the slot) and proceeds.
    backend.turn_responses = [assistant("built")]
    res = send(cid, "please build")
    assert res["status"] == "completed"
    assert "hung" not in cobuild._in_flight


def test_late_callback_after_eviction_still_persists(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()

    class _Resp:
        type = "assistant_message"
        is_error = False
        message = "late done"

    f = concurrent.futures.Future()
    f.set_running_or_notify_cancel()
    turn = cobuild._InFlightTurn(
        future=f,
        conversation_id=cid,
        project_key="PROJ",
        instance_name="inst-a",
        handle=object(),
        started_at=time.monotonic(),
        kind="send",
        allow_edit_project=False,
    )

    # The hung turn is evicted with an 'abandoned' placeholder outcome.
    with cobuild._lock:
        cobuild._abandon_turn(turn)
    assert read_store(env)[cid]["last_result_status"] == "abandoned"

    # Its daemon later finishes: the done-callback must tolerate the gone entry
    # and still overwrite 'abandoned' with the real terminal outcome.
    f.add_done_callback(lambda _f: cobuild._persist_terminal_outcome(turn))
    f.set_result(_Resp())
    assert read_store(env)[cid]["last_result_status"] == "completed"


# --------------------------------------------------------------------------- #
# Round-3 Finding 1: confirmation validation + consumption is atomic inside
# _begin_turn — two concurrent answers, only one consumes; the loser gets a
# structured in_progress with NO handle mutation and NO stale restore.
# --------------------------------------------------------------------------- #


def test_two_concurrent_confirmations_only_one_consumes(env, monkeypatch):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    # A pending delete confirmation cid-9 is live on the handle.
    backend.turn_responses = [confirmation("Delete x?", "cid-9", [OBJ], {})]
    send(cid, "delete x")
    entry = cobuild._get_live(cid)
    assert entry.conversation._pending_confirmation_id == "cid-9"

    # Caller A has already reserved the slot (its answer turn is in flight).
    cobuild._in_flight[cid] = _pending_turn(cid)

    # Caller B races in with a VALID confirmation_id but bypasses the early
    # fast-path, so it hits the ATOMIC _begin_turn overlap branch — the real
    # second-caller race path.
    monkeypatch.setattr(cobuild, "_get_in_flight", lambda _cid: None)
    backend.turn_responses = [assistant("must not run")]
    res = answer(cid, "APPROVE", "cid-9")

    # The loser gets a structured in_progress, not a raised exception or a send.
    assert res["status"] == "in_progress"
    # It consumed/validated nothing: the live pending id is untouched (no stale
    # restore, no clobber) and no confirmation POST was ever issued.
    assert entry.conversation._pending_confirmation_id == "cid-9"
    assert not any("/confirmation/" in p for _m, p, _b in backend.calls)


def test_begin_turn_confirmation_consumed_atomically_on_winner(env):
    # The winner validates + consumes inside _begin_turn under the lock: the SDK
    # answer_confirmation reads the id we bound, then clears it (consumed once).
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    backend.turn_responses = [confirmation("Delete y?", "cid-win", [OBJ], {})]
    send(cid, "delete y")

    backend.turn_responses = [assistant("deleted y")]
    res = answer(cid, "APPROVE", "cid-win")
    assert res["status"] == "completed"
    assert any("/confirmation/cid-win" in p for _m, p, _b in backend.calls)
    # Consumed exactly once: the handle's pending slot is cleared afterwards.
    assert cobuild._get_live(cid).conversation._pending_confirmation_id is None


# --------------------------------------------------------------------------- #
# Round-3 Finding 2: a rehydration racing a live entry discards its thin handle;
# the live handle of the active turn survives.
# --------------------------------------------------------------------------- #


def test_rehydration_discards_handle_when_live_entry_present(env, monkeypatch):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()  # installs a live entry + a store record
    live_entry = cobuild._get_live(cid)
    live_handle = live_entry.conversation

    # Force the cache-miss (rehydration) path even though a live entry exists,
    # simulating a caller that missed the cache then a concurrent caller that
    # installed/kept the live handle before our install.
    monkeypatch.setattr(cobuild, "_get_live", lambda _cid: None)

    _name, client = cobuild._resolve_client_and_instance()
    entry, rehydrated = cobuild._resolve_entry(cid, "PROJ", "inst-a", client)

    # The live handle survived; the freshly-rehydrated thin handle was discarded.
    assert entry is live_entry
    assert entry.conversation is live_handle
    assert rehydrated is False
    # The cache still holds the original live handle, not a replacement.
    assert cobuild._conversations[cid] is live_entry


def test_remember_does_not_overwrite_live_with_rehydrated(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    live_entry = cobuild._get_live(cid)

    thin = cobuild._CobuildEntry(
        instance_name="inst-a",
        project_key="PROJ",
        conversation=object(),
        created_at="",
    )
    # Install-if-absent (default): an existing live entry wins, thin is discarded.
    effective = cobuild._remember(cid, thin)
    assert effective is live_entry
    assert cobuild._conversations[cid] is live_entry

    # The start path (replace=True) is the only sanctioned overwrite.
    replacement = cobuild._CobuildEntry(
        instance_name="inst-a",
        project_key="PROJ",
        conversation=object(),
        created_at="",
    )
    effective2 = cobuild._remember(cid, replacement, replace=True)
    assert effective2 is replacement
    assert cobuild._conversations[cid] is replacement


# --------------------------------------------------------------------------- #
# Round-3 Finding 3: a late/stale in_flight marker cannot overwrite a terminal
# outcome recorded for the SAME turn token; a NEW turn still may go in_flight.
# --------------------------------------------------------------------------- #


def test_late_in_flight_mark_cannot_clobber_terminal(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    store = cobuild._store()
    token = f"{cobuild._PROCESS_ID}:7"

    # Simulate the OLD interleaving: the turn's terminal outcome was settled
    # (for token T) BEFORE the original caller armed persistence.
    store.record_outcome(cid, "completed", None, token=token)
    assert read_store(env)[cid]["last_result_status"] == "completed"

    # The late mark_in_flight for the SAME turn token must be REFUSED: a completed
    # turn cannot be resurrected to in_flight (settle-once can no longer correct it
    # once armed inside _begin_turn, so the store itself must refuse).
    store.mark_in_flight(cid, token)
    assert read_store(env)[cid]["last_result_status"] == "completed"

    # A genuinely NEW turn (newer token) may still go in_flight after the old
    # terminal outcome.
    store.mark_in_flight(cid, f"{cobuild._PROCESS_ID}:8")
    assert read_store(env)[cid]["last_result_status"] == "in_flight"


def test_older_turn_token_cannot_clobber_newer_outcome(env):
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    store = cobuild._store()

    store.record_outcome(cid, "completed", None, token=f"{cobuild._PROCESS_ID}:5")
    # An OLDER turn from the SAME process writes a late outcome: refused.
    store.record_outcome(cid, "error", "cid-old", token=f"{cobuild._PROCESS_ID}:3")
    assert read_store(env)[cid]["last_result_status"] == "completed"

    # A DIFFERENT process (a restart resets the sequence) is never refused: its
    # threads cannot race, and a reset seq must not freeze the store.
    store.record_outcome(cid, "needs_confirmation", "cid-new", token="other-proc:1")
    assert read_store(env)[cid]["last_result_status"] == "needs_confirmation"


def test_send_persists_terminal_never_lingers_in_flight(env):
    # End-to-end: arm-before-visible means a fast send settles to a terminal
    # store status; it never lingers at in_flight.
    backend = FakeBackend()
    env.set_client(backend)
    cid = start()
    backend.turn_responses = [assistant("built fast")]
    res = send(cid, "quick build")
    assert res["status"] == "completed"
    rec = _wait_store_terminal(env, cid)
    assert rec["last_result_status"] == "completed"


# --------------------------------------------------------------------------- #
# Round-3 Finding 4: a DataikuException without a client-error signature (the
# HTTP status was discarded by dataikuapi) is outcome-UNKNOWN; a structured DSS
# client error stays DEFINITIVE.
# --------------------------------------------------------------------------- #


def test_backend_failure_without_status_is_outcome_unknown(env):
    backend = FakeBackend()
    # A real HTTP 503 body: dataikuapi discards the status code, so no "5xx" text.
    backend.turn_responses = [DataikuException("BackendFailure: write failed")]
    env.set_client(backend)
    cid = start()

    res = send(cid, "build something")
    assert res["status"] == "error"
    assert res["error_kind"] == "transport_outcome_unknown"
    assert "partially" in res["message"].lower()


@pytest.mark.parametrize(
    "text",
    [
        "Permission denied on project X",
        "Invalid argument: column 'x' is unknown",
        "Object not found: dataset orders",
        "Dataset already exists: orders",
    ],
)
def test_structured_client_error_stays_definitive(env, text):
    backend = FakeBackend()
    backend.turn_responses = [DataikuException(text)]
    env.set_client(backend)
    cid = start()

    res = send(cid, "build something")
    assert res["status"] == "error"
    # A recognized DSS client-error signature → definitive (no blind-resend risk).
    assert res.get("error_kind") != "transport_outcome_unknown"
