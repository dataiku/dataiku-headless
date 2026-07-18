"""Durable JSON registry for Cobuild conversations.

A live ``DSSCobuildConversation`` handle cannot be serialized, so this stores
only the metadata needed to rehydrate a thin handle after a process restart:
the owning instance, the project, the creation time, and any pending
delete-confirmation id.

Writes are atomic (``mkstemp`` + ``os.replace``) so a crash mid-write can never
leave a half-written file, and the file is created ``0600`` because a stored
``pending_confirmation_id`` authorizes a destructive delete and must not be
world-readable. All read-modify-write cycles are guarded by a process-wide lock
because the store is instantiated per call (it holds no in-memory state itself).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

_FILE_MODE = 0o600
_lock = threading.RLock()


class ConversationStore:
    """File-backed ``{conversation_id: record}`` registry.

    ``record`` is a flat dict with ``instance_name``, ``project_key``,
    ``created_at``, and ``pending_confirmation_id`` (nullable). The instance is
    stateless: it reads and writes ``path`` on every operation, so a caller that
    resolves ``path`` from the environment on each call naturally picks up a
    changed state directory.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _read_all(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

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
        with _lock:
            return self._read_all().get(conversation_id)

    def all(self) -> dict:
        """Return every persisted record keyed by conversation id."""
        with _lock:
            return self._read_all()

    def upsert(self, conversation_id: str, record: dict) -> None:
        """Merge ``record`` into the stored record for ``conversation_id``."""
        with _lock:
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
        with _lock:
            data = self._read_all()
            record = data.get(conversation_id)
            if record is None:
                return
            record["pending_confirmation_id"] = value
            self._write_all(data)
