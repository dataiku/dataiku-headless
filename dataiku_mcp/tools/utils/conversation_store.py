"""Cross-platform durable metadata store for Cobuild conversations.

Only rehydration metadata is persisted; live SDK handles remain process-local.
Every read-modify-write cycle holds a process lock and a bounded cross-process
file lock. Writes use a private temporary file plus ``os.replace`` so readers
observe either the old complete JSON object or the new complete JSON object.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hmac
import itertools
import json
import os
from pathlib import Path
import tempfile
import threading
import time

import portalocker

_FILE_MODE = 0o600
_LOCK_TIMEOUT_SECONDS = 5
_thread_lock = threading.RLock()
_quarantine_counter = itertools.count()


class ConversationStoreError(RuntimeError):
    """Raised when durable conversation metadata cannot be trusted or updated."""


class ConversationOwnershipError(ValueError):
    """Raised when a record does not belong to the current principal/scope."""


class PendingConfirmationError(ValueError):
    """Raised when a confirmation is absent, stale, or does not exact-match."""


class ConversationStore:
    """File-backed ``conversation_id -> metadata`` registry."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.lock")

    def _prepare_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # os.open applies 0600 only on creation. chmod also repairs a permissive
        # sidecar left by an older version; Windows accepts the call as a no-op
        # for unsupported mode bits.
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, _FILE_MODE)
        os.close(fd)
        try:
            os.chmod(self.lock_path, _FILE_MODE)
        except OSError:
            # The lock still provides exclusion on platforms without POSIX modes.
            pass

    @contextmanager
    def _guarded(self) -> Iterator[None]:
        """Bound one read/modify/write cycle across threads and processes."""
        with _thread_lock:
            self._prepare_parent()
            lock = portalocker.Lock(
                self.lock_path,
                mode="a",
                timeout=_LOCK_TIMEOUT_SECONDS,
                check_interval=0.05,
            )
            try:
                with lock:
                    yield
            except portalocker.exceptions.LockException as exc:
                raise ConversationStoreError(
                    f"Timed out after {_LOCK_TIMEOUT_SECONDS}s waiting for the "
                    f"conversation store at {self.path}. Another live process may "
                    "be updating it; retry after that operation finishes."
                ) from exc

    def _fsync_parent(self) -> None:
        """Persist a directory-entry swap where the platform supports it."""
        if not hasattr(os, "O_DIRECTORY"):
            return
        try:
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _quarantine(self, reason: str) -> Path:
        suffix = f"{time.time_ns()}-{os.getpid()}-{next(_quarantine_counter)}"
        backup = self.path.with_name(f"{self.path.name}.corrupt-{suffix}")
        try:
            os.replace(self.path, backup)
            self._fsync_parent()
        except OSError as exc:
            raise ConversationStoreError(
                f"Conversation store {self.path} is corrupt ({reason}) and could "
                f"not be quarantined to {backup}: {exc}. It remains untouched."
            ) from exc
        return backup

    def _read_all_unlocked(self) -> dict[str, dict]:
        try:
            with self.path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            backup = self._quarantine(str(exc))
            raise ConversationStoreError(
                f"Conversation store {self.path} was corrupt and was moved to "
                f"{backup}. Refusing to overwrite unreadable state."
            ) from exc
        except OSError as exc:
            raise ConversationStoreError(
                f"Could not read conversation store {self.path}: {exc}. The file "
                "was not moved or overwritten."
            ) from exc

        valid = isinstance(data, dict) and all(
            isinstance(conversation_id, str)
            and bool(conversation_id.strip())
            and isinstance(record, dict)
            for conversation_id, record in data.items()
        )
        if not valid:
            backup = self._quarantine(
                "top level must map string conversation ids to objects"
            )
            raise ConversationStoreError(
                f"Conversation store {self.path} had an invalid shape and was "
                f"moved to {backup}."
            )
        return data

    def _write_all_unlocked(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, _FILE_MODE)
            except OSError:
                pass
            os.replace(temporary, self.path)
            self._fsync_parent()
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _assert_owned(
        conversation_id: str,
        record: dict,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> None:
        if (
            record.get("instance_name") != instance_name
            or record.get("project_key") != project_key
            or not hmac.compare_digest(
                str(record.get("owner_fingerprint", "")), owner_fingerprint
            )
        ):
            raise ConversationOwnershipError(
                f"Unknown Cobuild conversation_id '{conversation_id}' for the "
                "current credential, instance, and project."
            )

    def register(self, conversation_id: str, record: dict) -> None:
        """Create one record; refuse an id collision instead of changing owners."""
        with self._guarded():
            data = self._read_all_unlocked()
            if conversation_id in data:
                raise ConversationStoreError(
                    f"Conversation id '{conversation_id}' is already registered; "
                    "refusing to replace its ownership metadata."
                )
            data[conversation_id] = dict(record)
            self._write_all_unlocked(data)

    def read_owned(
        self,
        conversation_id: str,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> dict | None:
        """Return a copy of an owned record, or ``None`` when the id is absent."""
        with self._guarded():
            record = self._read_all_unlocked().get(conversation_id)
            if record is None:
                return None
            self._assert_owned(
                conversation_id,
                record,
                instance_name=instance_name,
                project_key=project_key,
                owner_fingerprint=owner_fingerprint,
            )
            return dict(record)

    def list_owned(
        self,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> dict[str, dict]:
        """Return copies of records visible to one credential and scope."""
        with self._guarded():
            data = self._read_all_unlocked()
            return {
                conversation_id: dict(record)
                for conversation_id, record in data.items()
                if record.get("instance_name") == instance_name
                and record.get("project_key") == project_key
                and hmac.compare_digest(
                    str(record.get("owner_fingerprint", "")), owner_fingerprint
                )
            }

    def set_pending_confirmation(
        self,
        conversation_id: str,
        *,
        confirmation_id: str | None,
        objects_to_delete,
        deletion_impacts,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> None:
        """Persist the complete proposal, or clear it when ``confirmation_id`` is None."""
        with self._guarded():
            data = self._read_all_unlocked()
            record = data.get(conversation_id)
            if record is None:
                raise ConversationStoreError(
                    f"Unknown Cobuild conversation_id '{conversation_id}'."
                )
            self._assert_owned(
                conversation_id,
                record,
                instance_name=instance_name,
                project_key=project_key,
                owner_fingerprint=owner_fingerprint,
            )
            record["pending_confirmation_id"] = confirmation_id
            record["pending_objects_to_delete"] = (
                objects_to_delete if confirmation_id else None
            )
            record["pending_deletion_impacts"] = (
                deletion_impacts if confirmation_id else None
            )
            self._write_all_unlocked(data)

    def consume_pending_confirmation(
        self,
        conversation_id: str,
        confirmation_id: str,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> dict:
        """Exact-match and consume one proposal in a single locked transaction."""
        with self._guarded():
            data = self._read_all_unlocked()
            record = data.get(conversation_id)
            if record is None:
                raise PendingConfirmationError(
                    f"No pending confirmation for conversation '{conversation_id}'."
                )
            self._assert_owned(
                conversation_id,
                record,
                instance_name=instance_name,
                project_key=project_key,
                owner_fingerprint=owner_fingerprint,
            )
            pending = record.get("pending_confirmation_id")
            if pending is None:
                raise PendingConfirmationError(
                    f"No pending confirmation for conversation '{conversation_id}'."
                )
            if not hmac.compare_digest(str(pending), confirmation_id):
                raise PendingConfirmationError(
                    "confirmation_id does not match the pending deletion proposal."
                )
            proposal = {
                "confirmation_id": pending,
                "objects_to_delete": record.get("pending_objects_to_delete"),
                "deletion_impacts": record.get("pending_deletion_impacts"),
            }
            record["pending_confirmation_id"] = None
            record["pending_objects_to_delete"] = None
            record["pending_deletion_impacts"] = None
            self._write_all_unlocked(data)
            return proposal
