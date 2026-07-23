"""Cobuild conversation tools with process-local retained turns.

The DSS Cobuild API is synchronous while one turn can run for minutes. A turn
therefore runs in a dedicated daemon thread whose ``concurrent.futures.Future``
stays registered after the calling MCP request stops waiting. A wait timeout
ends only the client's wait, never the worker: the caller polls the returned
``turn_id`` with ``get_cobuild_turn_status`` and must never resend a timed-out
mutation.

Everything here is process-local. Conversations, retained turns, and pending
deletion proposals live only in this process's memory: there is no durable
store, no cross-process coordination, and no lock files. A server restart drops
all of it; the correct recovery is to start a new conversation. Edits are opt-in
per message (``allow_edit_project`` defaults to ``False``) and deletion consent
is bound to the exact pending proposal id.

A turn accepted but never observed by its client (for example a cancelled MCP
request) stays discoverable: each conversation retains its latest ``turn_id``,
``list_cobuild_conversations`` exposes it, and a conversation whose latest turn
was never delivered to any client is protected from cap eviction. Recovery
after an interrupted send is list-then-poll-the-exact-id, never a blind resend;
``get_cobuild_turn_status`` also resolves the current latest turn when
``turn_id`` is omitted, as a convenience whose returned ``turn_id`` the caller
must compare.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import threading
import time
import uuid

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)
from .utils.validation import require_positive_int as _require_positive_int

_logger = logging.getLogger(__name__)

# Wait-timeout controls. A wait expiring returns a pollable turn id; it never
# cancels the worker. These are plain module constants: v1 is single-process,
# single-credential, so there is no env-var/cross-process capacity machinery.
DEFAULT_COBUILD_TIMEOUT_SECONDS = 1200
MAX_COBUILD_TIMEOUT_SECONDS = 1800

# Global concurrency cap on in-flight turns, enforced with a plain bounded
# semaphore. A send that cannot claim a slot is refused outright (no queueing).
MAX_CONCURRENT_COBUILD_TURNS = 3

# Terminal payloads are size-checked flat in the worker thread, before retention
# and before any event-loop serialization, so an oversized result can never stall
# the loop or accumulate in the registry. An oversized deletion proposal is
# disarmed, never truncated: the pending confirmation is answered CANCEL in DSS
# and its id withheld, so an un-inspectable deletion cannot be approved. An
# ordinary oversized response is clipped with explicit truncation metadata.
# Replacement payloads are re-measured after construction so the ceiling holds
# even against pathological server-supplied strings.
_MAX_TERMINAL_RESULT_BYTES = 512_000
_TRUNCATED_MESSAGE_CHARS = 2_000

# Bounds on the settled-turn registry so a long-lived process does not retain
# every terminal turn forever. A running turn is never swept, and a settled
# needs_confirmation turn is pinned outside TTL and count while its deletion
# proposal stays armed, so the exact confirmation id remains retrievable and
# answerable until the proposal is answered or cancelled.
_SETTLED_TURN_TTL_SECONDS = 3600
_MAX_SETTLED_TURNS = 64

# Bound on the conversation registry, enforced before any remote conversation
# is created. A conversation with an in-flight turn, an armed deletion
# confirmation, or a latest turn whose result was never delivered to a client
# is never evicted, so no active work, pending approval, or unobserved mutation
# is dropped; other idle handles are evicted oldest-first to make room, and
# creation is refused outright (without touching DSS) when nothing is
# evictable.
_MAX_CONVERSATIONS = 128


@dataclass
class _CobuildConversationEntry:
    instance_name: str
    project_key: str
    conversation: object
    created_at: str
    # The turn_id of the one in-flight turn for this conversation, or None.
    active_turn_id: str | None = None
    # The most recent turn started for this conversation, active or settled.
    # Never cleared at settlement: a client whose wait was cancelled recovers
    # the turn through this id via list_cobuild_conversations or a latest-turn
    # poll instead of blindly resending the instruction.
    last_turn_id: str | None = None
    # True once the latest turn's id has been delivered to a client through the
    # public surface (the awaited send/answer returned a terminal, timeout, or
    # busy payload, or get_cobuild_turn_status returned this turn). While False,
    # the conversation is never cap-evicted: evicting it would make an accepted,
    # unobserved mutation undiscoverable.
    last_turn_observed: bool = False
    # Number of in-flight tool requests that resolved this entry and are about
    # to start a turn on it. While positive the entry is never evicted, closing
    # the window between resolution and turn activation.
    admission_pins: int = 0


@dataclass
class _RetainedTurn:
    turn_id: str
    conversation_id: str
    project_key: str
    instance_name: str
    kind: str
    allow_edit_project: bool
    entry: _CobuildConversationEntry
    client: object
    future: concurrent.futures.Future
    started_at: float
    message: str | None = None
    choice: str | None = None
    confirmation_id: str | None = None
    settled_at: float | None = None
    result_payload: dict | None = None
    semaphore_released: bool = False
    thread: threading.Thread | None = None


class _TurnAlreadyActive(RuntimeError):
    """A turn is already in flight for this conversation; do not start another."""

    def __init__(self, turn: _RetainedTurn):
        super().__init__("A turn is already in flight for this conversation.")
        self.turn = turn


class _TurnSaturated(RuntimeError):
    """The global in-flight turn capacity is full; no turn was started."""

    def __init__(self, capacity: int):
        super().__init__("Cobuild turn capacity is full.")
        self.capacity = capacity


_conversations: dict[str, _CobuildConversationEntry] = {}
_turns: dict[str, _RetainedTurn] = {}  # keyed by turn_id
_registry_lock = threading.RLock()
_turn_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_COBUILD_TURNS)


def _capture_binding() -> tuple[str, object]:
    """Capture instance name and client from ONE immutable snapshot at tool entry.

    Both the name and the client are derived from a single
    ``config.get_current_instance()`` read and threaded through together. A
    concurrent ``switch_instance`` between two separate reads previously could
    yield a name from instance A paired with a client for instance B; deriving
    both from one snapshot makes the pair atomic. Resolving the client here (in
    the request context) and threading it through also means an in-flight switch
    cannot retarget a running turn.
    """
    instance = config.get_current_instance()
    return instance.name, get_dss_client(instance=instance)


def _guard_entry(
    conversation_id: str,
    entry: _CobuildConversationEntry,
    *,
    project_key: str,
    instance_name: str,
) -> None:
    if entry.project_key != project_key:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to project "
            f"'{entry.project_key}', not '{project_key}'."
        )
    if entry.instance_name != instance_name:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to instance "
            f"'{entry.instance_name}', but the active instance is '{instance_name}'. "
            "Switch back to the original instance before reusing this conversation."
        )


def _resolve_conversation_entry(
    conversation_id: str,
    project_key: str,
    instance_name: str,
    *,
    pin: bool = False,
) -> _CobuildConversationEntry:
    """Look up a process-local conversation handle and check ownership.

    There is no durable store to rehydrate from: an unknown id means the
    conversation was never started in this process (or the process restarted).

    With ``pin=True`` the entry is marked in-admission inside the same lock
    acquisition that resolves it, so a concurrent creation cannot evict it in
    the gap between resolution and turn activation. The caller must release
    the pin with ``_unpin_entry`` once the turn is active or the attempt
    failed.
    """
    with _registry_lock:
        entry = _conversations.get(conversation_id)
        if entry is None:
            raise ValueError(
                f"Unknown Cobuild conversation_id '{conversation_id}'. "
                "Conversations are process-local and do not survive a server "
                "restart. Start a new conversation first."
            )
        _guard_entry(
            conversation_id,
            entry,
            project_key=project_key,
            instance_name=instance_name,
        )
        if pin:
            entry.admission_pins += 1
    return entry


def _unpin_entry(entry: _CobuildConversationEntry) -> None:
    with _registry_lock:
        if entry.admission_pins > 0:
            entry.admission_pins -= 1


def _mark_turn_observed(turn: _RetainedTurn) -> None:
    """Record that this turn's id was delivered to a client via a public tool.

    Once the conversation's latest turn has been observed at least once, the
    conversation becomes eligible for cap eviction again; until then it is
    protected so an unobserved mutation can always be rediscovered.
    """
    with _registry_lock:
        if turn.entry.last_turn_id == turn.turn_id:
            turn.entry.last_turn_observed = True


def _require_pending_confirmation(conversation: object, confirmation_id: str) -> None:
    """Bind an approval to the exact pending proposal id before any SDK call."""
    pending = getattr(conversation, "_pending_confirmation_id", None)
    if pending is None:
        raise ValueError(
            "No pending confirmation for this conversation. Re-read a "
            "needs-confirmation response before answering."
        )
    # The confirmation id is not a secret, so a plain equality check is correct
    # here; it exists to bind the approval to the exact proposal.
    if str(pending) != confirmation_id:
        raise ValueError(
            "confirmation_id does not match the pending deletion proposal. "
            "Inspect the latest objects_to_delete and deletion_impacts, then "
            "pass its exact confirmation_id."
        )


def _json_size(payload: dict) -> int:
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))


def _bounded_replacement(payload: dict) -> dict:
    """Clip string fields until the replacement payload is provably under the
    ceiling.

    Replacement payloads embed server-supplied strings (conversation id, error
    text, clipped message), so they must be re-measured after construction: a
    pathological id could otherwise push the replacement itself over the
    ceiling. Strings start at the standard clip budget and are halved until the
    serialized payload fits; non-string fields are fixed-size. This terminates
    and guarantees the retained result respects ``_MAX_TERMINAL_RESULT_BYTES``.
    """
    limit = _TRUNCATED_MESSAGE_CHARS
    while True:
        clipped = {
            key: (value[:limit] if isinstance(value, str) else value)
            for key, value in payload.items()
        }
        if _json_size(clipped) <= _MAX_TERMINAL_RESULT_BYTES or limit <= 0:
            return clipped
        limit //= 2


def _bound_terminal_payload(payload: dict, entry: _CobuildConversationEntry) -> dict:
    """Flat size check on terminal payloads, applied in the worker thread.

    Runs off the event loop, before the payload is retained, so oversized
    results are measured and replaced without stalling the loop or filling the
    settled-turn registry. An oversized deletion proposal is never left armed
    and never truncated: the pending confirmation is answered CANCEL in DSS and
    its confirmation id withheld, so an un-inspectable deletion cannot be
    approved. If the DSS cancel fails, the proposal is still rejected locally
    and the payload reports the honest server-side state. An ordinary oversized
    response is clipped with explicit truncation metadata.
    """
    original_bytes = _json_size(payload)
    if original_bytes <= _MAX_TERMINAL_RESULT_BYTES:
        return payload
    if payload.get("status") == "needs_confirmation":
        # Actually cancel the proposal in DSS (the same SDK call that
        # answer_cobuild_confirmation uses) while it is still pending, then
        # disarm it locally regardless of the outcome.
        cancel_error = None
        try:
            entry.conversation.answer_confirmation("CANCEL")
        except BaseException as exc:
            cancel_error = str(exc) or type(exc).__name__
        entry.conversation._pending_confirmation_id = None
        replacement = {
            "status": "error",
            "error_kind": "response_too_large",
            "conversation_id": payload.get("conversation_id"),
            "turn_id": payload.get("turn_id"),
            "original_bytes": original_bytes,
        }
        if cancel_error is None:
            replacement["cancelled_confirmation"] = True
            replacement["message"] = (
                "Cobuild returned a deletion proposal too large to show "
                "completely. It was not armed for approval and its pending "
                "confirmation was cancelled in DSS. Narrow the requested "
                "deletion and ask Cobuild to propose it again."
            )
        else:
            replacement.update(
                {
                    "confirmation_disarmed_locally": True,
                    "cancel_failed": True,
                    "cancel_error": cancel_error,
                    "message": (
                        "Cobuild returned a deletion proposal too large to show "
                        "completely. It was not armed for approval in this "
                        "server, but cancelling it in DSS failed, so the "
                        "conversation may still await confirmation server-side. "
                        "Narrow the requested deletion and ask Cobuild to "
                        "propose it again."
                    ),
                }
            )
        return _bounded_replacement(replacement)
    return _bounded_replacement(
        {
            "status": "error",
            "error_kind": "response_too_large",
            "message": str(payload.get("message", "")),
            "truncated": True,
            "truncation_note": (
                "Cobuild returned a response too large to return safely; only "
                "the start of its message is shown."
            ),
            "conversation_id": payload.get("conversation_id"),
            "turn_id": payload.get("turn_id"),
            "original_bytes": original_bytes,
        }
    )


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
    # Bind the turn to the client captured at tool entry so an in-flight
    # switch_instance cannot retarget a running turn.
    turn.entry.conversation.client = turn.client
    if turn.kind == "message":
        response = turn.entry.conversation.send_message(
            turn.message,
            allow_edit_project=turn.allow_edit_project,
        )
    else:
        response = turn.entry.conversation.answer_confirmation(turn.choice)
    return _response_payload(turn, response)


def _run_turn_thread(turn: _RetainedTurn) -> None:
    try:
        payload = _execute_turn(turn)
    except BaseException as exc:  # daemon worker must never surface a raw error
        payload = _exception_payload(turn, exc)
    turn.future.set_result(payload)


def _settle_turn(turn: _RetainedTurn) -> None:
    """Capture one completed Future's result exactly once and free its slots.

    Both the completion callback and any waiter/poll call this; the
    ``result_payload is None`` guard under the registry lock makes it idempotent.
    """
    if not turn.future.done():
        return
    with _registry_lock:
        if turn.result_payload is not None:
            return
        try:
            turn.result_payload = turn.future.result()
        except BaseException as exc:  # defensive: runner normally catches all
            turn.result_payload = _exception_payload(turn, exc)
        turn.settled_at = time.monotonic()
        if turn.entry.active_turn_id == turn.turn_id:
            turn.entry.active_turn_id = None
        if not turn.semaphore_released:
            _turn_semaphore.release()
            turn.semaphore_released = True
        # Sweep at settlement too, not only before a new turn starts, so expired
        # or over-cap settled turns do not linger until later activity.
        _sweep_settled_locked(turn.settled_at)
        _evict_conversations_locked()


def _on_turn_done(turn: _RetainedTurn, _future: concurrent.futures.Future) -> None:
    _settle_turn(turn)


def _turn_is_pinned(turn: _RetainedTurn) -> bool:
    """True for a settled deletion proposal whose confirmation is still armed.

    While the proposal is armed, the turn is the only place the client can
    re-read the exact ``confirmation_id`` with its ``objects_to_delete`` and
    ``deletion_impacts``, so it is exempt from the TTL and count sweep. It
    becomes sweepable once the confirmation is answered or cancelled (the
    conversation is then no longer armed with this proposal's id).
    """
    payload = turn.result_payload
    if not payload or payload.get("status") != "needs_confirmation":
        return False
    pending = getattr(turn.entry.conversation, "_pending_confirmation_id", None)
    return bool(pending) and str(pending) == str(payload.get("confirmation_id"))


def _sweep_settled_locked(now: float) -> None:
    """Evict finalized turns by TTL and count; a running turn keeps its slot.

    Pinned turns (armed deletion proposals) are excluded from both the TTL and
    the count, so the ``_MAX_SETTLED_TURNS`` cap applies to unpinned settled
    turns only and an armed proposal can never be aged or crowded out.
    """
    settled = [
        turn
        for turn in _turns.values()
        if turn.result_payload is not None
        and turn.settled_at is not None
        and not _turn_is_pinned(turn)
    ]
    settled.sort(key=lambda turn: turn.settled_at or 0)
    remove = {
        turn.turn_id
        for turn in settled
        if now - (turn.settled_at or now) > _SETTLED_TURN_TTL_SECONDS
    }
    excess = max(0, len(settled) - _MAX_SETTLED_TURNS)
    remove.update(turn.turn_id for turn in settled[:excess])
    for turn_id in remove:
        turn = _turns.get(turn_id)
        if turn is not None and turn.result_payload is not None:
            del _turns[turn_id]


def _conversation_is_evictable(entry: _CobuildConversationEntry) -> bool:
    """True when a conversation can be dropped without losing anything.

    Not evictable while: a turn is in flight, a deletion confirmation is armed,
    a tool request has pinned the entry between resolution and turn activation,
    or the latest turn's id has never been delivered to a client (evicting it
    would make an accepted, unobserved mutation undiscoverable).
    """
    if entry.admission_pins > 0:
        return False
    active_id = entry.active_turn_id
    if active_id is not None:
        turn = _turns.get(active_id)
        if turn is not None and not turn.future.done():
            return False
    if getattr(entry.conversation, "_pending_confirmation_id", None):
        return False
    if entry.last_turn_id is not None and not entry.last_turn_observed:
        return False
    return True


def _evict_conversations_locked(
    *,
    target_len: int | None = None,
    protect: _CobuildConversationEntry | None = None,
) -> None:
    """Cap the conversation registry, evicting only idle, unconfirmed entries.

    Oldest-first by ``created_at``. A conversation with an in-flight turn or an
    armed deletion confirmation is never evicted, so no active work or pending
    approval is dropped. ``protect`` exempts the entry currently being admitted
    or used, so eviction can never race the caller and drop the very entry a
    turn is about to run on. Callers must hold ``_registry_lock``.
    """
    if target_len is None:
        target_len = _MAX_CONVERSATIONS
    if len(_conversations) <= target_len:
        return
    evictable = [
        (conversation_id, entry)
        for conversation_id, entry in _conversations.items()
        if entry is not protect and _conversation_is_evictable(entry)
    ]
    evictable.sort(key=lambda item: item[1].created_at)
    overflow = len(_conversations) - target_len
    for conversation_id, _entry in evictable[:overflow]:
        del _conversations[conversation_id]


# Slots reserved by creations that passed admission but have not yet inserted
# their conversation. Guarded by _registry_lock.
_reserved_conversation_slots = 0


def _reserve_conversation_slot_locked() -> None:
    """Enforce the registry cap BEFORE any remote conversation is created.

    Runs the eviction/refusal decision and reserves a slot under the lock, so a
    refusal never leaks a server-side DSS conversation and concurrent creations
    cannot over-admit. The caller must later insert the conversation and call
    ``_release_conversation_slot_locked`` (also on failure).
    """
    global _reserved_conversation_slots
    occupied = len(_conversations) + _reserved_conversation_slots
    if occupied >= _MAX_CONVERSATIONS:
        _evict_conversations_locked(
            target_len=max(0, _MAX_CONVERSATIONS - 1 - _reserved_conversation_slots)
        )
        occupied = len(_conversations) + _reserved_conversation_slots
    if occupied >= _MAX_CONVERSATIONS:
        raise ValueError(
            f"The Cobuild conversation registry is full ({_MAX_CONVERSATIONS}) "
            "and every retained conversation has a turn in flight, an armed "
            "deletion confirmation, or an undelivered latest turn result. "
            "Answer or cancel pending confirmations, poll undelivered turns "
            "with get_cobuild_turn_status, or wait for running turns to "
            "settle, then retry. No conversation was created in DSS."
        )
    _reserved_conversation_slots += 1


def _release_conversation_slot_locked() -> None:
    global _reserved_conversation_slots
    if _reserved_conversation_slots > 0:
        _reserved_conversation_slots -= 1


def _begin_turn(
    entry: _CobuildConversationEntry,
    client: object,
    *,
    conversation_id: str,
    kind: str,
    allow_edit_project: bool,
    message: str | None = None,
    choice: str | None = None,
    confirmation_id: str | None = None,
) -> _RetainedTurn:
    """Serialize per conversation, claim a global slot, then start the worker."""
    with _registry_lock:
        _sweep_settled_locked(time.monotonic())
        # The entry about to run a turn is protected: eviction must never drop
        # the conversation being used before its turn is marked active.
        _evict_conversations_locked(protect=entry)

        active_id = entry.active_turn_id
        if active_id is not None:
            existing = _turns.get(active_id)
            if existing is not None and not existing.future.done():
                # One in-flight turn per conversation. Never queue or duplicate a
                # mutation; the caller polls the existing turn instead.
                raise _TurnAlreadyActive(existing)
            if existing is not None:
                _settle_turn(existing)
            entry.active_turn_id = None

        # For a confirmation turn, bind to the exact pending proposal under the
        # same lock that serializes turns, so a concurrent answer is rejected as
        # busy above rather than racing this check.
        if kind == "confirmation":
            _require_pending_confirmation(entry.conversation, confirmation_id)

        if not _turn_semaphore.acquire(blocking=False):
            raise _TurnSaturated(MAX_CONCURRENT_COBUILD_TURNS)

        turn_id = uuid.uuid4().hex
        future: concurrent.futures.Future = concurrent.futures.Future()
        # Mark the Future running before an asyncio wrapper can see it, so
        # cancelling an MCP wait never cancels the authoritative worker.
        future.set_running_or_notify_cancel()
        turn = _RetainedTurn(
            turn_id=turn_id,
            conversation_id=conversation_id,
            project_key=entry.project_key,
            instance_name=entry.instance_name,
            kind=kind,
            allow_edit_project=allow_edit_project,
            entry=entry,
            client=client,
            future=future,
            started_at=time.monotonic(),
            message=message,
            choice=choice,
            confirmation_id=confirmation_id,
        )
        _turns[turn_id] = turn
        entry.active_turn_id = turn_id
        entry.last_turn_id = turn_id
        entry.last_turn_observed = False
        future.add_done_callback(lambda completed: _on_turn_done(turn, completed))
        thread = threading.Thread(
            target=_run_turn_thread,
            args=(turn,),
            name=f"cobuild-{turn_id[:10]}",
            daemon=True,
        )
        turn.thread = thread
        try:
            thread.start()
        except BaseException as exc:
            future.set_result(_exception_payload(turn, exc))
        return turn


def _progress_payload(turn: _RetainedTurn, *, status: str) -> dict:
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
            "Poll get_cobuild_turn_status with this conversation_id and turn_id. "
            "The worker is still authoritative; do not resend the instruction."
        ),
    }


def _busy_payload(turn: _RetainedTurn, *, verb: str) -> dict:
    return {
        "status": "busy",
        "conversation_id": turn.conversation_id,
        "turn_id": turn.turn_id,
        "message": (
            "A Cobuild turn is already in flight for this conversation; the new "
            f"instruction was not {verb}."
        ),
        "next_action": (
            "Poll get_cobuild_turn_status with this turn_id; do not resend."
        ),
    }


def _saturated_payload(conversation_id: str, capacity: int, *, verb: str) -> dict:
    return {
        "status": "error",
        "error_kind": "saturated",
        "capacity": capacity,
        "conversation_id": conversation_id,
        "message": f"Cobuild turn capacity is full; no turn was {verb}.",
        "next_action": "Wait for a running turn to finish, then retry once.",
    }


def _validate_timeout(timeout_seconds: int) -> int:
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    if timeout_seconds > MAX_COBUILD_TIMEOUT_SECONDS:
        raise ValueError(f"'timeout_seconds' must be <= {MAX_COBUILD_TIMEOUT_SECONDS}")
    return timeout_seconds


async def _wait_for_turn(turn: _RetainedTurn, timeout_seconds: int) -> dict:
    wrapped = asyncio.wrap_future(turn.future)
    done, _pending = await asyncio.wait({wrapped}, timeout=float(timeout_seconds))
    if not done:
        # The timeout payload carries the turn_id, so the client has observed
        # the turn. A cancelled wait never reaches this point.
        _mark_turn_observed(turn)
        return _progress_payload(turn, status="timeout")
    _settle_turn(turn)
    _mark_turn_observed(turn)
    return turn.result_payload


@mcp.tool()
async def start_cobuild_conversation(project_key: str, ctx: Context) -> str:
    """Start a new process-local Cobuild conversation for a project.

    The conversation lives only in this server process; a restart drops it and
    the correct recovery is to start a new one.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    instance_name, client = _capture_binding()
    await ctx.info(f"Starting Cobuild conversation for project {project_key}...")

    def _run():
        # Admission (eviction or refusal) happens BEFORE the SDK call, so a
        # refused creation never leaks a server-side DSS conversation.
        with _registry_lock:
            _reserve_conversation_slot_locked()
        try:
            project = client.get_project(project_key)
            conversation = project.new_cobuild_conversation()
            created_at = datetime.now(timezone.utc).isoformat()
            entry = _CobuildConversationEntry(
                instance_name=instance_name,
                project_key=project_key,
                conversation=conversation,
                created_at=created_at,
            )
            with _registry_lock:
                _conversations[conversation.conversation_id] = entry
            return {
                "conversation_id": conversation.conversation_id,
                "instance_name": instance_name,
                "project_key": project_key,
                "created_at": created_at,
            }
        finally:
            with _registry_lock:
                _release_conversation_slot_locked()

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
    """Start one retained Cobuild turn; project editing is opt-in for this message.

    ``allow_edit_project`` defaults to ``False`` (read-only supervision); pass
    ``True`` only for the single message allowed to create or edit project
    objects. A wait that reaches ``timeout_seconds`` stops the wait, not the
    worker: poll the returned ``turn_id`` with ``get_cobuild_turn_status`` and
    never resend a timed-out instruction.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    message = _require_non_empty_string(message, "message")
    timeout_seconds = _validate_timeout(timeout_seconds)
    instance_name, client = _capture_binding()
    # pin=True marks the entry in-admission inside the resolve lock, so a
    # concurrent creation cannot evict it before the turn is marked active.
    entry = await run_blocking(
        _resolve_conversation_entry,
        conversation_id,
        project_key,
        instance_name,
        pin=True,
    )
    try:
        await ctx.info(f"Starting Cobuild turn for conversation {conversation_id}...")
        turn = await run_blocking(
            _begin_turn,
            entry,
            client,
            conversation_id=conversation_id,
            kind="message",
            allow_edit_project=allow_edit_project,
            message=message,
        )
    except _TurnAlreadyActive as exc:
        _mark_turn_observed(exc.turn)
        return compact_json(_busy_payload(exc.turn, verb="sent"))
    except _TurnSaturated as exc:
        return compact_json(
            _saturated_payload(conversation_id, exc.capacity, verb="started")
        )
    finally:
        _unpin_entry(entry)
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
    """Answer the exact pending deletion proposal with APPROVE or CANCEL.

    ``confirmation_id`` is required and must match the id returned with the
    proposal's ``objects_to_delete`` and ``deletion_impacts``. A mismatched or
    already-consumed id is rejected before any SDK call, so an ambiguous
    transport failure cannot be retried as a blind second approval. The answer
    runs as a retained turn; a wait timeout returns a pollable ``turn_id``.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    choice = _require_non_empty_string(choice, "choice")
    confirmation_id = _require_non_empty_string(confirmation_id, "confirmation_id")
    timeout_seconds = _validate_timeout(timeout_seconds)
    if choice not in {"APPROVE", "CANCEL"}:
        raise ValueError("choice must be 'APPROVE' or 'CANCEL'")
    instance_name, client = _capture_binding()
    # pin=True marks the entry in-admission inside the resolve lock, so a
    # concurrent creation cannot evict it before the turn is marked active.
    entry = await run_blocking(
        _resolve_conversation_entry,
        conversation_id,
        project_key,
        instance_name,
        pin=True,
    )
    try:
        await ctx.info(
            f"Answering Cobuild confirmation for conversation {conversation_id} "
            f"with {choice}..."
        )
        turn = await run_blocking(
            _begin_turn,
            entry,
            client,
            conversation_id=conversation_id,
            kind="confirmation",
            allow_edit_project=True,
            choice=choice,
            confirmation_id=confirmation_id,
        )
    except _TurnAlreadyActive as exc:
        _mark_turn_observed(exc.turn)
        return compact_json(_busy_payload(exc.turn, verb="answered"))
    except _TurnSaturated as exc:
        return compact_json(
            _saturated_payload(conversation_id, exc.capacity, verb="answered")
        )
    finally:
        _unpin_entry(entry)
    return compact_json(await _wait_for_turn(turn, timeout_seconds))


@mcp.tool()
async def get_cobuild_turn_status(
    conversation_id: str,
    project_key: str,
    ctx: Context,
    turn_id: str = "",
) -> str:
    """Poll one retained turn: ``in_progress`` or its terminal outcome.

    Pass the exact ``turn_id`` returned by ``send_cobuild_message``,
    ``answer_cobuild_confirmation``, or a listing's ``last_turn_id``; that is
    the reliable form. Omitting ``turn_id`` is a convenience that polls
    whatever the conversation's latest turn is at that moment, which may be a
    newer turn than one seen in an earlier listing, so always compare the
    ``turn_id`` carried in the result against the id you expected. Turns are
    process-local; a ``turn_id`` from a previous server process is unknown
    here, and settled turns other than armed deletion proposals are retained
    only for a bounded time.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    turn_id = (turn_id or "").strip()
    instance_name, _client = _capture_binding()

    if not turn_id:
        entry = await run_blocking(
            _resolve_conversation_entry, conversation_id, project_key, instance_name
        )
        with _registry_lock:
            latest = entry.last_turn_id
        if latest is None:
            raise ValueError(
                f"No Cobuild turns recorded for conversation '{conversation_id}' "
                "in this process."
            )
        turn_id = latest

    await ctx.info(
        f"Polling Cobuild turn {turn_id} for conversation {conversation_id}..."
    )

    with _registry_lock:
        turn = _turns.get(turn_id)
    if turn is None:
        raise ValueError(
            f"Unknown Cobuild turn_id '{turn_id}'. Turns are process-local, do "
            "not survive a server restart, and settled turns other than armed "
            "deletion proposals are retained only for a bounded time. Check "
            "list_cobuild_conversations for the conversation's last_turn_id "
            "and its state before re-sending anything."
        )
    if (
        turn.conversation_id != conversation_id
        or turn.project_key != project_key
        or turn.instance_name != instance_name
    ):
        raise ValueError(
            f"Cobuild turn_id '{turn_id}' does not match the given conversation, "
            "project, and active instance."
        )
    _mark_turn_observed(turn)
    if not turn.future.done():
        return compact_json(_progress_payload(turn, status="in_progress"))
    _settle_turn(turn)
    return compact_json(turn.result_payload)


def _last_turn_status_locked(last_turn_id: str | None) -> str | None:
    """Status of a conversation's latest turn, or None if it was never started
    or its settled record has been swept. Callers must hold ``_registry_lock``."""
    if not last_turn_id:
        return None
    turn = _turns.get(last_turn_id)
    if turn is None:
        return None
    if not turn.future.done():
        return "in_progress"
    _settle_turn(turn)
    return (turn.result_payload or {}).get("status")


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List retained Cobuild conversations in the project for this process.

    Each row carries the conversation's ``last_turn_id`` and its status. After
    a cancelled or interrupted send, this is the recovery path: list, read the
    conversation's ``last_turn_id``, and poll it with
    ``get_cobuild_turn_status`` before ever re-sending an instruction.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(
        f"Listing retained Cobuild conversations for project {project_key}..."
    )

    current_instance_name = config.get_current_instance_name()
    rows = []
    with _registry_lock:
        for conversation_id, entry in list(_conversations.items()):
            if (
                entry.instance_name != current_instance_name
                or entry.project_key != project_key
            ):
                continue
            rows.append(
                {
                    "conversation_id": conversation_id,
                    "instance_name": entry.instance_name,
                    "project_key": entry.project_key,
                    "created_at": entry.created_at,
                    "last_turn_id": entry.last_turn_id,
                    "last_turn_status": _last_turn_status_locked(entry.last_turn_id),
                    "has_pending_confirmation": bool(
                        getattr(entry.conversation, "_pending_confirmation_id", None)
                    ),
                }
            )

    return compact_json(
        {
            "conversations": columnar(
                rows,
                [
                    "conversation_id",
                    "instance_name",
                    "project_key",
                    "created_at",
                    "last_turn_id",
                    "last_turn_status",
                    "has_pending_confirmation",
                ],
            )
        }
    )
