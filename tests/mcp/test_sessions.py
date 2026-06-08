"""Tests for per-agent session isolation."""

from __future__ import annotations

import os

from dku_cli.mcp.sessions import SessionStore


def test_get_or_create_makes_isolated_dir(tmp_path):
    store = SessionStore(tmp_path)
    session = store.get_or_create("agent-A")
    assert session.workdir.is_dir()
    assert session.workdir.parent.name == "sessions"
    # 0700 on POSIX so other users in the pod cannot read it.
    if os.name == "posix":
        assert (session.workdir.stat().st_mode & 0o777) == 0o700


def test_key_is_stable_and_opaque(tmp_path):
    store = SessionStore(tmp_path)
    s1 = store.get_or_create("agent-A")
    s2 = store.get_or_create("agent-A")
    assert s1 is s2  # cached
    assert s1.key == store.key_for("agent-A")
    # The raw session id does not leak into the path.
    assert "agent-A" not in str(s1.workdir)


def test_distinct_agents_get_distinct_dirs(tmp_path):
    store = SessionStore(tmp_path)
    a = store.get_or_create("agent-A")
    b = store.get_or_create("agent-B")
    assert a.workdir != b.workdir


def test_secret_persists_across_instances(tmp_path):
    store1 = SessionStore(tmp_path)
    key1 = store1.key_for("agent-A")
    # A fresh store on the same root must derive the same key.
    store2 = SessionStore(tmp_path)
    assert store2.key_for("agent-A") == key1


def test_store_is_bounded_and_evicts_lru_workdir(tmp_path):
    # A long-lived hosted server sees one session per distinct bearer; the store
    # must stay bounded (LRU) and reap the evicted session's workdir.
    store = SessionStore(tmp_path, max_sessions=2)
    a = store.get_or_create("bearer:a")
    b = store.get_or_create("bearer:b")
    assert a.workdir.is_dir() and b.workdir.is_dir()

    # Touch 'a' so 'b' becomes the least-recently-used, then add a third.
    store.get_or_create("bearer:a")
    c = store.get_or_create("bearer:c")

    # Only two sessions are retained; 'b' was evicted and its workdir removed.
    assert len(store._sessions) == 2
    assert "bearer:b" not in store._sessions
    assert {"bearer:a", "bearer:c"} == set(store._sessions)
    assert not b.workdir.exists()  # evicted workdir cleaned up
    assert a.workdir.is_dir() and c.workdir.is_dir()


def test_eviction_does_not_grow_unbounded(tmp_path):
    store = SessionStore(tmp_path, max_sessions=4)
    for i in range(20):
        store.get_or_create(f"bearer:{i}")
    assert len(store._sessions) == 4
    # On disk, only the live sessions' workdirs remain.
    live = {s.key for s in store._sessions.values()}
    on_disk = {p.name for p in (tmp_path / "sessions").iterdir()}
    assert on_disk == live


def test_leased_session_is_exempt_from_eviction(tmp_path):
    store = SessionStore(tmp_path, max_sessions=2)
    a = store.get_or_create("bearer:a")
    store.get_or_create("bearer:b")

    with store.lease(a):
        # 'a' is LRU but leased — eviction must skip it and take 'b' instead.
        store.get_or_create("bearer:c")
        assert "bearer:a" in store._sessions
        assert "bearer:b" not in store._sessions
        assert a.workdir.is_dir()  # workdir survives while leased

    # After the lease ends, 'a' is evictable again.
    store.get_or_create("bearer:d")
    assert "bearer:a" not in store._sessions
    assert not a.workdir.exists()


def test_all_sessions_leased_allows_temporary_overflow(tmp_path):
    store = SessionStore(tmp_path, max_sessions=1)
    a = store.get_or_create("bearer:a")
    with store.lease(a):
        # 'a' is leased and 'b' is the just-created (protected) session, so
        # nothing is evictable: the store exceeds the cap rather than deleting
        # a workdir someone is using.
        b = store.get_or_create("bearer:b")
        assert len(store._sessions) == 2
        assert a.workdir.is_dir() and b.workdir.is_dir()
        with store.lease(b):
            c = store.get_or_create("bearer:c")
            assert len(store._sessions) == 3
            assert c.workdir.is_dir()
    # Leases released: the next create evicts the idle backlog down to the cap.
    d = store.get_or_create("bearer:d")
    assert len(store._sessions) == 1
    assert set(store._sessions) == {"bearer:d"}
    assert d.workdir.is_dir()


def test_new_session_at_full_busy_cap_is_not_self_evicted(tmp_path):
    # Regression: with the cap full of BUSY sessions, the newly created session
    # used to be the only idle candidate and was instantly evicted — handing
    # the caller a Session whose workdir was already rmtree'd.
    store = SessionStore(tmp_path, max_sessions=1)
    a = store.get_or_create("bearer:a")
    with store.lease(a):
        b = store.get_or_create("bearer:b")
        assert "bearer:b" in store._sessions
        assert b.workdir.is_dir()  # must NOT have been evicted at birth
