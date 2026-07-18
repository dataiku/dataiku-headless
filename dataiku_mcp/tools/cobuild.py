"""Cobuild conversation tools.

Cobuild is the AI assistant that runs *inside* a DSS instance. These tools are
this server's write door for in-project building: instead of exposing direct
create/edit/delete tools, project mutations are delegated to Cobuild over the
DSS public API.

A Cobuild turn (``send_message`` / ``answer_confirmation``) can run for minutes,
so the design here has three moving parts beyond a naive call:

* A **durable registry** (``conversations.json`` under ``DKU_MCP_STATE_DIR``)
  persists the metadata needed to rehydrate a thin conversation handle after a
  process restart. The in-memory dict is only a hot cache of live handles.
* **Retained-turn timeout machinery**: the blocking turn runs in a daemon thread
  whose Future is retained, so a client-side timeout returns control without
  dropping the work; ``get_cobuild_turn_status`` later settles it.
* **Overlap guards**: sending while a turn is already in flight for a
  conversation reports progress instead of double-sending.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import contextvars
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dataikuapi.dss.cobuild import DSSCobuildConversation
from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.conversation_store import ConversationStore
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)
from .utils.validation import (
    require_non_negative_int as _require_non_negative_int,
)

_logger = logging.getLogger(__name__)

# Wall-clock budgets (seconds) for a single Cobuild turn. A multi-recipe build
# has been measured well past ten minutes, so the default leaves headroom and
# the ceiling covers the occasional slow turn. Env-overridable for ops; the
# values below are the shipped defaults. Kept local to this module on purpose.
DEFAULT_COBUILD_TIMEOUT_SECONDS = int(
    os.environ.get("DKU_COBUILD_TIMEOUT_SECONDS", "1200")
)
MAX_COBUILD_TIMEOUT_SECONDS = int(
    os.environ.get("DKU_COBUILD_MAX_TIMEOUT_SECONDS", "1800")
)
MIN_COBUILD_TIMEOUT_SECONDS = 1

# Bound on the live-handle hot cache. The durable store is the source of truth;
# an evicted handle is transparently rehydrated on next use.
_LIVE_HANDLE_MAX = 256

# Cap on concurrently in-flight Cobuild turns across all conversations. Each turn
# owns a daemon thread and (potentially) an open DSS connection for minutes, so
# an unbounded fan-out would exhaust threads/sockets. Env-overridable for ops.
MAX_CONCURRENT_COBUILD_TURNS = int(
    os.environ.get("DKU_MCP_MAX_COBUILD_TURNS", "8")
)

# How long a settled-but-unpolled retained turn stays in the in-memory registry
# before it is swept. Its terminal state is already persisted to the store by the
# done-callback, so sweeping it loses nothing and stops completed turns from
# accumulating forever. Constant on purpose (not a tuning knob).
RETAINED_TURN_TTL_SECONDS = 3600

# Hard cap on the number of *settled* retained turns kept in the in-memory
# registry, independent of the TTL. Their outcomes are already persisted to the
# durable store, so beyond this bound the oldest are evicted first — this stops a
# burst of completed-but-unpolled turns from growing the registry without limit.
MAX_SETTLED_RETAINED = 64

# Hard ceiling for an *unfinished* turn to linger in the registry. Past 2x the max
# turn timeout the daemon thread is almost certainly wedged, so the turn is
# evicted (with a persisted 'abandoned' outcome) to free a concurrency slot. The
# daemon may still finish server-side; its done-callback tolerates the missing
# registry entry and still writes the real terminal outcome to the store.
HUNG_TURN_CEILING_SECONDS = 2 * MAX_COBUILD_TIMEOUT_SECONDS

_PERMISSION_MARKERS = (
    "permission",
    "not allowed",
    "not permitted",
    "forbidden",
    "read-only",
    "read only",
    "allow_edit",
    "cannot edit",
    "cannot create",
    "edit project",
)


# Per-process identity + monotonic counter used to stamp every turn with a token
# ``"<process-id>:<seq>"``. The token lets the durable store reject an out-of-order
# ``in_flight``/outcome write for a settled turn without confusing a genuinely new
# turn (see ``ConversationStore``/``_token_is_stale``). The seq is only advanced
# under ``_lock`` in ``_begin_turn``, so it is serialized process-wide.
_PROCESS_ID = uuid.uuid4().hex
_turn_token_seq = 0


def _next_turn_token() -> str:
    """Return the next process-scoped monotonic turn token. Caller holds ``_lock``."""
    global _turn_token_seq
    _turn_token_seq += 1
    return f"{_PROCESS_ID}:{_turn_token_seq}"


@dataclass
class _CobuildEntry:
    """A live conversation handle plus its owning instance/project."""

    instance_name: str
    project_key: str
    conversation: object
    created_at: str


@dataclass
class _ConfirmDirective:
    """A delete-confirmation to validate + consume atomically inside ``_begin_turn``.

    ``supplied_id`` is the caller's proof-of-inspection argument; ``rehydrated``
    records whether the handle was freshly rebuilt this call (a post-restart path
    that must sync the durable store after consuming).
    """

    supplied_id: str
    rehydrated: bool


@dataclass
class _InFlightTurn:
    """A Cobuild turn running in a daemon thread, retained across timeouts."""

    future: concurrent.futures.Future
    conversation_id: str
    project_key: str
    instance_name: str
    handle: object
    started_at: float
    kind: str
    allow_edit_project: bool
    rehydrated: bool = False
    restore_confirmation_id: str | None = None
    # Process-scoped monotonic identity for this turn, set in ``_begin_turn``. Used
    # to scope the durable store's in_flight/outcome writes so a late/stale write
    # cannot clobber a newer turn (None for test-constructed turns → the store
    # keeps its unconditional, token-less behaviour).
    token: str | None = None
    # monotonic time the future settled; set by the done-callback, used by the
    # TTL sweep. None while the turn is still running.
    settled_at: float | None = None
    # Set once (under ``_lock``) by whichever of the done-callback / the client
    # finalizer writes this turn's terminal outcome to the store first; the other
    # becomes a no-op. Guarantees a single terminal write and no in_flight linger.
    terminal_persisted: bool = False


class _CobuildTimeout(Exception):
    """The client stopped waiting; the turn may still finish server-side."""


class _CobuildInProgress(Exception):
    """The conversation already has an in-flight turn; carries it for the caller.

    Raised by ``_begin_turn`` when the atomic overlap check finds the slot already
    reserved, so the losing caller is handed the existing turn (never an uncaught
    ``RuntimeError``) and reports ``in_progress`` / the settled result.
    """

    def __init__(self, turn: "_InFlightTurn"):
        super().__init__("A Cobuild turn is already in progress.")
        self.turn = turn


class _CobuildSaturated(Exception):
    """Too many turns already in flight; carries their conversation ids."""

    def __init__(self, running: list[str]):
        super().__init__("Cobuild turn capacity reached.")
        self.running = running


_conversations: OrderedDict[str, _CobuildEntry] = OrderedDict()
_in_flight: dict[str, _InFlightTurn] = {}
_lock = threading.RLock()


# --------------------------------------------------------------------------- #
# Durable store + live-handle cache
# --------------------------------------------------------------------------- #


def _state_dir() -> Path:
    """Resolve the state directory at call time so a changed env is honoured."""
    raw = os.environ.get("DKU_MCP_STATE_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "state" / "dataiku-headless"


def _store() -> ConversationStore:
    return ConversationStore(_state_dir() / "conversations.json")


def _remember(
    conversation_id: str, entry: _CobuildEntry, *, replace: bool = False
) -> _CobuildEntry:
    """Install ``entry`` in the hot cache and return the EFFECTIVE live entry.

    Default (``replace=False`` — the rehydration path): install-if-absent under
    the lock. If a live entry already exists (a concurrent caller won the race
    while we were reading the store / building a thin handle), the passed
    rehydrated handle is DISCARDED and the existing live entry is returned — a
    thin handle must never clobber the live handle of an active turn.

    ``replace=True`` (the ``start_cobuild_conversation`` path ONLY): install
    unconditionally; that caller created this conversation and owns its handle.
    """
    with _lock:
        existing = _conversations.get(conversation_id)
        if existing is not None and not replace:
            _conversations.move_to_end(conversation_id)
            return existing
        _conversations[conversation_id] = entry
        _conversations.move_to_end(conversation_id)
        while len(_conversations) > _LIVE_HANDLE_MAX:
            for cid in list(_conversations):
                if cid not in _in_flight:  # never evict a handle mid-turn
                    del _conversations[cid]
                    break
            else:
                break
        return entry


def _get_live(conversation_id: str) -> _CobuildEntry | None:
    with _lock:
        entry = _conversations.get(conversation_id)
        if entry is not None:
            _conversations.move_to_end(conversation_id)
        return entry


def _get_in_flight(conversation_id: str) -> _InFlightTurn | None:
    with _lock:
        return _in_flight.get(conversation_id)


# --------------------------------------------------------------------------- #
# Guards + resolution / rehydration
# --------------------------------------------------------------------------- #


def _guard_project(conversation_id: str, owner_project: str, project_key: str) -> None:
    if owner_project != project_key:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to project "
            f"'{owner_project}', not '{project_key}'."
        )


def _guard_instance(
    conversation_id: str, owner_instance: str, current_instance: str
) -> None:
    if owner_instance != current_instance:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to instance "
            f"'{owner_instance}', but the active instance is '{current_instance}'. "
            "Switch back to the original instance before reusing this conversation."
        )


def _resolve_client_and_instance() -> tuple[str, object]:
    """Snapshot the active instance and build its DSS client, atomically, at entry.

    Both are derived from a single ``get_current_instance()`` snapshot so a
    concurrent ``switch_instance`` cannot make ``instance_name`` and the client
    disagree. Every Cobuild tool must call this at the very top — before any
    ``await``/thread handoff — and thread both values through, so nothing is ever
    re-resolved inside a worker (which could target a different instance, and in
    HTTP mode could no longer read the request-scoped bearer token).
    """
    instance = config.get_current_instance()
    return instance.name, get_dss_client(instance)


def _resolve_entry(
    conversation_id: str, project_key: str, instance_name: str, client: object
) -> tuple[_CobuildEntry, bool]:
    """Return ``(entry, rehydrated)``, rebuilding a thin handle on a cache miss.

    ``instance_name``/``client`` are the entry-time snapshot. The captured client
    is NOT bound onto a cache-hit handle here — that binding is deferred to
    ``_begin_turn`` so it happens atomically with the turn-slot reservation (a
    concurrent caller must never rebind the handle between the overlap check and
    the send). A rehydrated thin handle is *constructed* with ``client``.

    A live handle carries client-side state (pending confirmation id, selection
    focus) that DSS does not persist. On a cache miss for a persisted id we
    rebuild a thin handle from the durable store; the client-side selection
    focus is lost (fine — the server thread is authoritative for the build) and
    ``rehydrated`` is returned True so the tool result can say so.
    """
    entry = _get_live(conversation_id)
    if entry is not None:
        _guard_project(conversation_id, entry.project_key, project_key)
        _guard_instance(conversation_id, entry.instance_name, instance_name)
        return entry, False

    record = _store().read(conversation_id)
    if record is None:
        raise ValueError(
            f"Unknown Cobuild conversation_id '{conversation_id}'. "
            "Start one with start_cobuild_conversation."
        )
    owner_project = str(record.get("project_key", ""))
    _guard_project(conversation_id, owner_project, project_key)
    _guard_instance(conversation_id, str(record.get("instance_name", "")), instance_name)

    # Constructing the handle is cheap and does no network I/O; the POST happens
    # later inside the daemon thread but against the entry-time ``client``.
    # Rehydrating here (not in a worker) is what lets the overlap guard reason
    # about the handle synchronously.
    handle = DSSCobuildConversation(client, owner_project, conversation_id)
    pending = record.get("pending_confirmation_id")
    if pending:
        # The SDK exposes no public setter; _pending_confirmation_id is the only
        # hook for restoring a pending delete confirmation after a restart.
        handle._pending_confirmation_id = pending
    rehydrated_entry = _CobuildEntry(
        instance_name=str(record.get("instance_name", "")),
        project_key=owner_project,
        conversation=handle,
        created_at=str(record.get("created_at", "")),
    )
    # Double-checked install: between the cache miss above and here another caller
    # may have installed a LIVE handle (e.g. started a turn on it). ``_remember``
    # re-checks the cache under the lock and, if a live entry appeared, discards
    # this thin handle and returns the winner — a rehydrated handle must never
    # replace the live handle of an active turn.
    effective = _remember(conversation_id, rehydrated_entry)
    if effective is rehydrated_entry:
        return rehydrated_entry, True
    _guard_project(conversation_id, effective.project_key, project_key)
    _guard_instance(conversation_id, effective.instance_name, instance_name)
    return effective, False


# --------------------------------------------------------------------------- #
# Retained-turn machinery (daemon thread + progress heartbeat)
# --------------------------------------------------------------------------- #


def _spawn_blocking(fn) -> concurrent.futures.Future:
    """Run a blocking Cobuild turn in a daemon thread.

    Deliberately NOT ``run_blocking``: the shared 4-worker pool that serves every
    other MCP tool must not be starved by a Cobuild build that can run for
    minutes. Owning the Future ourselves also lets ``get_cobuild_turn_status``
    recover a turn that outlived its client-side timeout without re-sending.

    Like ``run_blocking``, we snapshot the caller's ContextVars and run ``fn``
    inside them: FastMCP keeps the request (and thus the HTTP bearer token) in
    ContextVars that a bare thread would not inherit. (The turn's client is
    already resolved at entry, but this keeps any late request read correct too.)
    """
    future: concurrent.futures.Future = concurrent.futures.Future()
    future.set_running_or_notify_cancel()
    parent_context = contextvars.copy_context()

    def _runner() -> None:
        try:
            future.set_result(parent_context.run(fn))
        except BaseException as exc:  # noqa: BLE001 - surfaced via future.result()
            future.set_exception(exc)

    threading.Thread(target=_runner, daemon=True, name="cobuild-turn").start()
    return future


def _abandon_turn(turn: _InFlightTurn) -> None:
    """Persist an 'abandoned' terminal outcome for a hung, evicted turn.

    Best-effort: the still-running daemon thread may later complete and its
    done-callback will then overwrite this with the real outcome (``_abandon_turn``
    deliberately does NOT set ``terminal_persisted``, so the callback is not a
    no-op). Persisting 'abandoned' keeps a poll before that honest rather than
    silently losing the turn.
    """
    with contextlib.suppress(Exception):
        _store().record_outcome(
            turn.conversation_id, "abandoned", None, token=turn.token
        )


def _sweep_in_flight(now: float | None = None) -> None:
    """Bound the retained-turn registry. Caller must already hold ``_lock``.

    Three jobs, each of which loses no persisted result:

    * **Hung unfinished turns** older than ``HUNG_TURN_CEILING_SECONDS`` are
      evicted with a persisted 'abandoned' outcome, freeing a concurrency slot.
    * **Settled turns** past ``RETAINED_TURN_TTL_SECONDS`` are evicted (their
      outcome was already persisted by the done-callback).
    * The number of retained **settled** turns is bounded to
      ``MAX_SETTLED_RETAINED``; any excess is evicted oldest-first.
    """
    now = time.monotonic() if now is None else now

    # 1. Hung, still-running turns → abandon + evict (frees the slot for the cap).
    for cid in list(_in_flight):
        turn = _in_flight[cid]
        if turn.future.done():
            continue
        if now - turn.started_at > HUNG_TURN_CEILING_SECONDS:
            _abandon_turn(turn)
            del _in_flight[cid]

    # 2. Settled turns past their TTL → evict (stamp settled_at on first sight).
    for cid in list(_in_flight):
        turn = _in_flight[cid]
        if not turn.future.done():
            continue
        if turn.settled_at is None:
            turn.settled_at = now
        elif now - turn.settled_at > RETAINED_TURN_TTL_SECONDS:
            del _in_flight[cid]

    # 3. Bound the total number of retained *settled* turns, oldest-first.
    settled = [
        (cid, turn) for cid, turn in _in_flight.items() if turn.future.done()
    ]
    if len(settled) > MAX_SETTLED_RETAINED:
        settled.sort(key=lambda kv: kv[1].settled_at or 0.0)
        for cid, _turn in settled[: len(settled) - MAX_SETTLED_RETAINED]:
            del _in_flight[cid]


def _sweep_under_lock(now: float | None = None) -> None:
    """Acquire ``_lock`` and run ``_sweep_in_flight`` — callable from a worker.

    The sweep may write to the durable store (abandoning a hung turn), so tools
    invoke this via ``run_blocking`` to keep that write off the event-loop thread.
    """
    with _lock:
        _sweep_in_flight(now)


def _running_conversation_ids() -> list[str]:
    """Conversation ids whose retained turn has not settled yet. Holds ``_lock``."""
    return sorted(cid for cid, t in _in_flight.items() if not t.future.done())


def _consume_confirmation(
    conversation_id: str, handle, directive: _ConfirmDirective
) -> str:
    """Validate the supplied confirmation id against the SINGLE authoritative
    source and consume it. Caller holds ``_lock``.

    The authoritative pending id is the handle's own ``_pending_confirmation_id``:
    on a live cache hit it is the id the caller actually saw; on a post-restart
    rehydration ``_resolve_entry`` already seeded it from the durable store. The
    store is therefore NEVER unioned with the live id — a stale persisted id can
    never approve a different live deletion. Returns the consumed id so a failed
    answer POST can settle-aware re-arm exactly it for a retry.

    Runs entirely under the lock, after the overlap check and before the slot is
    reserved: the losing overlapping caller exits with ``_CobuildInProgress``
    BEFORE any validation side-effect, so it can never write (or replay) a pending
    id onto the shared handle.
    """
    authoritative = getattr(handle, "_pending_confirmation_id", None)
    if not authoritative:
        raise ValueError(
            f"No pending confirmation for conversation '{conversation_id}'. "
            "Re-send the request so Cobuild asks again, then pass the "
            "confirmation_id from that needs_confirmation result."
        )
    if directive.supplied_id != authoritative:
        raise ValueError(
            f"confirmation_id '{directive.supplied_id}' does not match the pending "
            f"confirmation for conversation '{conversation_id}'. Re-read the "
            "latest needs_confirmation response and pass exactly its "
            "confirmation_id — it is your proof of having inspected precisely "
            "which objects will be deleted."
        )
    # Bind/consume the authoritative id onto the handle (idempotent on the live
    # path; installs the store value on the freshly-rehydrated thin handle).
    handle._pending_confirmation_id = authoritative
    if directive.rehydrated:
        # Restart-path match: sync the store to what we are about to answer.
        _sync_pending_confirmation(conversation_id, handle)
    return authoritative


def _begin_turn(
    conversation_id: str,
    entry: _CobuildEntry,
    fn,
    *,
    kind: str,
    allow_edit_project: bool,
    rehydrated: bool,
    client: object,
    confirmation: _ConfirmDirective | None = None,
) -> _InFlightTurn:
    """Atomically reserve the turn slot, arm persistence, and spawn.

    Everything below runs under the single registry lock, in this order:

    1. **sweep** stale/hung retained turns (may free a slot);
    2. **overlap check** — a second in-flight turn for this conversation turns the
       loser away with ``_CobuildInProgress`` BEFORE any validation side-effect;
    3. **validate + consume** a delete confirmation (answer path only): the
       supplied id is checked against the single authoritative source and consumed
       onto the handle — so two concurrent answers can never both validate/write
       the same pending id, and the loser never replays a stale id;
    4. **cap check** (``_CobuildSaturated``);
    5. **client bind** — the captured client is bound onto the handle so the turn
       thread reads THIS caller's client/bearer and no interleaved caller can
       retarget it;
    6. **spawn** the daemon-thread turn;
    7. **arm persistence** — the ``in_flight`` store marker + terminal-outcome
       callback are installed while still under the lock and BEFORE the turn is
       inserted, so a fast-completing turn cannot be settled by an overlapping
       caller before its persistence is armed (which would let a late ``in_flight``
       marker clobber the terminal outcome);
    8. **insert** — only now is the turn visible to any other caller.

    Because steps 2-8 share one critical section, none of them can interleave with
    a concurrent caller.
    """
    with _lock:
        _sweep_in_flight()
        existing = _in_flight.get(conversation_id)
        if existing is not None:
            raise _CobuildInProgress(existing)
        restore_confirmation_id: str | None = None
        if confirmation is not None:
            restore_confirmation_id = _consume_confirmation(
                conversation_id, entry.conversation, confirmation
            )
        running = _running_conversation_ids()
        if len(running) >= MAX_CONCURRENT_COBUILD_TURNS:
            # Checked atomically under _lock with the insert below, so the cap
            # cannot be raced past.
            raise _CobuildSaturated(running)
        entry.conversation.client = client
        turn = _InFlightTurn(
            future=_spawn_blocking(fn),
            conversation_id=conversation_id,
            project_key=entry.project_key,
            instance_name=entry.instance_name,
            handle=entry.conversation,
            started_at=time.monotonic(),
            kind=kind,
            allow_edit_project=allow_edit_project,
            rehydrated=rehydrated,
            restore_confirmation_id=restore_confirmation_id,
            token=_next_turn_token(),
        )
        _arm_turn_persistence(turn)
        _in_flight[conversation_id] = turn
        return turn


def _terminal_status(turn: _InFlightTurn) -> str:
    """Classify a *settled* future's outcome into the response contract status."""
    try:
        response = turn.future.result()
    except BaseException:  # noqa: BLE001 - any raise is an error outcome
        return "error"
    rtype = getattr(response, "type", None)
    if bool(getattr(response, "is_error", False)) or rtype == "error":
        return "error"
    if rtype == "delete_confirmation_request" or getattr(
        response, "is_confirmation_request", False
    ):
        return "needs_confirmation"
    if rtype == "assistant_message":
        return "completed"
    return "error"


def _persist_terminal_once(
    turn: _InFlightTurn, status: str, pending: str | None
) -> None:
    """Write the turn's terminal outcome to the store exactly once.

    Both the done-callback (daemon thread) and the client-side finalizer (event
    loop) can reach here; the first to run flips ``terminal_persisted`` under the
    lock and performs the single store write, the other is a no-op. This closes
    the race where either path could clobber the other. A write failure is caught
    and logged, then a minimal terminal-status write is retried so
    ``last_result_status`` can never linger at ``in_flight`` for a settled turn.
    """
    with _lock:
        if turn.terminal_persisted:
            return
        turn.terminal_persisted = True
    try:
        _store().record_outcome(
            turn.conversation_id, status, pending, token=turn.token
        )
    except Exception:  # noqa: BLE001 - best-effort; retried minimally below
        _logger.exception(
            "Failed to persist terminal Cobuild outcome for conversation %s; "
            "retrying a minimal terminal-status write.",
            turn.conversation_id,
        )
        with contextlib.suppress(Exception):
            _store().record_outcome(
                turn.conversation_id, status, None, token=turn.token
            )


def _persist_terminal_outcome(turn: _InFlightTurn) -> None:
    """Done-callback: settle the turn's terminal outcome into the store, once.

    Runs in the daemon thread the instant the future settles, so a
    finished-but-unpolled turn's result (and any newly-requested delete
    confirmation) survive in the durable store even if it is never polled. It
    mirrors the finalizer's status/pending computation — including restoring a
    lost confirmation id on failure — so whichever runs first writes the same
    terminal state. Never raises: a persistence error is logged, not propagated.
    """
    if turn.settled_at is None:
        turn.settled_at = time.monotonic()
    try:
        failed = turn.future.exception() is not None
    except BaseException:  # noqa: BLE001 - cancelled/odd future → treat as error
        failed = True
    if failed:
        # Error path: restore a confirmation id cleared by a failed answer POST,
        # so a needs_confirmation delete stays retriable after this turn.
        _restore_confirmation(turn)
        status = "error"
    else:
        status = _terminal_status(turn)
    pending = getattr(turn.handle, "_pending_confirmation_id", None)
    _persist_terminal_once(turn, status, pending)


def _arm_turn_persistence(turn: _InFlightTurn) -> None:
    """Persist an in-flight marker and register the terminal-outcome callback.

    The marker lets ``get_cobuild_turn_status`` report ``turn_lost`` truthfully
    after a restart (the daemon thread does not survive one). The callback then
    overwrites it with the real terminal state the moment the future settles.
    Order matters: mark first, register second, so the terminal state always wins.

    Called from INSIDE ``_begin_turn`` under ``_lock``, before the turn is inserted
    into the registry — so the marker and callback are armed before any other
    caller can observe (and race to settle) this turn. The marker is scoped to the
    turn's token, so a late/duplicate marker can never regress a terminal outcome.
    """
    _store().mark_in_flight(turn.conversation_id, turn.token)
    turn.future.add_done_callback(lambda _f: _persist_terminal_outcome(turn))


def _restore_confirmation(turn: _InFlightTurn) -> None:
    """Re-arm the confirmation the SDK cleared before a FAILED answer POST.

    ``answer_confirmation()`` clears ``_pending_confirmation_id`` before its POST;
    if that POST failed the id is lost, so restore exactly it for a retry (no
    public setter exists). Settle-aware: we only restore when
    (a) there is an id to restore, (b) a NEWER turn has not taken over this
    conversation (restoring over a successor would replay a consumed deletion),
    and (c) the handle's pending slot is still empty (a live successor that set a
    new pending must not be clobbered). We only ever restore the exact id THIS
    turn consumed, never a value that no longer matches. The durable side is
    additionally guarded by the monotonic turn token in ``record_outcome``.
    """
    if not turn.restore_confirmation_id:
        return
    with _lock:
        current = _in_flight.get(turn.conversation_id)
        if current is not None and current is not turn and current.token != turn.token:
            # A different turn now owns this conversation; do not replay onto it.
            return
        if getattr(turn.handle, "_pending_confirmation_id", None) is None:
            turn.handle._pending_confirmation_id = turn.restore_confirmation_id


async def _wait_for_turn(
    turn: _InFlightTurn, timeout: int, ctx: Context | None
) -> tuple[object, int]:
    """Await a turn, popping it on completion but retaining it on timeout."""
    next_heartbeat = 10
    while True:
        if turn.future.done():
            with _lock:
                _in_flight.pop(turn.conversation_id, None)
            elapsed = int(time.monotonic() - turn.started_at)
            return turn.future.result(), elapsed  # may raise; caller finalizes
        elapsed = int(time.monotonic() - turn.started_at)
        if elapsed >= timeout:
            raise _CobuildTimeout()  # do NOT pop: the turn stays retrievable
        await asyncio.sleep(min(0.25, max(0.05, timeout - elapsed)))
        elapsed = int(time.monotonic() - turn.started_at)
        if ctx is not None and elapsed >= next_heartbeat:
            try:
                await ctx.report_progress(progress=elapsed, total=timeout)
                await ctx.info(f"Cobuild still working... {elapsed}s elapsed")
            except Exception:  # noqa: BLE001 - heartbeat is best-effort
                pass
            next_heartbeat = elapsed + 10


# --------------------------------------------------------------------------- #
# Result shaping (stable response contract)
# --------------------------------------------------------------------------- #


def _clamp_timeout(timeout_seconds: int) -> int:
    if not timeout_seconds:
        return DEFAULT_COBUILD_TIMEOUT_SECONDS
    return max(
        MIN_COBUILD_TIMEOUT_SECONDS,
        min(int(timeout_seconds), MAX_COBUILD_TIMEOUT_SECONDS),
    )


def _looks_permission_denied(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _PERMISSION_MARKERS)


_TRANSPORT_MARKERS = (
    "connection refused",
    "failed to establish",
    "name or service not known",
    "max retries",
    "getaddrinfo",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "broken pipe",
    "remotedisconnected",
    "connection error",
)

# requests/urllib3 transport exception class names: a raise of one of these means
# the request never got a definitive HTTP response, so the DSS-side outcome is
# UNKNOWN. ``dataikuapi`` raises a bare ``DataikuException`` for ANY >=400 response
# and DISCARDS the HTTP status code while doing so (see
# ``dataikuapi/utils.py:handle_http_exception`` — it formats only errorType +
# detailedMessage), so a 5xx cannot be recovered from the message text. That is
# why a DataikuException is classified by matching known client-error signatures
# rather than by looking for a 5xx (see ``_is_transport_outcome_unknown``).
_TRANSPORT_EXC_NAMES = frozenset(
    {
        "connectionerror",
        "connecttimeout",
        "readtimeout",
        "timeout",
        "sslerror",
        "chunkedencodingerror",
        "newconnectionerror",
        "maxretryerror",
        "protocolerror",
        "proxyerror",
    }
)

# Known DSS *structured client-error* signatures. A ``DataikuException`` whose
# message matches one of these was a request DSS rejected BEFORE mutating (a 4xx-
# class error), so its outcome is DEFINITIVE. Anything else from DSS — including a
# 5xx whose status code was discarded (e.g. "BackendFailure: write failed") — is
# treated as outcome-UNKNOWN, the safe direction (never advise a blind resend on
# an ambiguous server error). Kept deliberately specific so a genuine server-side
# failure is not misread as a clean client rejection.
_DSS_CLIENT_ERROR_MARKERS = (
    "permission",
    "not allowed",
    "not permitted",
    "forbidden",
    "unauthorized",
    "not authorized",
    "authorization denied",
    "access denied",
    "not found",
    "does not exist",
    "no such",
    "already exists",
    "invalid argument",
    "illegal argument",
    "validation",
    "bad request",
    "security token",
)

# A bare 5xx signature in an arbitrary (non-Dataiku) error's text still means the
# server may have mutated state before failing → UNKNOWN. ``\b5\d\d\b`` matches a
# standalone 5xx status code; the phrase markers catch the common reason strings.
_SERVER_ERROR_RE = re.compile(r"\b5\d\d\b")
_SERVER_ERROR_MARKERS = (
    "internal server error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
)


def _looks_server_error(text: str) -> bool:
    lowered = text.lower()
    return bool(_SERVER_ERROR_RE.search(text)) or any(
        marker in lowered for marker in _SERVER_ERROR_MARKERS
    )


def _looks_dss_client_error(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _DSS_CLIENT_ERROR_MARKERS)


def _is_transport_outcome_unknown(exc: BaseException) -> bool:
    """True when it is UNKNOWN whether DSS received and acted on the turn.

    The caller must not blindly resend when the outcome is unknown:

    * A transport-layer failure (no HTTP response ever arrived) → UNKNOWN.
    * A ``DataikuException`` is classified by INVERTING the default, because
      ``dataikuapi`` discards the HTTP status code when it raises (a real 503 body
      "BackendFailure: write failed" carries no "5xx" text). It is DEFINITIVE only
      when its message matches a known DSS structured client-error signature
      (permission / not-found / already-exists / invalid-argument / validation /
      bad-request / security-token …); OTHERWISE it is UNKNOWN — a server-side
      error may have partially applied a mutation. This is the safe direction: a
      misclassified client error merely asks the caller to verify state, whereas a
      misclassified server error would wrongly green-light a blind resend.
    * Any other exception whose text names a transport failure or a bare 5xx →
      UNKNOWN.
    """
    for cls in type(exc).__mro__:
        if cls.__name__.lower() in _TRANSPORT_EXC_NAMES:
            return True
    text = str(exc)
    if type(exc).__name__ == "DataikuException":
        return not _looks_dss_client_error(text)
    if any(marker in text.lower() for marker in _TRANSPORT_MARKERS):
        return True
    # A non-Dataiku, non-transport error that nonetheless names a 5xx: unknown.
    return _looks_server_error(text)


def _map_exception(exc: BaseException) -> str:
    """Map a transport-level failure to a prescriptive, next-action message."""
    text = str(exc)
    lowered = text.lower()
    if _is_transport_outcome_unknown(exc):
        if type(exc).__name__ == "DataikuException" or _looks_server_error(text):
            return (
                f"DSS returned a server error ({text}); it may have partially "
                "applied the change before failing. Verify the project state "
                "before deciding whether to retry."
            )
        return f"Could not reach DSS ({text}). Check the instance URL is reachable."
    if any(
        marker in lowered
        for marker in ("401", "403", "forbidden", "unauthorized")
    ):
        return (
            f"DSS rejected the request ({text}). Check the API key has access to "
            "this project and to Cobuild."
        )
    if "404" in text or "not found" in lowered:
        return (
            f"Cobuild endpoint not found ({text}). This DSS instance may not "
            "expose Cobuild, or the project key is wrong."
        )
    return f"Unexpected DSS error: {text}"


def _response_result(
    turn: _InFlightTurn, response, elapsed: int
) -> dict:
    """Map an SDK response to the stable contract, failing closed on the unknown."""
    base = {
        "conversation_id": turn.conversation_id,
        "project_key": turn.project_key,
        "instance_name": turn.instance_name,
        "elapsed_seconds": elapsed,
    }
    if turn.rehydrated:
        base["rehydrated"] = True

    rtype = getattr(response, "type", None)
    is_error = bool(getattr(response, "is_error", False)) or rtype == "error"

    if is_error:
        message = getattr(response, "message", None) or "Cobuild returned an error."
        result = {**base, "status": "error", "message": message}
        if not turn.allow_edit_project and _looks_permission_denied(message):
            result["next_action"] = (
                "This looks like a missing edit permission. If the user asked for "
                "a build or modification, retry the same message with "
                "allow_edit_project=true."
            )
        return result

    if rtype == "delete_confirmation_request" or getattr(
        response, "is_confirmation_request", False
    ):
        return {
            **base,
            "status": "needs_confirmation",
            "message": getattr(response, "message", None)
            or "Cobuild is requesting confirmation before deleting objects.",
            "confirmation_id": getattr(turn.handle, "_pending_confirmation_id", None),
            "objects_to_delete": getattr(response, "objects_to_delete", None),
            "deletion_impacts": getattr(response, "deletion_impacts", None),
            "next_action": (
                "Inspect objects_to_delete, then call answer_cobuild_confirmation "
                "with choice=APPROVE or CANCEL (pass confirmation_id to stay "
                "restart-safe)."
            ),
        }

    if rtype == "assistant_message":
        return {**base, "status": "completed", "message": getattr(response, "message", None) or ""}

    # Fail-closed: an unknown/malformed type must never read as a success.
    return {
        **base,
        "status": "error",
        "message": (
            f"Cobuild returned an unrecognized response type {rtype!r}. Treating "
            "it as an error rather than a success. Re-send the message, or inspect "
            "the conversation in DSS."
        ),
    }


def _sync_pending_confirmation(conversation_id: str, handle) -> None:
    """Mirror the handle's pending confirmation id into the durable store."""
    _store().set_pending_confirmation(
        conversation_id, getattr(handle, "_pending_confirmation_id", None)
    )


def _finalize_response(turn: _InFlightTurn, response, elapsed: int) -> dict:
    result = _response_result(turn, response, elapsed)
    pending = getattr(turn.handle, "_pending_confirmation_id", None)
    # Single settle path (idempotent with the done-callback): writes both the
    # terminal status and the pending id, so it also covers the store sync.
    _persist_terminal_once(turn, result["status"], pending)
    return result


def _finalize_error(turn: _InFlightTurn, exc: BaseException, elapsed: int) -> dict:
    _restore_confirmation(turn)
    pending = getattr(turn.handle, "_pending_confirmation_id", None)
    result = {
        "conversation_id": turn.conversation_id,
        "project_key": turn.project_key,
        "instance_name": turn.instance_name,
        "status": "error",
        "message": _map_exception(exc),
        "elapsed_seconds": elapsed,
    }
    if _is_transport_outcome_unknown(exc):
        # The send never got a definitive response, so we do NOT know whether the
        # turn took effect. Distinguish this from a DSS rejection so the caller
        # does not blindly resend a build or a delete approval.
        result["error_kind"] = "transport_outcome_unknown"
        result["next_action"] = (
            "The connection to DSS failed before any response was received, so it "
            "is UNKNOWN whether this turn took effect. Do NOT blindly resend a "
            "build/edit or a delete approval — it may have already happened. First "
            "inspect the project (or send a read-only follow-up) to check the "
            "current state, then decide."
        )
    # Single settle path (idempotent with the done-callback): persist the error
    # outcome and the (possibly restored) pending id.
    _persist_terminal_once(turn, "error", pending)
    return result


def _timeout_result(turn: _InFlightTurn) -> dict:
    elapsed = int(time.monotonic() - turn.started_at)
    return {
        "conversation_id": turn.conversation_id,
        "project_key": turn.project_key,
        "instance_name": turn.instance_name,
        "status": "timeout",
        "message": (
            "Stopped waiting for Cobuild after the client-side timeout; the turn "
            "may still be completing inside DSS."
        ),
        "elapsed_seconds": elapsed,
        "next_action": (
            f"Poll get_cobuild_turn_status(conversation_id='{turn.conversation_id}', "
            f"project_key='{turn.project_key}'). Do not send a new message while "
            "this turn is still running."
        ),
    }


def _in_progress_result(turn: _InFlightTurn) -> dict:
    elapsed = int(time.monotonic() - turn.started_at)
    return {
        "conversation_id": turn.conversation_id,
        "project_key": turn.project_key,
        "instance_name": turn.instance_name,
        "status": "in_progress",
        "message": (
            "A Cobuild turn is already running for this conversation; no new "
            "message was sent."
        ),
        "elapsed_seconds": elapsed,
        "next_action": (
            f"Poll get_cobuild_turn_status(conversation_id='{turn.conversation_id}', "
            f"project_key='{turn.project_key}')."
        ),
    }


def _saturation_result(
    conversation_id: str, project_key: str, instance_name: str, running: list[str]
) -> dict:
    return {
        "conversation_id": conversation_id,
        "project_key": project_key,
        "instance_name": instance_name,
        "status": "error",
        "error_kind": "saturated",
        "message": (
            f"Too many Cobuild turns are already in flight "
            f"({len(running)}/{MAX_CONCURRENT_COBUILD_TURNS}); no new turn was "
            f"started. In-flight conversations: {', '.join(running)}."
        ),
        "next_action": (
            "Wait for one of the in-flight turns to finish (poll them with "
            "get_cobuild_turn_status), then retry. Raise the cap with "
            "DKU_MCP_MAX_COBUILD_TURNS only if the host can afford more "
            "concurrent builds."
        ),
    }


def _turn_lost_result(conversation_id: str, project_key: str, instance_name: str) -> dict:
    return {
        "conversation_id": conversation_id,
        "project_key": project_key,
        "instance_name": instance_name,
        "status": "turn_lost",
        "message": (
            "A Cobuild turn was in flight but its worker thread did not survive "
            "(the MCP server restarted). The turn cannot be resumed here; the "
            "DSS-side turn may nonetheless have completed."
        ),
        "next_action": (
            "Do NOT assume the build failed. Inspect the project (or send a "
            "read-only follow-up) to see whether the change landed, then decide "
            "whether to re-send."
        ),
    }


def _store_reported_result(
    conversation_id: str, project_key: str, instance_name: str, record: dict
) -> dict:
    """Report a settled turn's persisted terminal state after a restart."""
    status = record.get("last_result_status") or "completed"
    pending = record.get("pending_confirmation_id")
    result = {
        "conversation_id": conversation_id,
        "project_key": project_key,
        "instance_name": instance_name,
        "status": status,
        "message": (
            "Reporting this turn's last known outcome from the durable store "
            "(the in-memory turn is no longer held, e.g. after a restart)."
        ),
    }
    if status == "needs_confirmation" and pending:
        result["confirmation_id"] = pending
        result["next_action"] = (
            "Inspect the objects to delete in DSS, then call "
            "answer_cobuild_confirmation with the confirmation_id above."
        )
    elif status == "abandoned":
        result["message"] = (
            "This turn was still running past the hard time ceiling and was "
            "evicted from the registry with an 'abandoned' outcome; the DSS-side "
            "turn may nonetheless have completed."
        )
        result["next_action"] = (
            "Do NOT assume it failed. Inspect the project (or send a read-only "
            "follow-up) to see whether the change landed, then decide."
        )
    return result


def _settle_turn(turn: _InFlightTurn) -> dict:
    """Pop a finished retained turn and turn its Future into a result dict."""
    with _lock:
        _in_flight.pop(turn.conversation_id, None)
    elapsed = int(time.monotonic() - turn.started_at)
    try:
        response = turn.future.result()
    except BaseException as exc:  # noqa: BLE001 - mapped to an error result
        return _finalize_error(turn, exc, elapsed)
    return _finalize_response(turn, response, elapsed)


def _handle_existing_turn(turn: _InFlightTurn) -> dict:
    """Overlap guard: never double-send while a turn is in flight for a convo."""
    if turn.future.done():
        result = _settle_turn(turn)
        result["next_action"] = (
            "NOTE: your new call was NOT sent - a previously in-flight turn had "
            "just completed and is shown above. "
            + result.get("next_action", "Call the tool again if you still need to continue.")
        )
        return result
    return _in_progress_result(turn)


# --------------------------------------------------------------------------- #
# MCP tools
# --------------------------------------------------------------------------- #


@mcp.tool()
async def start_cobuild_conversation(project_key: str, ctx: Context) -> str:
    """Open a new Cobuild conversation for a project and register it durably.

    Cobuild is the AI assistant running inside the DSS instance; it can inspect
    and (when granted) build Flows, recipes, datasets, dashboards, and other
    project objects. This tool only creates the thread — no work is sent yet.

    The returned ``conversation_id`` is the handle for follow-ups. It is
    persisted so ``send_cobuild_message`` / ``answer_cobuild_confirmation`` keep
    working even after the MCP server restarts.

    Returns compact JSON: ``{conversation_id, project_key, instance_name,
    status, created_at, next_action}``.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Starting Cobuild conversation for project {project_key}...")

    # Resolve instance + client once, at entry, and thread the client into the
    # worker so a concurrent switch_instance cannot retarget it and (in HTTP
    # mode) the bearer token is read while the request context is still live.
    instance_name, client = _resolve_client_and_instance()

    def _run():
        project = client.get_project(project_key)
        return project.new_cobuild_conversation()

    conversation = await run_blocking(_run)
    conversation_id = conversation.conversation_id
    created_at = datetime.now(UTC).isoformat()

    _remember(
        conversation_id,
        _CobuildEntry(
            instance_name=instance_name,
            project_key=project_key,
            conversation=conversation,
            created_at=created_at,
        ),
        # This caller CREATED the conversation and owns its live handle, so it may
        # install unconditionally (the only sanctioned replace of a cache entry).
        replace=True,
    )
    # Persist off the event-loop thread (the store takes a bounded file lock).
    await run_blocking(
        _store().upsert,
        conversation_id,
        {
            "instance_name": instance_name,
            "project_key": project_key,
            "created_at": created_at,
            "pending_confirmation_id": None,
        },
    )

    return compact_json(
        omit_empty(
            {
                "conversation_id": conversation_id,
                "project_key": project_key,
                "instance_name": instance_name,
                "status": "completed",
                "created_at": created_at,
                "next_action": (
                    "Send work with send_cobuild_message(conversation_id, "
                    "project_key, message). Pass allow_edit_project=true only for "
                    "an explicitly requested build."
                ),
            }
        )
    )


@mcp.tool()
async def send_cobuild_message(
    conversation_id: str,
    project_key: str,
    message: str,
    ctx: Context,
    allow_edit_project: bool = False,
    timeout_seconds: int = 0,
) -> str:
    """Send one message to a Cobuild conversation and return its settled result.

    ``allow_edit_project``: Per-message grant. False = Cobuild can inspect and
    answer but cannot create/edit; pass True only for an explicitly requested
    build/modification.

    If the server restarted and the live handle was lost, the conversation is
    rehydrated from ``conversation_id`` + ``project_key`` and the result carries
    ``rehydrated: true`` (the prior client-side selection focus is reset).

    Long builds: the turn runs off the shared worker pool. If it exceeds
    ``timeout_seconds`` (0 -> server default, clamped to the ceiling), the result
    is ``status: timeout`` and the work is retained — poll
    ``get_cobuild_turn_status`` rather than re-sending. Sending while a turn is
    already in flight returns ``status: in_progress`` without double-sending.

    Result contract (compact JSON): ``{conversation_id, project_key,
    instance_name, status: completed|in_progress|needs_confirmation|error|
    timeout, message, confirmation_id?, objects_to_delete?, deletion_impacts?,
    rehydrated?, elapsed_seconds, next_action?}``. When ``status`` is
    ``needs_confirmation``, inspect ``objects_to_delete`` then call
    ``answer_cobuild_confirmation``.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    message = _require_non_empty_string(message, "message")
    timeout_seconds = _require_non_negative_int(timeout_seconds, "timeout_seconds")
    await ctx.info(f"Sending Cobuild message to conversation {conversation_id}...")

    # Snapshot instance + client at entry, before any thread/await handoff.
    instance_name, client = _resolve_client_and_instance()

    existing = _get_in_flight(conversation_id)
    if existing is not None:
        _guard_project(conversation_id, existing.project_key, project_key)
        # _handle_existing_turn may settle a done turn (a store write), so keep it
        # off the event-loop thread.
        return compact_json(omit_empty(await run_blocking(_handle_existing_turn, existing)))

    # _resolve_entry reads the durable store on a rehydration; run it off-thread.
    entry, rehydrated = await run_blocking(
        _resolve_entry, conversation_id, project_key, instance_name, client
    )
    timeout = _clamp_timeout(timeout_seconds)

    def _call():
        return entry.conversation.send_message(
            message, allow_edit_project=allow_edit_project
        )

    try:
        # _begin_turn sweeps (a possible store write for a hung turn) and reserves
        # the slot; run it off-thread. The atomic overlap check inside may hand us
        # back the existing turn instead (never an uncaught RuntimeError).
        turn = await run_blocking(
            _begin_turn,
            conversation_id,
            entry,
            _call,
            kind="send",
            allow_edit_project=allow_edit_project,
            rehydrated=rehydrated,
            client=client,
        )
    except _CobuildInProgress as exc:
        _guard_project(conversation_id, exc.turn.project_key, project_key)
        return compact_json(omit_empty(await run_blocking(_handle_existing_turn, exc.turn)))
    except _CobuildSaturated as exc:
        return compact_json(
            omit_empty(
                _saturation_result(
                    conversation_id, project_key, instance_name, exc.running
                )
            )
        )
    # Persistence was armed inside _begin_turn (under the lock, before the turn
    # became visible), so nothing extra to arm here.
    try:
        response, elapsed = await _wait_for_turn(turn, timeout, ctx)
    except _CobuildTimeout:
        return compact_json(omit_empty(_timeout_result(turn)))
    except Exception as exc:  # noqa: BLE001 - mapped to an error result
        elapsed = int(time.monotonic() - turn.started_at)
        return compact_json(omit_empty(await run_blocking(_finalize_error, turn, exc, elapsed)))
    return compact_json(omit_empty(await run_blocking(_finalize_response, turn, response, elapsed)))


@mcp.tool()
async def answer_cobuild_confirmation(
    conversation_id: str,
    project_key: str,
    choice: str,
    confirmation_id: str,
    ctx: Context,
    timeout_seconds: int = 0,
) -> str:
    """Answer a pending Cobuild delete-confirmation with APPROVE or CANCEL.

    Call this only after a ``send_cobuild_message`` /
    ``answer_cobuild_confirmation`` result returned
    ``status: needs_confirmation``. SAFETY: APPROVE is destructive — inspect the
    prior ``objects_to_delete`` before approving.

    ``confirmation_id`` is REQUIRED and is the id from that latest
    ``needs_confirmation`` result. It is proof that you inspected exactly this
    pending deletion: the call is rejected unless it matches the conversation's
    current pending confirmation (live handle or durable store). This prevents a
    stale token from approving a *different* deletion that became pending in the
    meantime — if you get a mismatch error, re-read the most recent
    ``needs_confirmation`` response and pass its confirmation_id. It also keeps
    the answer restart-safe: after a server restart the pending confirmation is
    restored from the durable store and validated against this argument.

    Same retained-turn / overlap / timeout behaviour and result contract as
    ``send_cobuild_message``.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    choice = _require_non_empty_string(choice, "choice").upper()
    if choice not in {"APPROVE", "CANCEL"}:
        raise ValueError("choice must be 'APPROVE' or 'CANCEL'")
    confirmation_id = _require_non_empty_string(confirmation_id, "confirmation_id")
    timeout_seconds = _require_non_negative_int(timeout_seconds, "timeout_seconds")
    await ctx.info(
        f"Answering Cobuild confirmation for conversation {conversation_id} "
        f"with {choice}..."
    )

    # Snapshot instance + client at entry, before any thread/await handoff.
    instance_name, client = _resolve_client_and_instance()

    existing = _get_in_flight(conversation_id)
    if existing is not None:
        _guard_project(conversation_id, existing.project_key, project_key)
        return compact_json(omit_empty(await run_blocking(_handle_existing_turn, existing)))

    entry, rehydrated = await run_blocking(
        _resolve_entry, conversation_id, project_key, instance_name, client
    )

    # The delete confirmation is validated AND consumed INSIDE _begin_turn, under
    # the registry lock and after the overlap check (see _consume_confirmation).
    # This makes the whole check-and-consume atomic: two concurrent answers can
    # never both validate the same id, and a losing overlapping caller exits with
    # in_progress BEFORE touching the handle, so it can never write or replay a
    # stale pending id. The authoritative source is the single handle pending id —
    # a live cache hit keeps the id the caller saw; a post-restart rehydration was
    # already seeded from the durable store by _resolve_entry.
    timeout = _clamp_timeout(timeout_seconds)

    def _call():
        return entry.conversation.answer_confirmation(choice)

    try:
        turn = await run_blocking(
            _begin_turn,
            conversation_id,
            entry,
            _call,
            kind="answer",
            allow_edit_project=True,  # an approved deletion is itself an edit
            rehydrated=rehydrated,
            client=client,
            confirmation=_ConfirmDirective(
                supplied_id=confirmation_id, rehydrated=rehydrated
            ),
        )
    except _CobuildInProgress as exc:
        _guard_project(conversation_id, exc.turn.project_key, project_key)
        return compact_json(omit_empty(await run_blocking(_handle_existing_turn, exc.turn)))
    except _CobuildSaturated as exc:
        return compact_json(
            omit_empty(
                _saturation_result(
                    conversation_id, project_key, instance_name, exc.running
                )
            )
        )
    # Persistence was armed inside _begin_turn, before the turn became visible.
    try:
        response, elapsed = await _wait_for_turn(turn, timeout, ctx)
    except _CobuildTimeout:
        return compact_json(omit_empty(_timeout_result(turn)))
    except Exception as exc:  # noqa: BLE001 - mapped to an error result
        elapsed = int(time.monotonic() - turn.started_at)
        return compact_json(omit_empty(await run_blocking(_finalize_error, turn, exc, elapsed)))
    return compact_json(omit_empty(await run_blocking(_finalize_response, turn, response, elapsed)))


@mcp.tool()
async def get_cobuild_turn_status(
    conversation_id: str, project_key: str, ctx: Context
) -> str:
    """Poll a Cobuild turn that returned ``status: timeout``. Never sends a message.

    While the retained turn is still running this returns ``status:
    in_progress``; once it finishes this settles it and returns that turn's real
    result (``completed`` / ``needs_confirmation`` / ``error``). Use this instead
    of re-sending to avoid overlapping turns.

    If the in-memory turn is gone but the durable store shows it was still
    running (the server restarted mid-turn), returns ``status: turn_lost`` — the
    worker thread did not survive, though the DSS-side turn may have completed;
    inspect the project rather than blindly re-sending. If the store holds a
    settled outcome, that outcome is reported from the store. If nothing is known
    for this conversation, returns ``status: error`` — there is nothing to poll.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Checking Cobuild turn status for conversation {conversation_id}...")

    # Snapshot the active instance at entry so a concurrent switch_instance cannot
    # leak another instance's turn under the same project key.
    instance_name = config.get_current_instance_name()

    # Sweep on poll too (not only on begin-turn): evict hung/settled turns and
    # keep the registry bounded. The sweep may write to the store, so run it off
    # the event-loop thread.
    await run_blocking(_sweep_under_lock)

    turn = _get_in_flight(conversation_id)
    if turn is None:
        record = await run_blocking(_store().read, conversation_id)
        if record is not None:
            _guard_project(
                conversation_id, str(record.get("project_key", "")), project_key
            )
            _guard_instance(
                conversation_id, str(record.get("instance_name", "")), instance_name
            )
            last = record.get("last_result_status")
            if last == "in_flight":
                # Marker set at turn start, never overwritten by the terminal
                # done-callback: the worker thread is gone (restart). Be honest.
                return compact_json(
                    omit_empty(
                        _turn_lost_result(conversation_id, project_key, instance_name)
                    )
                )
            if last in ("completed", "needs_confirmation", "error", "abandoned"):
                return compact_json(
                    omit_empty(
                        _store_reported_result(
                            conversation_id, project_key, instance_name, record
                        )
                    )
                )
        return compact_json(
            omit_empty(
                {
                    "conversation_id": conversation_id,
                    "project_key": project_key,
                    "instance_name": instance_name,
                    "status": "error",
                    "message": (
                        "No Cobuild turn is currently in progress for this "
                        "conversation; there is nothing to poll."
                    ),
                    "next_action": (
                        "Send work with send_cobuild_message. Only poll after a "
                        "send/answer returned status=timeout."
                    ),
                }
            )
        )
    _guard_project(conversation_id, turn.project_key, project_key)
    _guard_instance(conversation_id, turn.instance_name, instance_name)
    if not turn.future.done():
        return compact_json(omit_empty(_in_progress_result(turn)))
    return compact_json(omit_empty(await run_blocking(_settle_turn, turn)))


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List Cobuild conversations for the current instance + project.

    Reads the durable registry (merged with any live handles), so it survives
    server restarts. Each row carries whether a delete confirmation is pending
    and whether a turn is currently in flight.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing retained Cobuild conversations for project {project_key}...")

    current_instance_name = config.get_current_instance_name()
    # Sweep on list calls too (may write to the store), then read it — both off
    # the event-loop thread.
    await run_blocking(_sweep_under_lock)
    merged = dict(await run_blocking(_store().all))
    with _lock:
        for cid, entry in _conversations.items():
            merged.setdefault(
                cid,
                {
                    "instance_name": entry.instance_name,
                    "project_key": entry.project_key,
                    "created_at": entry.created_at,
                    "pending_confirmation_id": getattr(
                        entry.conversation, "_pending_confirmation_id", None
                    ),
                },
            )
        in_flight_ids = set(_in_flight)

    rows = [
        {
            "conversation_id": cid,
            "instance_name": record.get("instance_name"),
            "project_key": record.get("project_key"),
            "created_at": record.get("created_at"),
            "pending_confirmation_id": record.get("pending_confirmation_id"),
            "in_flight": cid in in_flight_ids,
        }
        for cid, record in merged.items()
        if record.get("instance_name") == current_instance_name
        and record.get("project_key") == project_key
    ]
    rows.sort(key=lambda row: row.get("created_at") or "")

    return compact_json(
        {
            "conversations": columnar(
                rows,
                [
                    "conversation_id",
                    "instance_name",
                    "project_key",
                    "created_at",
                    "pending_confirmation_id",
                    "in_flight",
                ],
            )
        }
    )
