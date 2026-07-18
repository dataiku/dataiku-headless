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
import fcntl
import json
import os
import tempfile
import threading
import time
from pathlib import Path

_FILE_MODE = 0o600
_lock = threading.RLock()


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
        """Hold the in-process lock and an inter-process flock for one RMW cycle."""
        with _lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, _FILE_MODE)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _quarantine(self, reason: str) -> Path:
        """Move a corrupt store aside and return the backup path."""
        backup = self._path.with_name(f"{self._path.name}.corrupt-{int(time.time())}")
        with contextlib.suppress(OSError):
            os.replace(self._path, backup)
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

    def mark_in_flight(self, conversation_id: str) -> None:
        """Mark a turn as running so a poll after a crash can report it lost.

        A daemon-thread turn does not survive a process restart; persisting an
        ``in_flight`` marker lets ``get_cobuild_turn_status`` distinguish a
        turn that was lost to a restart from one that simply never existed.
        """
        with self._guarded():
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            record["last_result_status"] = "in_flight"
            self._write_all(data)

    def record_outcome(
        self, conversation_id: str, status: str, pending: str | None
    ) -> None:
        """Persist a settled turn's terminal status + pending confirmation id.

        Called from the turn's done-callback so a finished-but-unpolled turn's
        outcome (and any newly-requested delete confirmation) is not lost until
        the client next polls.
        """
        with self._guarded():
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            record["last_result_status"] = status
            record["pending_confirmation_id"] = pending
            self._write_all(data)
