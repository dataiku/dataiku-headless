"""Durable JSON registry for Cobuild conversations.

A live ``DSSCobuildConversation`` handle cannot be serialized, so this stores
only the metadata needed to rehydrate a thin handle after a process restart:
the owning instance, the project, the creation time, any pending
delete-confirmation id, and the last known terminal status of a turn.

Concurrency & durability:

* Writes are atomic (``mkstemp`` + ``os.replace``) so a crash mid-write can
  never leave a half-written file, and the file is created ``0600`` because a
  stored ``pending_confirmation_id`` authorizes a destructive delete and must
  not be world-readable.
* Every read-modify-write cycle is guarded by both a process-wide lock and an
  inter-process ``fcntl.flock`` on a sidecar ``.lock`` file, so two MCP
  processes sharing a state dir cannot clobber each other's updates.
* The store **fails closed** on corruption: a file that is not valid JSON (or
  not a JSON object) is quarantined to ``<name>.corrupt-<unix-ts>`` and a clear
  error is raised naming the backup — it is never silently overwritten. A
  *missing* file is a normal empty store.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import itertools
import json
import os
import tempfile
import threading
import time
from pathlib import Path

_FILE_MODE = 0o600
_lock = threading.RLock()

# Upper bound on how long a read-modify-write cycle will wait for the sidecar
# ``flock`` before giving up. The lock is acquired non-blocking in a short retry
# loop so a wedged peer can never freeze the caller (notably an async event
# loop) indefinitely.
STORE_LOCK_TIMEOUT_SECONDS = 5

# Monotonic, process-lifetime counter that makes a quarantine backup name unique
# even when two corruptions land in the same wall-clock second.
_quarantine_counter = itertools.count()

# Statuses that represent a *settled* turn in the durable store. An ``in_flight``
# marker must never be written over one of these when it belongs to the SAME turn
# (a late, out-of-order marker for a turn that already reached a terminal state).
_TERMINAL_STORE_STATUSES = frozenset(
    {"completed", "needs_confirmation", "error", "abandoned"}
)


def _token_is_stale(existing_token, new_token) -> bool:
    """True when ``new_token`` is an OLDER turn from the SAME process as ``existing``.

    Turn tokens are ``"<process-id>:<monotonic-seq>"``. The sequence is only
    meaningful within a single process (it resets to 1 on restart), so an ordering
    comparison is valid ONLY when both tokens carry the same process id. Across
    processes (a restart) we never call a write stale: the old process's worker
    threads are gone and cannot race the new one, and a reset seq would otherwise
    wrongly freeze the store at the pre-restart outcome. A missing/None token on
    either side is never stale (backward-compatible with token-less callers).
    """
    if not existing_token or not new_token:
        return False
    existing_proc, _, existing_seq = str(existing_token).rpartition(":")
    new_proc, _, new_seq = str(new_token).rpartition(":")
    if not existing_proc or existing_proc != new_proc:
        return False
    try:
        return int(new_seq) < int(existing_seq)
    except ValueError:
        return False


class ConversationStoreError(RuntimeError):
    """Raised when the store file exists but cannot be trusted (fail closed)."""


class ConversationStore:
    """File-backed ``{conversation_id: record}`` registry.

    ``record`` is a flat dict with ``instance_name``, ``project_key``,
    ``created_at``, ``pending_confirmation_id`` (nullable), and optionally
    ``last_result_status``. The instance is stateless: it reads and writes
    ``path`` on every operation, so a caller that resolves ``path`` from the
    environment on each call naturally picks up a changed state directory.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)

    @property
    def _lock_path(self) -> Path:
        return self._path.with_name(self._path.name + ".lock")

    @contextlib.contextmanager
    def _guarded(self):
        """Hold the in-process lock and a bounded inter-process flock for one RMW cycle.

        The flock is acquired non-blocking in a short retry loop bounded by
        ``STORE_LOCK_TIMEOUT_SECONDS`` so a wedged peer holding the lock can never
        freeze the caller (notably an async event-loop thread) indefinitely; on
        the deadline we raise a clear error naming the lock file.
        """
        with _lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, _FILE_MODE)
            try:
                self._acquire_flock(fd)
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _acquire_flock(self, fd: int) -> None:
        """Acquire the exclusive sidecar flock, bounded by the store lock timeout."""
        deadline = time.monotonic() + STORE_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise ConversationStoreError(
                        f"Timed out after {STORE_LOCK_TIMEOUT_SECONDS}s waiting for "
                        f"the conversation-store lock at {self._lock_path}. Another "
                        "MCP process (or a wedged/crashed peer) is holding it; check "
                        "for a stuck process, then remove the stale .lock file if "
                        "none is running."
                    ) from exc
                time.sleep(0.05)

    def _quarantine(self, reason: str) -> Path:
        """Move a corrupt store aside and return the backup path.

        The backup name carries a unix-second, pid, and monotonic-counter suffix
        so two corruptions in the same second never collide. If the move itself
        fails the corrupt file is left in place and a ``ConversationStoreError`` is
        raised naming both paths — we never claim the file was quarantined when it
        was not.
        """
        suffix = f"{int(time.time())}-{os.getpid()}-{next(_quarantine_counter)}"
        backup = self._path.with_name(f"{self._path.name}.corrupt-{suffix}")
        try:
            os.replace(self._path, backup)
        except OSError as exc:
            raise ConversationStoreError(
                f"Conversation store at {self._path} is corrupt ({reason}) and could "
                f"NOT be quarantined to {backup} ({exc}). The corrupt file is still "
                f"in place at {self._path}; move or remove it by hand, then retry."
            ) from exc
        return backup

    def _read_all(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            # A missing store is a normal, empty store.
            return {}
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            backup = self._quarantine(str(exc))
            raise ConversationStoreError(
                f"Conversation store at {self._path} is unreadable/corrupt "
                f"({exc}). It was moved aside to {backup}; inspect or remove that "
                "backup, then retry. Refusing to overwrite it silently."
            ) from exc
        if not isinstance(data, dict):
            backup = self._quarantine("top-level JSON is not an object")
            raise ConversationStoreError(
                f"Conversation store at {self._path} did not contain a JSON object. "
                f"It was moved aside to {backup}; inspect or remove that backup, "
                "then retry."
            )
        return data

    def _write_all(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # mkstemp creates the file 0600 regardless of umask; os.replace then
        # atomically swaps it into place, preserving those permissions.
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".conversations-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"))
            os.chmod(tmp, _FILE_MODE)
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def read(self, conversation_id: str) -> dict | None:
        """Return the record for ``conversation_id`` or ``None``."""
        with self._guarded():
            return self._read_all().get(conversation_id)

    def all(self) -> dict:
        """Return every persisted record keyed by conversation id."""
        with self._guarded():
            return self._read_all()

    def upsert(self, conversation_id: str, record: dict) -> None:
        """Merge ``record`` into the stored record for ``conversation_id``."""
        with self._guarded():
            data = self._read_all()
            existing = data.get(conversation_id, {})
            existing.update(record)
            data[conversation_id] = existing
            self._write_all(data)

    def set_pending_confirmation(self, conversation_id: str, value: str | None) -> None:
        """Persist (or clear) the pending confirmation id for a known conversation.

        No-op if the conversation was never registered, so a lost/foreign id
        cannot inject an orphan record.
        """
        with self._guarded():
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            record["pending_confirmation_id"] = value
            self._write_all(data)

    def mark_in_flight(self, conversation_id: str, token: str | None = None) -> None:
        """Mark a turn as running so a poll after a crash can report it lost.

        A daemon-thread turn does not survive a process restart; persisting an
        ``in_flight`` marker lets ``get_cobuild_turn_status`` distinguish a
        turn that was lost to a restart from one that simply never existed.

        ``token`` scopes the marker to a specific turn. The write is REFUSED when
        it would regress the store: either the incoming token is an older turn
        from this process (a stale, out-of-order marker), or a terminal outcome
        has already been recorded for this exact token (a late marker that must
        not resurrect a settled turn to ``in_flight``). A genuinely NEW turn
        (a newer/other token) may of course go ``in_flight`` after an old
        terminal outcome. Token-less callers keep the previous unconditional
        behaviour.
        """
        with self._guarded():
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            if token is not None:
                existing_token = record.get("last_result_turn_token")
                if _token_is_stale(existing_token, token):
                    return
                if (
                    existing_token == token
                    and record.get("last_result_status") in _TERMINAL_STORE_STATUSES
                ):
                    return
                record["last_result_turn_token"] = token
            record["last_result_status"] = "in_flight"
            self._write_all(data)

    def record_outcome(
        self,
        conversation_id: str,
        status: str,
        pending: str | None,
        token: str | None = None,
    ) -> None:
        """Persist a settled turn's terminal status + pending confirmation id.

        Called from the turn's done-callback so a finished-but-unpolled turn's
        outcome (and any newly-requested delete confirmation) is not lost until
        the client next polls.

        ``token`` scopes the outcome to a specific turn: an OLDER turn's late
        outcome (same process, lower sequence) is REFUSED so it cannot clobber a
        newer turn's already-recorded state. Token-less callers keep the previous
        unconditional behaviour.
        """
        with self._guarded():
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            if token is not None:
                if _token_is_stale(record.get("last_result_turn_token"), token):
                    return
                record["last_result_turn_token"] = token
            record["last_result_status"] = status
            record["pending_confirmation_id"] = pending
            self._write_all(data)
