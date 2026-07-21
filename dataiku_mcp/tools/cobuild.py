"""Durable, least-privilege Cobuild conversation and retained-turn tools.

The DSS Cobuild API is synchronous, while one turn can run for minutes. A turn
therefore runs in a daemon thread whose ``Future`` remains registered after the
calling MCP request stops waiting. The durable store records ownership,
in-flight identity, terminal results, and complete delete proposals; OS locks
prevent overlap and bound capacity across server processes sharing that store.

No code here claims that a Python thread survives process exit. If the process
dies, its OS locks disappear while the durable in-flight marker remains. A poll
can then distinguish a live external owner (lock held) from a lost turn (lock
free) and reports the latter as outcome-unknown.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import concurrent.futures
import contextvars
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid

from dataikuapi.dss.cobuild import DSSCobuildConversation
from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client_and_principal
from .utils.conversation_store import (
    ConversationStore,
    ConversationTurnBusy,
    ConversationTurnClaim,
    ConversationTurnLost,
    ConversationTurnSaturated,
)
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)
from .utils.validation import require_positive_int as _require_positive_int

_logger = logging.getLogger(__name__)


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


DEFAULT_COBUILD_TIMEOUT_SECONDS = _bounded_env_int(
    "DKU_COBUILD_TIMEOUT_SECONDS", 1200, minimum=1, maximum=1800
)
MAX_COBUILD_TIMEOUT_SECONDS = _bounded_env_int(
    "DKU_COBUILD_MAX_TIMEOUT_SECONDS", 1800, minimum=1, maximum=7200
)
if DEFAULT_COBUILD_TIMEOUT_SECONDS > MAX_COBUILD_TIMEOUT_SECONDS:
    raise ValueError(
        "DKU_COBUILD_TIMEOUT_SECONDS cannot exceed DKU_COBUILD_MAX_TIMEOUT_SECONDS"
    )
MAX_CONCURRENT_COBUILD_TURNS = _bounded_env_int(
    "DKU_MCP_MAX_COBUILD_TURNS", 8, minimum=1, maximum=256
)

_LIVE_HANDLE_MAX = 256
_SETTLED_TURN_TTL_SECONDS = 3600
_MAX_SETTLED_TURNS = 64
_MAX_PERSISTED_RESULT_BYTES = 512_000


@dataclass
class _CobuildConversationEntry:
    instance_name: str
    project_key: str
    owner_fingerprint: str
    conversation: object
    created_at: str
    turn_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class _RetainedTurn:
    turn_id: str
    conversation_id: str
    project_key: str
    instance_name: str
    owner_fingerprint: str
    kind: str
    allow_edit_project: bool
    entry: _CobuildConversationEntry
    client: object
    store: ConversationStore
    claim: ConversationTurnClaim
    future: concurrent.futures.Future
    started_at: float
    rehydrated: bool
    message: str | None = None
    choice: str | None = None
    confirmation_id: str | None = None
    settled_at: float | None = None
    result_payload: dict | None = None
    result_persisted: bool = False
    terminal_persisted: bool = False
    persistence_error: str | None = None
    thread: threading.Thread | None = None
    finalize_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class _TurnAlreadyActive(RuntimeError):
    def __init__(self, turn: _RetainedTurn):
        super().__init__("A turn is already active for this conversation.")
        self.turn = turn


_conversations: OrderedDict[str, _CobuildConversationEntry] = OrderedDict()
_turns: dict[str, _RetainedTurn] = {}
_registry_lock = threading.RLock()


def _state_dir() -> Path:
    configured = os.environ.get("DKU_MCP_STATE_DIR", "").strip()
    if configured:
        return Path(configured)
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return base / "dataiku-headless"


def _store() -> ConversationStore:
    return ConversationStore(_state_dir() / "conversations.json")


def _capture_binding() -> tuple[str, object, str]:
    """Capture instance, client, and principal before the first tool ``await``."""
    instance = config.get_current_instance()
    client, owner_fingerprint = get_dss_client_and_principal(instance)
    return instance.name, client, owner_fingerprint


def _guard_entry(
    conversation_id: str,
    entry: _CobuildConversationEntry,
    *,
    project_key: str,
    instance_name: str,
    owner_fingerprint: str,
) -> None:
    if entry.project_key != project_key:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to project "
            f"'{entry.project_key}', not '{project_key}'."
        )
    if entry.instance_name != instance_name:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to instance "
            f"'{entry.instance_name}', not '{instance_name}'."
        )
    if not hmac.compare_digest(entry.owner_fingerprint, owner_fingerprint):
        raise ValueError(
            f"Unknown Cobuild conversation_id '{conversation_id}' for the current "
            "credential."
        )


def _get_live(conversation_id: str) -> _CobuildConversationEntry | None:
    with _registry_lock:
        entry = _conversations.get(conversation_id)
        if entry is not None:
            _conversations.move_to_end(conversation_id)
        return entry


def _remember(
    conversation_id: str,
    candidate: _CobuildConversationEntry,
    *,
    replace: bool = False,
) -> _CobuildConversationEntry:
    """Install a new handle or retain the existing live handle on rehydration."""
    with _registry_lock:
        existing = _conversations.get(conversation_id)
        if existing is not None and not replace:
            _conversations.move_to_end(conversation_id)
            return existing
        _conversations[conversation_id] = candidate
        _conversations.move_to_end(conversation_id)
        while len(_conversations) > _LIVE_HANDLE_MAX:
            for old_id in list(_conversations):
                active = _turns.get(old_id)
                if active is None or active.terminal_persisted:
                    del _conversations[old_id]
                    break
            else:
                break
        return candidate


def _resolve_conversation_entry(
    conversation_id: str,
    project_key: str,
    instance_name: str,
    client: object,
    owner_fingerprint: str,
) -> tuple[_CobuildConversationEntry, bool]:
    entry = _get_live(conversation_id)
    if entry is not None:
        _guard_entry(
            conversation_id,
            entry,
            project_key=project_key,
            instance_name=instance_name,
            owner_fingerprint=owner_fingerprint,
        )
        return entry, False

    record = _store().read_owned(
        conversation_id,
        instance_name=instance_name,
        project_key=project_key,
        owner_fingerprint=owner_fingerprint,
    )
    if record is None:
        raise ValueError(
            f"Unknown Cobuild conversation_id '{conversation_id}'. Start a new "
            "conversation first."
        )
    handle = DSSCobuildConversation(client, project_key, conversation_id)
    pending = record.get("pending_confirmation_id")
    if pending:
        handle._pending_confirmation_id = pending
    candidate = _CobuildConversationEntry(
        instance_name=instance_name,
        project_key=project_key,
        owner_fingerprint=owner_fingerprint,
        conversation=handle,
        created_at=str(record.get("created_at", "")),
    )
    entry = _remember(conversation_id, candidate)
    _guard_entry(
        conversation_id,
        entry,
        project_key=project_key,
        instance_name=instance_name,
        owner_fingerprint=owner_fingerprint,
    )
    return entry, entry is candidate


def _json_size(payload: dict) -> int:
    return len(
        json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    )


def _bound_terminal_payload(payload: dict, entry: _CobuildConversationEntry) -> dict:
    """Keep durable terminal results bounded without truncating a delete proposal."""
    # DSS payloads are normally plain JSON, but normalize any SDK wrapper values
    # before the terminal result reaches both compact_json and the strict durable
    # store. A non-JSON leaf must not leave a finished turn locked forever.
    payload = json.loads(json.dumps(payload, separators=(",", ":"), default=str))
    original_bytes = _json_size(payload)
    if original_bytes <= _MAX_PERSISTED_RESULT_BYTES:
        return payload

    if payload.get("status") == "needs_confirmation":
        entry.conversation._pending_confirmation_id = None
        return {
            "status": "error",
            "error_kind": "confirmation_proposal_too_large",
            "message": (
                "Cobuild returned a deletion proposal too large to preserve and "
                "show completely. It was not armed for approval. Narrow the "
                "requested deletion and ask Cobuild to propose it again."
            ),
            "conversation_id": payload.get("conversation_id"),
            "turn_id": payload.get("turn_id"),
            "original_bytes": original_bytes,
        }

    message = str(payload.get("message", ""))
    candidate = dict(payload)
    candidate["truncated"] = True
    candidate["original_bytes"] = original_bytes
    low, high = 0, len(message)
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate["message"] = message[:midpoint]
        if _json_size(candidate) <= _MAX_PERSISTED_RESULT_BYTES:
            low = midpoint
        else:
            high = midpoint - 1
    candidate["message"] = message[:low]
    if _json_size(candidate) <= _MAX_PERSISTED_RESULT_BYTES:
        return candidate
    return {
        "status": "error",
        "error_kind": "response_too_large",
        "message": "Cobuild returned a response that could not be stored safely.",
        "conversation_id": payload.get("conversation_id"),
        "turn_id": payload.get("turn_id"),
        "original_bytes": original_bytes,
    }


def _response_payload(turn: _RetainedTurn, response) -> dict:
    response_type = str(getattr(response, "type", ""))
    is_confirmation = bool(
        getattr(response, "is_confirmation_request", False)
        or response_type == "delete_confirmation_request"
    )
    is_error = bool(getattr(response, "is_error", False))
    payload = {
        "conversation_id": turn.conversation_id,
        "turn_id": turn.turn_id,
        "instance_name": turn.instance_name,
        "project_key": turn.project_key,
        "message": str(getattr(response, "message", "")),
        "response_type": response_type,
        "rehydrated": turn.rehydrated,
    }
    if is_confirmation:
        confirmation_id = getattr(
            turn.entry.conversation, "_pending_confirmation_id", None
        )
        if not confirmation_id:
            return {
                **payload,
                "status": "error",
                "error_kind": "missing_confirmation_id",
                "message": (
                    "Cobuild requested deletion confirmation without a server id; "
                    "the proposal was not armed for approval."
                ),
            }
        payload.update(
            {
                "status": "needs_confirmation",
                "confirmation_id": confirmation_id,
                "objects_to_delete": getattr(response, "objects_to_delete", None),
                "deletion_impacts": getattr(response, "deletion_impacts", None),
                "next_action": (
                    "Inspect objects_to_delete and deletion_impacts, then answer "
                    "this exact confirmation_id with APPROVE or CANCEL."
                ),
            }
        )
    elif is_error:
        payload.update({"status": "error", "error_kind": "cobuild_response"})
    else:
        payload["status"] = "completed"
    return _bound_terminal_payload(omit_empty(payload), turn.entry)


def _exception_payload(turn: _RetainedTurn, exc: BaseException) -> dict:
    text = str(exc) or type(exc).__name__
    lower = text.lower()
    known_client_error = any(
        marker in lower
        for marker in (
            "status code 4",
            "http 4",
            "bad request",
            "forbidden",
            "unauthorized",
            "not found",
            "permission denied",
            "validation",
        )
    )
    ambiguous = isinstance(exc, (ConnectionError, TimeoutError, OSError)) or (
        isinstance(exc, DataikuException) and not known_client_error
    )
    payload = {
        "status": "error",
        "error_kind": (
            "transport_outcome_unknown" if ambiguous else "definitive_error"
        ),
        "message": text,
        "conversation_id": turn.conversation_id,
        "turn_id": turn.turn_id,
        "instance_name": turn.instance_name,
        "project_key": turn.project_key,
    }
    if ambiguous:
        payload["next_action"] = (
            "Do not resend a mutating instruction blindly. Inspect project state "
            "or use a read-only follow-up first."
        )
    return _bound_terminal_payload(payload, turn.entry)


def _execute_turn(turn: _RetainedTurn) -> dict:
    with turn.entry.turn_lock:
        turn.entry.conversation.client = turn.client
        if turn.kind == "message":
            response = turn.entry.conversation.send_message(
                turn.message,
                allow_edit_project=turn.allow_edit_project,
            )
        else:
            # claim_turn consumed this exact id from durable state before the
            # worker became visible. Restore it only for the SDK's one POST.
            turn.entry.conversation._pending_confirmation_id = turn.confirmation_id
            response = turn.entry.conversation.answer_confirmation(turn.choice)
        return _response_payload(turn, response)


def _try_finalize(turn: _RetainedTurn) -> None:
    """Persist the terminal result, then release ownership; retryable on polls."""
    with turn.finalize_lock:
        if turn.terminal_persisted or turn.result_payload is None:
            return
        try:
            if not turn.result_persisted:
                turn.store.record_turn_result(
                    turn.conversation_id,
                    turn.turn_id,
                    turn.result_payload,
                    instance_name=turn.instance_name,
                    project_key=turn.project_key,
                    owner_fingerprint=turn.owner_fingerprint,
                )
                turn.result_persisted = True
            if not turn.claim.released:
                turn.claim.release()
            turn.terminal_persisted = turn.result_persisted and turn.claim.released
            turn.persistence_error = None
        except BaseException as exc:
            turn.persistence_error = str(exc) or type(exc).__name__
            _logger.exception(
                "Could not finalize Cobuild turn %s for conversation %s",
                turn.turn_id,
                turn.conversation_id,
            )


def _settle_turn(turn: _RetainedTurn) -> None:
    """Capture and durably finalize one completed Future exactly once.

    A Future marks itself done before invoking callbacks. The async waiter may
    therefore wake while the completion callback is still being scheduled.
    Both paths call this function so neither relies on callback timing.
    """
    if not turn.future.done():
        return
    with _registry_lock:
        if turn.result_payload is None:
            try:
                turn.result_payload = turn.future.result()
            except BaseException as exc:  # defensive: runner normally catches all
                turn.result_payload = _exception_payload(turn, exc)
            turn.settled_at = time.monotonic()
    _try_finalize(turn)


def _on_turn_done(turn: _RetainedTurn, _future: concurrent.futures.Future) -> None:
    _settle_turn(turn)


def _run_turn_thread(turn: _RetainedTurn, context: contextvars.Context) -> None:
    try:
        payload = context.run(_execute_turn, turn)
    except BaseException as exc:
        payload = _exception_payload(turn, exc)
    turn.future.set_result(payload)


def _sweep_settled_locked(now: float) -> None:
    """Evict only finalized turns; a running/unfinished thread keeps its locks."""
    finalized = [
        turn
        for turn in _turns.values()
        if turn.terminal_persisted and turn.settled_at is not None
    ]
    finalized.sort(key=lambda turn: turn.settled_at or 0)
    remove = {
        turn.conversation_id
        for turn in finalized
        if now - (turn.settled_at or now) > _SETTLED_TURN_TTL_SECONDS
    }
    excess = max(0, len(finalized) - _MAX_SETTLED_TURNS)
    remove.update(turn.conversation_id for turn in finalized[:excess])
    for conversation_id in remove:
        turn = _turns.get(conversation_id)
        if turn is not None and turn.terminal_persisted:
            del _turns[conversation_id]


def _begin_turn(
    entry: _CobuildConversationEntry,
    client: object,
    *,
    conversation_id: str,
    kind: str,
    allow_edit_project: bool,
    rehydrated: bool,
    message: str | None = None,
    choice: str | None = None,
    confirmation_id: str | None = None,
) -> _RetainedTurn:
    """Reserve the turn atomically, persist it, register it, then start work."""
    with _registry_lock:
        _sweep_settled_locked(time.monotonic())
        existing = _turns.get(conversation_id)
        if existing is not None and (
            not existing.future.done()
            or not existing.terminal_persisted
            or not existing.claim.released
        ):
            raise _TurnAlreadyActive(existing)

        turn_id = uuid.uuid4().hex
        store = _store()
        claim, proposal = store.claim_turn(
            conversation_id,
            turn_id,
            instance_name=entry.instance_name,
            project_key=entry.project_key,
            owner_fingerprint=entry.owner_fingerprint,
            kind=kind,
            allow_edit_project=allow_edit_project,
            max_concurrent_turns=MAX_CONCURRENT_COBUILD_TURNS,
            confirmation_id=confirmation_id,
            allow_lost_recovery=(kind == "message" and not allow_edit_project),
        )
        if proposal is not None:
            confirmation_id = str(proposal["confirmation_id"])

        future: concurrent.futures.Future = concurrent.futures.Future()
        # Mark the Future running before it becomes visible to an asyncio
        # wrapper. Cancelling an MCP wait must never cancel the authoritative
        # worker in the small window before its thread begins executing.
        future.set_running_or_notify_cancel()
        turn = _RetainedTurn(
            turn_id=turn_id,
            conversation_id=conversation_id,
            project_key=entry.project_key,
            instance_name=entry.instance_name,
            owner_fingerprint=entry.owner_fingerprint,
            kind=kind,
            allow_edit_project=allow_edit_project,
            entry=entry,
            client=client,
            store=store,
            claim=claim,
            future=future,
            started_at=time.monotonic(),
            rehydrated=rehydrated,
            message=message,
            choice=choice,
            confirmation_id=confirmation_id,
        )
        _turns[conversation_id] = turn
        future.add_done_callback(lambda completed: _on_turn_done(turn, completed))
        context = contextvars.copy_context()
        thread = threading.Thread(
            target=_run_turn_thread,
            args=(turn, context),
            name=f"cobuild-{turn_id[:10]}",
            daemon=True,
        )
        turn.thread = thread
        try:
            thread.start()
        except BaseException as exc:
            future.set_result(_exception_payload(turn, exc))
        return turn


def _progress_payload(turn: _RetainedTurn, *, status: str = "in_progress") -> dict:
    elapsed = max(0.0, time.monotonic() - turn.started_at)
    overdue = elapsed > MAX_COBUILD_TIMEOUT_SECONDS
    return {
        "status": status,
        "conversation_id": turn.conversation_id,
        "turn_id": turn.turn_id,
        "instance_name": turn.instance_name,
        "project_key": turn.project_key,
        "elapsed_seconds": round(elapsed, 3),
        "overdue": overdue,
        "next_action": (
            "This worker still owns the turn and its capacity slot. Poll again; "
            "if it is genuinely wedged, investigate DSS state before restarting "
            "the MCP process. Do not release lock files or resend the instruction."
            if overdue
            else "Poll get_cobuild_turn_status with this conversation_id and "
            "turn_id. Do not resend the instruction."
        ),
    }


def _terminal_payload_for_client(turn: _RetainedTurn) -> dict:
    result = dict(turn.result_payload or {})
    if turn.persistence_error:
        if result.get("status") == "needs_confirmation":
            return {
                "status": "finalization_pending",
                "conversation_id": turn.conversation_id,
                "turn_id": turn.turn_id,
                "instance_name": turn.instance_name,
                "project_key": turn.project_key,
                "message": (
                    "Cobuild returned a deletion proposal, but it could not yet "
                    "be stored safely. The proposal is not approvable until a "
                    "poll persists and returns it in full."
                ),
                "next_action": (
                    "Poll get_cobuild_turn_status with this conversation_id and "
                    "turn_id; do not resend or answer the proposal yet."
                ),
            }
        result["durability_status"] = "finalization_pending"
        result["durability_message"] = (
            "The turn finished, but its terminal record could not yet be persisted. "
            "Polling will retry; a new turn remains blocked meanwhile."
        )
    return result


async def _wait_for_turn(turn: _RetainedTurn, timeout_seconds: int) -> dict:
    wrapped = asyncio.wrap_future(turn.future)
    done, _pending = await asyncio.wait({wrapped}, timeout=float(timeout_seconds))
    if not done:
        return _progress_payload(turn, status="timeout")
    await wrapped
    await run_blocking(_settle_turn, turn)
    return _terminal_payload_for_client(turn)


def _validate_timeout(timeout_seconds: int) -> int:
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    if timeout_seconds > MAX_COBUILD_TIMEOUT_SECONDS:
        raise ValueError(
            f"'timeout_seconds' must be <= {MAX_COBUILD_TIMEOUT_SECONDS}"
        )
    return timeout_seconds


def _lost_payload(conversation_id: str, turn_id: str | None = None) -> dict:
    return omit_empty(
        {
            "status": "turn_lost",
            "error_kind": "transport_outcome_unknown",
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "message": (
                "A previous process exited while this conversation was in flight. "
                "Inspect project state before deciding whether to retry a mutation."
            ),
        }
    )


@mcp.tool()
async def start_cobuild_conversation(project_key: str, ctx: Context) -> str:
    """Start and durably register one Cobuild conversation for a project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    instance_name, client, owner_fingerprint = _capture_binding()
    await ctx.info(f"Starting Cobuild conversation for project {project_key}...")

    def _run():
        project = client.get_project(project_key)
        conversation = project.new_cobuild_conversation()
        created_at = datetime.now(timezone.utc).isoformat()
        entry = _CobuildConversationEntry(
            instance_name=instance_name,
            project_key=project_key,
            owner_fingerprint=owner_fingerprint,
            conversation=conversation,
            created_at=created_at,
        )
        _store().register(
            conversation.conversation_id,
            {
                "instance_name": instance_name,
                "project_key": project_key,
                "owner_fingerprint": owner_fingerprint,
                "created_at": created_at,
                "pending_confirmation_id": None,
                "pending_objects_to_delete": None,
                "pending_deletion_impacts": None,
                "last_turn_id": None,
                "last_turn_status": "idle",
                "last_result": None,
            },
        )
        _remember(conversation.conversation_id, entry, replace=True)
        return {
            "conversation_id": conversation.conversation_id,
            "instance_name": instance_name,
            "project_key": project_key,
            "created_at": created_at,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def send_cobuild_message(
    conversation_id: str,
    project_key: str,
    message: str,
    ctx: Context,
    allow_edit_project: bool = False,
    timeout_seconds: int = DEFAULT_COBUILD_TIMEOUT_SECONDS,
) -> str:
    """Start one retained Cobuild turn; editing is opt-in for this message.

    A timeout stops waiting, not the worker. Poll the returned ``turn_id`` with
    ``get_cobuild_turn_status``; never resend a timed-out instruction.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    message = _require_non_empty_string(message, "message")
    timeout_seconds = _validate_timeout(timeout_seconds)
    instance_name, client, owner_fingerprint = _capture_binding()
    entry, rehydrated = await run_blocking(
        _resolve_conversation_entry,
        conversation_id,
        project_key,
        instance_name,
        client,
        owner_fingerprint,
    )
    await ctx.info(f"Starting Cobuild turn for conversation {conversation_id}...")
    try:
        turn = await run_blocking(
            _begin_turn,
            entry,
            client,
            conversation_id=conversation_id,
            kind="message",
            allow_edit_project=allow_edit_project,
            rehydrated=rehydrated,
            message=message,
        )
    except _TurnAlreadyActive as exc:
        return compact_json(_progress_payload(exc.turn))
    except ConversationTurnBusy:
        return compact_json(
            {
                "status": "in_progress",
                "conversation_id": conversation_id,
                "message": "Another live MCP process owns this conversation turn.",
                "next_action": "Poll get_cobuild_turn_status; do not resend.",
            }
        )
    except ConversationTurnSaturated as exc:
        return compact_json(
            {
                "status": "error",
                "error_kind": "saturated",
                "capacity": exc.capacity,
                "message": "Cobuild turn capacity is full; no turn was started.",
                "next_action": "Wait for a running turn to finish, then retry once.",
            }
        )
    except ConversationTurnLost:
        return compact_json(_lost_payload(conversation_id))
    return compact_json(await _wait_for_turn(turn, timeout_seconds))


@mcp.tool()
async def answer_cobuild_confirmation(
    conversation_id: str,
    project_key: str,
    choice: str,
    confirmation_id: str,
    ctx: Context,
    timeout_seconds: int = DEFAULT_COBUILD_TIMEOUT_SECONDS,
) -> str:
    """Answer one exact, persisted deletion proposal with APPROVE or CANCEL."""
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    choice = _require_non_empty_string(choice, "choice")
    confirmation_id = _require_non_empty_string(confirmation_id, "confirmation_id")
    timeout_seconds = _validate_timeout(timeout_seconds)
    if choice not in {"APPROVE", "CANCEL"}:
        raise ValueError("choice must be 'APPROVE' or 'CANCEL'")
    instance_name, client, owner_fingerprint = _capture_binding()
    entry, rehydrated = await run_blocking(
        _resolve_conversation_entry,
        conversation_id,
        project_key,
        instance_name,
        client,
        owner_fingerprint,
    )
    await ctx.info(
        f"Starting confirmation turn for conversation {conversation_id} with {choice}..."
    )
    try:
        turn = await run_blocking(
            _begin_turn,
            entry,
            client,
            conversation_id=conversation_id,
            kind="confirmation",
            allow_edit_project=True,
            rehydrated=rehydrated,
            choice=choice,
            confirmation_id=confirmation_id,
        )
    except _TurnAlreadyActive as exc:
        return compact_json(_progress_payload(exc.turn))
    except ConversationTurnBusy:
        return compact_json(
            {
                "status": "in_progress",
                "conversation_id": conversation_id,
                "message": "Another live MCP process owns this conversation turn.",
                "next_action": "Poll get_cobuild_turn_status; do not answer twice.",
            }
        )
    except ConversationTurnSaturated as exc:
        return compact_json(
            {
                "status": "error",
                "error_kind": "saturated",
                "capacity": exc.capacity,
                "message": "Cobuild turn capacity is full; no answer was sent.",
            }
        )
    except ConversationTurnLost:
        return compact_json(_lost_payload(conversation_id))
    return compact_json(await _wait_for_turn(turn, timeout_seconds))


@mcp.tool()
async def get_cobuild_turn_status(
    conversation_id: str,
    project_key: str,
    ctx: Context,
    turn_id: str = "",
) -> str:
    """Poll a retained turn or recover its authenticated durable outcome.

    Pass the ``turn_id`` returned by send/answer to ensure a later turn cannot be
    mistaken for the one being polled. Omitting it returns the latest turn for
    backward compatibility.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    turn_id = turn_id.strip()
    instance_name, _client, owner_fingerprint = _capture_binding()
    await ctx.info(f"Polling Cobuild conversation {conversation_id}...")

    with _registry_lock:
        local = _turns.get(conversation_id)
    if local is not None:
        if (
            local.project_key != project_key
            or local.instance_name != instance_name
            or not hmac.compare_digest(local.owner_fingerprint, owner_fingerprint)
        ):
            raise ValueError(
                f"Unknown Cobuild conversation_id '{conversation_id}' for the "
                "current credential, instance, and project."
            )
        if turn_id and not hmac.compare_digest(local.turn_id, turn_id):
            raise ValueError(
                f"turn_id '{turn_id}' is not the latest turn for conversation "
                f"'{conversation_id}'."
            )
        if not local.future.done():
            return compact_json(_progress_payload(local))
        await run_blocking(_settle_turn, local)
        return compact_json(_terminal_payload_for_client(local))

    record, live_external = await run_blocking(
        _store().inspect_turn,
        conversation_id,
        instance_name=instance_name,
        project_key=project_key,
        owner_fingerprint=owner_fingerprint,
    )
    latest_turn_id = str(record.get("last_turn_id") or "")
    if turn_id and not hmac.compare_digest(latest_turn_id, turn_id):
        raise ValueError(
            f"turn_id '{turn_id}' is not the latest turn for conversation "
            f"'{conversation_id}'."
        )
    if live_external:
        return compact_json(
            omit_empty(
                {
                    "status": "in_progress",
                    "conversation_id": conversation_id,
                    "turn_id": latest_turn_id,
                    "message": "Another live MCP process still owns this turn.",
                    "next_action": "Poll again; do not resend.",
                }
            )
        )
    result = record.get("last_result")
    if isinstance(result, dict):
        return compact_json(result)
    if record.get("pending_confirmation_id"):
        return compact_json(
            omit_empty(
                {
                    "status": "needs_confirmation",
                    "conversation_id": conversation_id,
                    "turn_id": latest_turn_id,
                    "confirmation_id": record.get("pending_confirmation_id"),
                    "objects_to_delete": record.get("pending_objects_to_delete"),
                    "deletion_impacts": record.get("pending_deletion_impacts"),
                    "next_action": (
                        "Inspect this complete proposal, then answer its exact "
                        "confirmation_id with APPROVE or CANCEL."
                    ),
                }
            )
        )
    return compact_json(
        {
            "status": str(record.get("last_turn_status") or "idle"),
            "conversation_id": conversation_id,
            "turn_id": latest_turn_id,
        }
    )


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List this credential's durable conversations without approval tokens."""
    project_key = _require_non_empty_string(project_key, "project_key")
    instance_name, _client, owner_fingerprint = _capture_binding()
    await ctx.info(f"Listing Cobuild conversations for project {project_key}...")
    records = await run_blocking(
        _store().list_owned,
        instance_name=instance_name,
        project_key=project_key,
        owner_fingerprint=owner_fingerprint,
    )
    rows = [
        {
            "conversation_id": conversation_id,
            "instance_name": record.get("instance_name"),
            "project_key": record.get("project_key"),
            "created_at": record.get("created_at"),
            "last_turn_status": record.get("last_turn_status"),
            "last_turn_id": record.get("last_turn_id"),
            "has_pending_confirmation": bool(
                record.get("pending_confirmation_id")
            ),
        }
        for conversation_id, record in records.items()
    ]
    return compact_json(
        {
            "conversations": columnar(
                rows,
                [
                    "conversation_id",
                    "instance_name",
                    "project_key",
                    "created_at",
                    "last_turn_status",
                    "last_turn_id",
                    "has_pending_confirmation",
                ],
            )
        }
    )
