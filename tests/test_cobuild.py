"""Tests for the Cobuild conversation tools.

These never touch the network: ``get_dss_client`` is replaced by a fake client
whose ``_perform_json`` returns canned raw dicts, so the *real*
``DSSCobuildConversation`` SDK object drives the turn (exercising its actual
confirmation-id plumbing) against a fake backend. The durable store is pointed
at a per-test ``tmp_path`` via ``DKU_MCP_STATE_DIR``.
"""

import asyncio
import inspect
import json
import stat
import threading
import time

import pytest

from dataikuapi.dss.cobuild import DSSCobuildConversation
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
        return self.turn_responses.pop(0)


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


def answer(cid, choice, project_key="PROJ", **kwargs):
    return json.loads(
        run(
            cobuild.answer_cobuild_confirmation(
                cid, project_key, choice, FakeCtx(), **kwargs
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
    monkeypatch.setattr(
        "dataiku_mcp.config.get_current_instance_name", lambda: holder["instance"]
    )
    cobuild._conversations.clear()
    cobuild._in_flight.clear()

    class _Env:
        def __init__(self):
            self.tmp_path = tmp_path

        def set_client(self, backend):
            monkeypatch.setattr(cobuild, "get_dss_client", lambda: FakeClient(backend))

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
    res = answer(cid, "APPROVE", confirmation_id="cid-42")

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
    # No confirmation_id passed: it must be restored from the durable store.
    res = answer(cid, "APPROVE")

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
