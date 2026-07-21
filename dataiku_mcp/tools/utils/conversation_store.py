"""Cross-platform durable metadata store for Cobuild conversations.

Only rehydration metadata is persisted; live SDK handles remain process-local.
Every read-modify-write cycle holds a process lock and a bounded cross-process
file lock. Writes use a private temporary file plus ``os.replace`` so readers
observe either the old complete JSON object or the new complete JSON object.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
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


class ConversationTurnBusy(RuntimeError):
    """Raised when a live process owns this conversation's turn lock."""


class ConversationTurnLost(RuntimeError):
    """Raised when durable state says in-flight but its process lock is gone."""


class ConversationTurnSaturated(RuntimeError):
    """Raised when every cross-process capacity slot is held."""

    def __init__(self, capacity: int):
        super().__init__(f"All {capacity} Cobuild turn slots are occupied.")
        self.capacity = capacity


class ConversationTurnClaim:
    """Own the per-conversation and capacity locks for one live turn."""

    def __init__(self, conversation_lock, slot_lock):
        self._conversation_lock = conversation_lock
        self._slot_lock = slot_lock
        self._conversation_released = False
        self._slot_released = False
        self._release_lock = threading.Lock()

    @property
    def released(self) -> bool:
        with self._release_lock:
            return self._conversation_released and self._slot_released

    def release(self) -> None:
        with self._release_lock:
            # Release the capacity slot first, then the conversation. A new
            # caller can only claim the conversation after both are free.
            try:
                if not self._slot_released:
                    self._slot_lock.release()
                    self._slot_released = True
            finally:
                if not self._conversation_released:
                    self._conversation_lock.release()
                    self._conversation_released = True


class ConversationStore:
    """File-backed ``conversation_id -> metadata`` registry."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.lock")

    def _turn_lock_path(self, conversation_id: str) -> Path:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:24]
        return self.path.with_name(f"{self.path.name}.turn-{digest}.lock")

    def _slot_lock_path(self, slot: int) -> Path:
        return self.path.with_name(f"{self.path.name}.slot-{slot}.lock")

    @staticmethod
    def _prepare_private_lock(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, _FILE_MODE)
        os.close(fd)
        try:
            os.chmod(path, _FILE_MODE)
        except OSError:
            pass

    def _prepare_parent(self) -> None:
        # os.open applies 0600 on creation; chmod repairs a permissive sidecar
        # left by an older version where POSIX mode bits are supported.
        self._prepare_private_lock(self.lock_path)

    @staticmethod
    def _try_lock(path: Path):
        """Return an acquired Portalocker lock, or ``None`` without waiting."""
        ConversationStore._prepare_private_lock(path)
        lock = portalocker.Lock(
            path,
            mode="a",
            timeout=0,
            check_interval=0.01,
            fail_when_locked=True,
        )
        try:
            lock.acquire()
        except portalocker.exceptions.AlreadyLocked:
            return None
        return lock

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

    def claim_turn(
        self,
        conversation_id: str,
        turn_id: str,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
        kind: str,
        allow_edit_project: bool,
        max_concurrent_turns: int,
        confirmation_id: str | None = None,
        allow_lost_recovery: bool = False,
    ) -> tuple[ConversationTurnClaim, dict | None]:
        """Claim one conversation and capacity slot, then persist ``in_flight``.

        The OS locks remain held by the returned claim until the worker's
        terminal result has been persisted. If a process exits first, the OS
        releases the locks while the marker remains, allowing a later poll to
        report an outcome-unknown lost turn.
        """
        if not 1 <= max_concurrent_turns <= 256:
            raise ValueError("max_concurrent_turns must be between 1 and 256")

        conversation_lock = self._try_lock(self._turn_lock_path(conversation_id))
        if conversation_lock is None:
            raise ConversationTurnBusy(
                f"Conversation '{conversation_id}' has a turn in another process."
            )

        slot_lock = None
        try:
            for slot in range(max_concurrent_turns):
                slot_lock = self._try_lock(self._slot_lock_path(slot))
                if slot_lock is not None:
                    break
            if slot_lock is None:
                raise ConversationTurnSaturated(max_concurrent_turns)

            proposal = None
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
                if record.get("last_turn_status") == "in_flight":
                    if not allow_lost_recovery:
                        raise ConversationTurnLost(
                            f"Conversation '{conversation_id}' has an outcome-unknown "
                            "turn left by a process that exited."
                        )
                    record["last_recovered_lost_turn_id"] = record.get(
                        "last_turn_id"
                    )

                pending = record.get("pending_confirmation_id")
                if kind == "message" and pending:
                    raise PendingConfirmationError(
                        "This conversation has an unanswered deletion proposal. "
                        "Answer or cancel it before sending another message."
                    )
                if kind == "confirmation":
                    if not confirmation_id or not pending:
                        raise PendingConfirmationError(
                            f"No pending confirmation for conversation "
                            f"'{conversation_id}'."
                        )
                    if not hmac.compare_digest(str(pending), confirmation_id):
                        raise PendingConfirmationError(
                            "confirmation_id does not match the pending deletion "
                            "proposal."
                        )
                    proposal = {
                        "confirmation_id": pending,
                        "objects_to_delete": record.get(
                            "pending_objects_to_delete"
                        ),
                        "deletion_impacts": record.get("pending_deletion_impacts"),
                    }
                    record["pending_confirmation_id"] = None
                    record["pending_objects_to_delete"] = None
                    record["pending_deletion_impacts"] = None

                record["last_turn_id"] = turn_id
                record["last_turn_status"] = "in_flight"
                record["last_turn_kind"] = kind
                record["last_turn_allow_edit"] = allow_edit_project
                record["last_turn_started_at"] = time.time()
                record["last_turn_finished_at"] = None
                record["last_result"] = None
                self._write_all_unlocked(data)

            return ConversationTurnClaim(conversation_lock, slot_lock), proposal
        except BaseException:
            if slot_lock is not None:
                slot_lock.release()
            conversation_lock.release()
            raise

    def record_turn_result(
        self,
        conversation_id: str,
        turn_id: str,
        result: dict,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> None:
        """Persist exactly one terminal result for the current turn id."""
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
            if record.get("last_turn_id") != turn_id:
                raise ConversationStoreError(
                    f"Refusing a stale result for turn '{turn_id}'; the current "
                    f"turn is '{record.get('last_turn_id')}'."
                )
            status = str(result.get("status", "error"))
            if status == "in_progress":
                raise ConversationStoreError("A terminal result cannot be in_progress.")
            if status == "needs_confirmation":
                confirmation_id = result.get("confirmation_id")
                if not confirmation_id:
                    raise ConversationStoreError(
                        "A needs_confirmation result must include confirmation_id."
                    )
                record["pending_confirmation_id"] = confirmation_id
                record["pending_objects_to_delete"] = result.get(
                    "objects_to_delete"
                )
                record["pending_deletion_impacts"] = result.get(
                    "deletion_impacts"
                )
            record["last_turn_status"] = status
            record["last_turn_finished_at"] = time.time()
            record["last_result"] = dict(result)
            self._write_all_unlocked(data)

    def inspect_turn(
        self,
        conversation_id: str,
        *,
        instance_name: str,
        project_key: str,
        owner_fingerprint: str,
    ) -> tuple[dict, bool]:
        """Return ``(record, live_external)`` and settle orphan markers as lost.

        A busy per-conversation lock proves another process is still alive, so
        durable ``in_flight`` is reported as progress. If the lock can be
        acquired, no process owns that turn; an ``in_flight`` marker is changed
        to a durable outcome-unknown ``turn_lost`` result before returning.
        """
        record = self.read_owned(
            conversation_id,
            instance_name=instance_name,
            project_key=project_key,
            owner_fingerprint=owner_fingerprint,
        )
        if record is None:
            raise ConversationStoreError(
                f"Unknown Cobuild conversation_id '{conversation_id}'."
            )
        if record.get("last_turn_status") != "in_flight":
            return record, False

        probe = self._try_lock(self._turn_lock_path(conversation_id))
        if probe is None:
            return record, True
        try:
            with self._guarded():
                data = self._read_all_unlocked()
                current = data.get(conversation_id)
                if current is None:
                    raise ConversationStoreError(
                        f"Unknown Cobuild conversation_id '{conversation_id}'."
                    )
                self._assert_owned(
                    conversation_id,
                    current,
                    instance_name=instance_name,
                    project_key=project_key,
                    owner_fingerprint=owner_fingerprint,
                )
                if current.get("last_turn_status") == "in_flight":
                    lost = {
                        "status": "turn_lost",
                        "error_kind": "transport_outcome_unknown",
                        "message": (
                            "The process that owned this turn exited before a "
                            "terminal result was recorded. Inspect project state "
                            "before deciding whether any mutation should be retried."
                        ),
                        "conversation_id": conversation_id,
                        "turn_id": current.get("last_turn_id"),
                    }
                    current["last_turn_status"] = "turn_lost"
                    current["last_turn_finished_at"] = time.time()
                    current["last_result"] = lost
                    self._write_all_unlocked(data)
                return dict(current), False
        finally:
            probe.release()
