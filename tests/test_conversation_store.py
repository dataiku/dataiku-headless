"""Durability, ownership, and cross-process tests for conversation metadata."""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import stat
import time

import portalocker
import pytest

from dataiku_mcp.tools import cobuild
from dataiku_mcp.tools.utils import conversation_store as store_module
from dataiku_mcp.tools.utils.conversation_store import (
    ConversationOwnershipError,
    ConversationStore,
    ConversationStoreError,
    PendingConfirmationError,
)


def record(*, owner="owner-a", project="PROJECT", instance="instance-a"):
    return {
        "instance_name": instance,
        "project_key": project,
        "owner_fingerprint": owner,
        "created_at": "2026-07-21T00:00:00+00:00",
        "pending_confirmation_id": None,
        "pending_objects_to_delete": None,
        "pending_deletion_impacts": None,
    }


def list_owned(store, *, owner="owner-a", project="PROJECT", instance="instance-a"):
    return store.list_owned(
        instance_name=instance,
        project_key=project,
        owner_fingerprint=owner,
    )


def register_in_process(path, conversation_id, start, results):
    start.wait(10)
    try:
        ConversationStore(path).register(conversation_id, record())
    except BaseException as exc:  # returned to the parent for an exact assertion
        results.put((conversation_id, type(exc).__name__, str(exc)))
    else:
        results.put((conversation_id, "ok", ""))


def hold_lock_in_process(lock_path, ready, release):
    with portalocker.Lock(lock_path, mode="a", timeout=5, check_interval=0.05):
        ready.set()
        release.wait(10)


def test_missing_store_is_an_empty_registry(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")

    assert list_owned(store) == {}


def test_register_and_read_owned_round_trip(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    store.register("conversation-1", record())

    loaded = store.read_owned(
        "conversation-1",
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="owner-a",
    )

    assert loaded == record()
    loaded["project_key"] = "mutated-copy"
    assert list_owned(store)["conversation-1"]["project_key"] == "PROJECT"


def test_register_refuses_to_replace_existing_ownership(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    store.register("conversation-1", record(owner="owner-a"))

    with pytest.raises(ConversationStoreError, match="already registered"):
        store.register("conversation-1", record(owner="owner-b"))

    assert list_owned(store, owner="owner-a")["conversation-1"][
        "owner_fingerprint"
    ] == "owner-a"


@pytest.mark.parametrize(
    ("owner", "project", "instance"),
    [
        ("owner-b", "PROJECT", "instance-a"),
        ("owner-a", "OTHER", "instance-a"),
        ("owner-a", "PROJECT", "instance-b"),
    ],
)
def test_read_owned_checks_every_scope_dimension(tmp_path, owner, project, instance):
    store = ConversationStore(tmp_path / "conversations.json")
    store.register("conversation-1", record())

    with pytest.raises(ConversationOwnershipError, match="current credential"):
        store.read_owned(
            "conversation-1",
            instance_name=instance,
            project_key=project,
            owner_fingerprint=owner,
        )


def test_list_owned_filters_instead_of_disclosing_foreign_ids(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    store.register("owned", record(owner="owner-a"))
    store.register("foreign", record(owner="owner-b"))

    assert set(list_owned(store, owner="owner-a")) == {"owned"}
    assert set(list_owned(store, owner="owner-b")) == {"foreign"}


def test_complete_confirmation_proposal_is_persisted_and_consumed_once(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    store.register("conversation-1", record())
    objects = [{"type": "DATASET", "id": "old_output"}]
    impacts = {"recipes": ["downstream"]}
    store.set_pending_confirmation(
        "conversation-1",
        confirmation_id="confirm-once",
        objects_to_delete=objects,
        deletion_impacts=impacts,
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="owner-a",
    )

    persisted = list_owned(store)["conversation-1"]
    assert persisted["pending_confirmation_id"] == "confirm-once"
    assert persisted["pending_objects_to_delete"] == objects
    assert persisted["pending_deletion_impacts"] == impacts

    consumed = store.consume_pending_confirmation(
        "conversation-1",
        "confirm-once",
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="owner-a",
    )

    assert consumed == {
        "confirmation_id": "confirm-once",
        "objects_to_delete": objects,
        "deletion_impacts": impacts,
    }
    persisted = list_owned(store)["conversation-1"]
    assert persisted["pending_confirmation_id"] is None
    assert persisted["pending_objects_to_delete"] is None
    assert persisted["pending_deletion_impacts"] is None
    with pytest.raises(PendingConfirmationError, match="No pending"):
        store.consume_pending_confirmation(
            "conversation-1",
            "confirm-once",
            instance_name="instance-a",
            project_key="PROJECT",
            owner_fingerprint="owner-a",
        )


def test_wrong_confirmation_id_does_not_consume_proposal(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    store.register("conversation-1", record())
    store.set_pending_confirmation(
        "conversation-1",
        confirmation_id="confirm-right",
        objects_to_delete=[{"id": "old"}],
        deletion_impacts={"count": 1},
        instance_name="instance-a",
        project_key="PROJECT",
        owner_fingerprint="owner-a",
    )

    with pytest.raises(PendingConfirmationError, match="does not match"):
        store.consume_pending_confirmation(
            "conversation-1",
            "confirm-wrong",
            instance_name="instance-a",
            project_key="PROJECT",
            owner_fingerprint="owner-a",
        )

    assert list_owned(store)["conversation-1"]["pending_confirmation_id"] == (
        "confirm-right"
    )


def test_corrupt_json_is_quarantined_and_never_overwritten(tmp_path):
    path = tmp_path / "conversations.json"
    path.write_text("{not json", encoding="utf-8")
    store = ConversationStore(path)

    with pytest.raises(ConversationStoreError, match="moved") as error:
        list_owned(store)

    backups = list(tmp_path.glob("conversations.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not json"
    assert str(backups[0]) in str(error.value)
    assert not path.exists()


@pytest.mark.parametrize(
    "invalid",
    [[], {"conversation-1": []}, {"": {"project_key": "PROJECT"}}],
)
def test_invalid_registry_shape_is_quarantined(tmp_path, invalid):
    path = tmp_path / "conversations.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ConversationStoreError, match="invalid shape"):
        list_owned(ConversationStore(path))

    assert list(tmp_path.glob("conversations.json.corrupt-*"))


def test_quarantine_names_are_unique(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    for contents in ("bad-one", "bad-two"):
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(ConversationStoreError):
            list_owned(store)

    backups = sorted(tmp_path.glob("conversations.json.corrupt-*"))
    assert len(backups) == 2
    assert {item.read_text(encoding="utf-8") for item in backups} == {
        "bad-one",
        "bad-two",
    }


def test_io_error_is_reported_without_moving_the_file(tmp_path, monkeypatch):
    path = tmp_path / "conversations.json"
    path.write_text("{}", encoding="utf-8")
    original_open = Path.open

    def denied(candidate, *args, **kwargs):
        if candidate == path:
            raise PermissionError("denied")
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)

    with pytest.raises(ConversationStoreError, match="was not moved"):
        list_owned(ConversationStore(path))

    assert path.exists()
    assert list(tmp_path.glob("conversations.json.corrupt-*")) == []


def test_failed_atomic_replace_cleans_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "conversations.json"
    original_replace = store_module.os.replace

    def fail_temporary_replace(source, destination):
        if str(source).endswith(".tmp") and Path(destination) == path:
            raise OSError("simulated replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(store_module.os, "replace", fail_temporary_replace)

    with pytest.raises(OSError, match="simulated"):
        ConversationStore(path).register("conversation-1", record())

    assert list(tmp_path.glob(".conversations.json-*.tmp")) == []
    assert not path.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable")
def test_state_and_lock_files_are_private(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    store.register("conversation-1", record())

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.lock_path.stat().st_mode) == 0o600


def test_cross_process_writers_do_not_lose_records(tmp_path):
    path = tmp_path / "conversations.json"
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=register_in_process,
            args=(path, f"conversation-{index}", start, results),
        )
        for index in range(6)
    ]
    for process in processes:
        process.start()
    start.set()
    outcomes = [results.get(timeout=15) for _ in processes]
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    assert {status for _conversation_id, status, _message in outcomes} == {"ok"}
    assert set(list_owned(ConversationStore(path))) == {
        f"conversation-{index}" for index in range(6)
    }


def test_store_lock_wait_is_bounded_and_does_not_recommend_deleting_lock(
    tmp_path, monkeypatch
):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    store.register("conversation-1", record())
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=hold_lock_in_process,
        args=(store.lock_path, ready, release),
    )
    process.start()
    assert ready.wait(10)
    monkeypatch.setattr(store_module, "_LOCK_TIMEOUT_SECONDS", 0.15)

    started = time.monotonic()
    with pytest.raises(ConversationStoreError, match="retry") as error:
        list_owned(store)
    elapsed = time.monotonic() - started

    release.set()
    process.join(timeout=10)
    assert process.exitcode == 0
    assert elapsed < 2
    assert "remove" not in str(error.value).lower()
    assert "delete" not in str(error.value).lower()


def test_state_dir_honors_explicit_then_xdg_then_home(monkeypatch, tmp_path):
    monkeypatch.setenv("DKU_MCP_STATE_DIR", str(tmp_path / "explicit"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert cobuild._state_dir() == tmp_path / "explicit"

    monkeypatch.delenv("DKU_MCP_STATE_DIR")
    assert cobuild._state_dir() == tmp_path / "xdg" / "dataiku-headless"

    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cobuild._state_dir() == (
        tmp_path / "home" / ".local" / "state" / "dataiku-headless"
    )
