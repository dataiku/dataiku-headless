"""Tests for per-agent session isolation."""

from __future__ import annotations

import os

from dku_cli.mcp.server import default_state_root
from dku_cli.mcp.sessions import SessionStore


def test_get_or_create_makes_isolated_dir(tmp_path):
    store = SessionStore(tmp_path)
    session = store.get_or_create("agent-A")
    assert session.workdir.is_dir()
    assert session.workdir.parent.name == "sessions"
    if os.name == "posix":
        assert (session.workdir.stat().st_mode & 0o777) == 0o700


def test_default_state_root_is_user_scoped(monkeypatch, tmp_path):
    monkeypatch.delenv("DKU_MCP_STATE_ROOT", raising=False)
    root = default_state_root()

    if hasattr(os, "geteuid"):
        assert root.name == f"dku-mcp-{os.geteuid()}"
    else:
        assert root.name == "dku-mcp"

    override = tmp_path / "custom-state"
    monkeypatch.setenv("DKU_MCP_STATE_ROOT", str(override))
    assert default_state_root() == override


def test_key_is_stable_and_opaque(tmp_path):
    store = SessionStore(tmp_path)
    s1 = store.get_or_create("agent-A")
    s2 = store.get_or_create("agent-A")
    assert s1 is s2
    assert s1.key == store.key_for("agent-A")
    assert "agent-A" not in str(s1.workdir)


def test_distinct_agents_get_distinct_dirs(tmp_path):
    store = SessionStore(tmp_path)
    a = store.get_or_create("agent-A")
    b = store.get_or_create("agent-B")
    assert a.workdir != b.workdir


def test_secret_persists_across_instances(tmp_path):
    store1 = SessionStore(tmp_path)
    key1 = store1.key_for("agent-A")
    store2 = SessionStore(tmp_path)
    assert store2.key_for("agent-A") == key1


def test_store_is_bounded_and_evicts_lru_workdir(tmp_path):
    store = SessionStore(tmp_path, max_sessions=2)
    a = store.get_or_create("bearer:a")
    b = store.get_or_create("bearer:b")
    assert a.workdir.is_dir() and b.workdir.is_dir()

    store.get_or_create("bearer:a")
    c = store.get_or_create("bearer:c")

    assert len(store._sessions) == 2
    assert "bearer:b" not in store._sessions
    assert {"bearer:a", "bearer:c"} == set(store._sessions)
    assert not b.workdir.exists()
    assert a.workdir.is_dir() and c.workdir.is_dir()


def test_eviction_does_not_grow_unbounded(tmp_path):
    store = SessionStore(tmp_path, max_sessions=4)
    for i in range(20):
        store.get_or_create(f"bearer:{i}")
    assert len(store._sessions) == 4
    live = {s.key for s in store._sessions.values()}
    on_disk = {p.name for p in (tmp_path / "sessions").iterdir()}
    assert on_disk == live


def test_leased_session_is_exempt_from_eviction(tmp_path):
    store = SessionStore(tmp_path, max_sessions=2)
    a = store.get_or_create("bearer:a")
    store.get_or_create("bearer:b")

    with store.lease(a):
        store.get_or_create("bearer:c")
        assert "bearer:a" in store._sessions
        assert "bearer:b" not in store._sessions
        assert a.workdir.is_dir()

    store.get_or_create("bearer:d")
    assert "bearer:a" not in store._sessions
    assert not a.workdir.exists()


def test_all_sessions_leased_allows_temporary_overflow(tmp_path):
    store = SessionStore(tmp_path, max_sessions=1)
    a = store.get_or_create("bearer:a")
    with store.lease(a):
        b = store.get_or_create("bearer:b")
        assert len(store._sessions) == 2
        assert a.workdir.is_dir() and b.workdir.is_dir()
        with store.lease(b):
            c = store.get_or_create("bearer:c")
            assert len(store._sessions) == 3
            assert c.workdir.is_dir()
    d = store.get_or_create("bearer:d")
    assert len(store._sessions) == 1
    assert set(store._sessions) == {"bearer:d"}
    assert d.workdir.is_dir()


def test_new_session_at_full_busy_cap_is_not_self_evicted(tmp_path):
    store = SessionStore(tmp_path, max_sessions=1)
    a = store.get_or_create("bearer:a")
    with store.lease(a):
        b = store.get_or_create("bearer:b")
        assert "bearer:b" in store._sessions
        assert b.workdir.is_dir()


def test_acquire_leases_for_duration(tmp_path):
    store = SessionStore(tmp_path)
    with store.acquire("bearer:a") as s:
        assert s.active == 1
    assert s.active == 0


def test_acquire_new_session_survives_concurrent_overflow(tmp_path):
    store = SessionStore(tmp_path, max_sessions=1)
    with store.acquire("bearer:a") as a:
        with store.acquire("bearer:b") as b:
            assert a.workdir.is_dir()
            assert b.workdir.is_dir()


def test_concurrent_acquire_is_thread_safe(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = SessionStore(tmp_path, max_sessions=8)

    def worker(i: int) -> int:
        for _ in range(25):
            with store.acquire(f"bearer:{i % 12}"):
                pass
        return i

    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in [ex.submit(worker, i) for i in range(8)]:
            fut.result()

    assert all(s.active == 0 for s in store._sessions.values())
    assert len(store._sessions) <= 8
