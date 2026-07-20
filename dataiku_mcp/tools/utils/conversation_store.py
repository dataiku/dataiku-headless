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
* A live turn also holds a per-conversation flock and one global capacity-slot
  flock for its entire lifetime. This prevents separate MCP processes sharing
  the state directory from double-sending or racing past the concurrency cap.
* The store **fails closed** on corruption: a file that is not valid JSON (or
  not a JSON object) is quarantined to ``<name>.corrupt-<unix-ts>`` and a clear
  error is raised naming the backup — it is never silently overwritten. A
  *missing* file is a normal empty store.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
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


class ConversationTurnBusy(RuntimeError):
    """Raised when another process owns this conversation's active turn."""


class ConversationTurnLost(RuntimeError):
    """Raised when a prior process died while its turn was still in flight."""


class ConversationTurnSaturated(RuntimeError):
    """Raised when every cross-process Cobuild capacity slot is occupied."""

    def __init__(self, running: list[str]):
        super().__init__("Cobuild turn capacity reached.")
        self.running = running


class ConversationTurnClaim:
    """Held OS locks proving ownership of one conversation turn and capacity slot."""

    def __init__(self, conversation_fd: int, slot_fd: int):
        self._conversation_fd = conversation_fd
        self._slot_fd = slot_fd
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        for fd in (self._slot_fd, self._conversation_fd):
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


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

    def _turn_lock_path(self, conversation_id: str) -> Path:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:24]
        return self._path.with_name(f"{self._path.name}.turn-{digest}.lock")

    def _slot_lock_path(self, slot: int) -> Path:
        return self._path.with_name(f"{self._path.name}.slot-{slot}.lock")

    @staticmethod
    def _try_flock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                return False
            raise

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

    def claim_turn(
        self,
        conversation_id: str,
        token: str,
        *,
        max_concurrent_turns: int,
        allow_lost_recovery: bool = False,
        confirmation_id: str | None = None,
        confirmation_source_token: str | None = None,
    ) -> ConversationTurnClaim:
        """Atomically claim a conversation and one global capacity slot.

        The per-conversation and slot flocks remain held by the returned claim for
        the whole turn. They are released automatically if the process dies, while
        the durable ``in_flight`` marker remains behind so the next process reports
        an outcome-unknown lost turn rather than blindly resending it.

        A caller may recover that lost marker only for an explicitly read-only
        follow-up. Because acquiring the conversation flock proves no live process
        still owns the turn, this preserves the documented inspection path without
        allowing a second mutating send after an ambiguous crash.
        """
        if max_concurrent_turns < 1:
            raise ValueError("max_concurrent_turns must be at least 1")

        self._path.parent.mkdir(parents=True, exist_ok=True)
        conversation_fd = os.open(
            self._turn_lock_path(conversation_id), os.O_CREAT | os.O_RDWR, _FILE_MODE
        )
        if not self._try_flock(conversation_fd):
            os.close(conversation_fd)
            raise ConversationTurnBusy(
                f"Conversation '{conversation_id}' has a turn in another process."
            )

        slot_fd: int | None = None
        try:
            for slot in range(max_concurrent_turns):
                candidate = os.open(
                    self._slot_lock_path(slot), os.O_CREAT | os.O_RDWR, _FILE_MODE
                )
                if self._try_flock(candidate):
                    slot_fd = candidate
                    break
                os.close(candidate)
            if slot_fd is None:
                with self._guarded():
                    data = self._read_all()
                    running = sorted(
                        cid
                        for cid, record in data.items()
                        if record.get("last_result_status") == "in_flight"
                    )
                raise ConversationTurnSaturated(running)

            with self._guarded():
                data = self._read_all()
                record = data.get(conversation_id)
                if record is None:
                    raise ValueError(f"Unknown Cobuild conversation_id '{conversation_id}'.")
                if record.get("last_result_status") == "in_flight":
                    if not allow_lost_recovery:
                        raise ConversationTurnLost(
                            f"Conversation '{conversation_id}' was in flight when its "
                            "owning process exited."
                        )
                if confirmation_id is not None:
                    pending = record.get("pending_confirmation_id")
                    if pending != confirmation_id:
                        same_producing_turn = (
                            confirmation_source_token is not None
                            and record.get("last_result_turn_token")
                            == confirmation_source_token
                        )
                        if not same_producing_turn:
                            raise ValueError(
                                f"confirmation_id '{confirmation_id}' does not match "
                                f"the durable pending confirmation for conversation "
                                f"'{conversation_id}'."
                            )
                    record["pending_confirmation_id"] = None
                record["last_result_status"] = "in_flight"
                record["last_result_turn_token"] = token
                record["turn_started_at"] = time.time()
                data[conversation_id] = record
                self._write_all(data)
            return ConversationTurnClaim(conversation_fd, slot_fd)
        except BaseException:
            if slot_fd is not None:
                fcntl.flock(slot_fd, fcntl.LOCK_UN)
                os.close(slot_fd)
            fcntl.flock(conversation_fd, fcntl.LOCK_UN)
            os.close(conversation_fd)
            raise

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

        ``token`` scopes the outcome to a specific turn. Once a token owns the
        record, an outcome carrying any other token is refused, so a late worker
        from another process cannot clobber its successor. Token-less callers
        keep the previous unconditional behaviour.
        """
        with self._guarded():
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            if token is not None:
                existing_token = record.get("last_result_turn_token")
                if existing_token is not None and existing_token != token:
                    return
                record["last_result_turn_token"] = token
            record["last_result_status"] = status
            record["pending_confirmation_id"] = pending
            self._write_all(data)
