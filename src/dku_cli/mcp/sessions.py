"""Per-agent execution sessions — isolated working dirs keyed by an opaque HMAC.

Each connecting agent (or, over stdio, the single local user) gets its own
working directory under ``<state_root>/sessions/<key>`` with ``0700``
permissions, so concurrent agents cannot read or clobber each other's files.
The key is an HMAC of the session id under a per-host secret, so neither the
session id nor any user identity leaks into the filesystem layout — the same
opaque-key pattern AgentOS uses.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import shutil
import threading
from collections import OrderedDict
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

_KEY_LEN = 40
# Bound the in-memory cache + on-disk workdir count. On a long-lived hosted HTTP
# server each distinct bearer key mints one session; without a cap the store and
# `<state_root>/sessions/<hmac>` dirs grow forever (rotated/expired/typo'd keys
# included). LRU eviction keeps both bounded; evicting deletes the workdir too.
_MAX_SESSIONS = 64


@dataclass
class Session:
    session_id: str
    key: str
    workdir: Path
    active: int = 0


class SessionStore:
    """Creates and caches per-session working directories under a state root.

    The cache is bounded (LRU, ``_MAX_SESSIONS``): when a new session would
    exceed the cap, the least-recently-used one is evicted and its workdir is
    removed so a long-lived multi-tenant server does not leak memory or disk.
    """

    def __init__(
        self, root: str | os.PathLike[str], *, max_sessions: int = _MAX_SESSIONS
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        _chmod(self.root, 0o700)
        self._secret = self._load_or_create_secret()
        self._max_sessions = max(1, int(max_sessions))
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.RLock()

    def _load_or_create_secret(self) -> bytes:
        secret_path = self.root / "identity-secret"
        if secret_path.is_file():
            return secret_path.read_bytes()
        secret = secrets.token_bytes(32)
        secret_path.write_bytes(secret)
        _chmod(secret_path, 0o600)
        return secret

    def key_for(self, session_id: str) -> str:
        digest = hmac.new(self._secret, session_id.encode("utf-8"), hashlib.sha256)
        return digest.hexdigest()[:_KEY_LEN]

    def get_or_create(self, session_id: str) -> Session:
        with self._lock:
            return self._get_or_create_locked(session_id)

    def _get_or_create_locked(self, session_id: str) -> Session:
        key = self.key_for(session_id)
        cached = self._sessions.get(key)
        if cached is not None:
            self._sessions.move_to_end(key)  # mark as recently used
            return cached

        workdir = self.root / "sessions" / key
        workdir.mkdir(parents=True, exist_ok=True)
        _chmod(workdir, 0o700)

        session = Session(session_id=session_id, key=key, workdir=workdir)
        self._sessions[key] = session
        self._evict_overflow(protect=session)
        return session

    @contextmanager
    def acquire(self, session_id: str):
        with self._lock:
            session = self._get_or_create_locked(session_id)
            session.active += 1
        try:
            yield session
        finally:
            with self._lock:
                session.active -= 1

    def _evict_overflow(self, *, protect: Session | None = None) -> None:
        """Drop least-recently-used idle sessions over the cap, removing their workdirs.

        Sessions with a live lease (``active > 0``) are skipped, and so is the
        just-created ``protect`` session (its caller is about to use it but has
        not leased it yet). If no candidate remains, the store temporarily
        exceeds the cap rather than deleting a workdir someone is using.
        """
        while len(self._sessions) > self._max_sessions:
            victim_id = next(
                (
                    sid
                    for sid, s in self._sessions.items()
                    if s.active == 0 and s is not protect
                ),
                None,
            )
            if victim_id is None:
                return  # every other session is mid-execution — allow overflow
            evicted = self._sessions.pop(victim_id)
            shutil.rmtree(evicted.workdir, ignore_errors=True)


def _chmod(path: Path, mode: int) -> None:
    # Best-effort: some filesystems (e.g. Windows) don't support POSIX modes.
    with suppress(OSError):
        os.chmod(path, mode)
