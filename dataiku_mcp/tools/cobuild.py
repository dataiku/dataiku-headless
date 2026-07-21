"""Least-privilege Cobuild conversation tools.

This slice deliberately keeps the original synchronous conversation lifecycle.
It establishes the security contract that later persistence and retained-turn
work must preserve: edits are opt-in per message, deletion consent is bound to
the exact proposal id, and every state access is bound to the effective DSS
credential as well as the instance and project.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import os
from pathlib import Path
import threading

from dataikuapi.dss.cobuild import DSSCobuildConversation
from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client_and_principal
from .utils.conversation_store import (
    ConversationStore,
    ConversationStoreError,
    PendingConfirmationError,
)
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)


@dataclass
class _CobuildConversationEntry:
    instance_name: str
    project_key: str
    owner_fingerprint: str
    conversation: object
    created_at: str
    turn_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


_conversations: dict[str, _CobuildConversationEntry] = {}
_registry_lock = threading.RLock()


def _state_dir() -> Path:
    """Resolve durable state at call time so tests and operators can relocate it."""
    configured = os.environ.get("DKU_MCP_STATE_DIR", "").strip()
    if configured:
        return Path(configured)
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return base / "dataiku-headless"


def _store() -> ConversationStore:
    return ConversationStore(_state_dir() / "conversations.json")


def _capture_binding() -> tuple[str, object, str]:
    """Capture instance, client, and effective credential before the first await."""
    instance = config.get_current_instance()
    client, owner_fingerprint = get_dss_client_and_principal(instance)
    return instance.name, client, owner_fingerprint


def _get_conversation_entry(
    conversation_id: str,
    project_key: str,
    instance_name: str,
    owner_fingerprint: str,
) -> _CobuildConversationEntry:
    with _registry_lock:
        entry = _conversations.get(conversation_id)
    if entry is None:
        raise ValueError(
            f"Unknown Cobuild conversation_id '{conversation_id}'. "
            "Start a new conversation first."
        )
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
    if not hmac.compare_digest(entry.owner_fingerprint, owner_fingerprint):
        raise ValueError(
            f"Unknown Cobuild conversation_id '{conversation_id}' for the current "
            "credential. Start a new conversation with this credential."
        )
    return entry


def _resolve_conversation_entry(
    conversation_id: str,
    project_key: str,
    instance_name: str,
    client: object,
    owner_fingerprint: str,
) -> tuple[_CobuildConversationEntry, bool]:
    """Return a live entry or rehydrate a thin SDK handle from durable metadata."""
    try:
        return (
            _get_conversation_entry(
                conversation_id,
                project_key,
                instance_name,
                owner_fingerprint,
            ),
            False,
        )
    except ValueError as live_error:
        with _registry_lock:
            missing_live_entry = conversation_id not in _conversations
        if not missing_live_entry:
            raise

        record = _store().read_owned(
            conversation_id,
            instance_name=instance_name,
            project_key=project_key,
            owner_fingerprint=owner_fingerprint,
        )
        if record is None:
            raise live_error

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
        # Install-if-absent: a concurrent caller may have rehydrated while the
        # file was being read. Never replace a live handle carrying turn state.
        with _registry_lock:
            entry = _conversations.setdefault(conversation_id, candidate)
        _get_conversation_entry(
            conversation_id,
            project_key,
            instance_name,
            owner_fingerprint,
        )
        return entry, entry is candidate


def _persist_confirmation_or_fail_closed(
    conversation_id: str,
    entry: _CobuildConversationEntry,
    payload: dict,
) -> None:
    """Persist a returned delete proposal before exposing its approval token."""
    confirmation_id = payload.get("confirmation_id")
    if not confirmation_id:
        return
    try:
        _store().set_pending_confirmation(
            conversation_id,
            confirmation_id=confirmation_id,
            objects_to_delete=payload.get("objects_to_delete"),
            deletion_impacts=payload.get("deletion_impacts"),
            instance_name=entry.instance_name,
            project_key=entry.project_key,
            owner_fingerprint=entry.owner_fingerprint,
        )
    except BaseException:
        # The proposal cannot be recovered safely, so do not leave a live token
        # that could still approve it. A later prompt must obtain a new proposal.
        entry.conversation._pending_confirmation_id = None
        raise


def _serialize_response(
    conversation_id: str,
    entry: _CobuildConversationEntry,
    response,
) -> dict:
    is_confirmation = bool(
        response.is_confirmation_request
        or response.type == "delete_confirmation_request"
    )
    confirmation_id = (
        getattr(entry.conversation, "_pending_confirmation_id", None)
        if is_confirmation
        else None
    )
    if is_confirmation and not confirmation_id:
        raise RuntimeError(
            "Cobuild requested deletion confirmation without a confirmation id; "
            "refusing to expose an unapprovable proposal."
        )
    return omit_empty(
        {
            "conversation_id": conversation_id,
            "instance_name": entry.instance_name,
            "project_key": entry.project_key,
            "message": response.message,
            "response_type": response.type,
            "is_error": response.is_error,
            "is_confirmation_request": is_confirmation,
            "confirmation_id": confirmation_id,
            "objects_to_delete": response.objects_to_delete,
            "deletion_impacts": response.deletion_impacts,
        }
    )


@mcp.tool()
async def start_cobuild_conversation(project_key: str, ctx: Context) -> str:
    """Start a new Cobuild conversation for a project."""
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
            },
        )
        with _registry_lock:
            _conversations[conversation.conversation_id] = entry
        return omit_empty(
            {
                "conversation_id": conversation.conversation_id,
                "instance_name": entry.instance_name,
                "project_key": entry.project_key,
                "created_at": entry.created_at,
            }
        )

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def send_cobuild_message(
    conversation_id: str,
    project_key: str,
    message: str,
    ctx: Context,
    allow_edit_project: bool = False,
) -> str:
    """Send one Cobuild message; project editing is opt-in for this message only."""
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    message = _require_non_empty_string(message, "message")
    instance_name, client, owner_fingerprint = _capture_binding()
    entry, _rehydrated = await run_blocking(
        _resolve_conversation_entry,
        conversation_id,
        project_key,
        instance_name,
        client,
        owner_fingerprint,
    )
    await ctx.info(f"Sending Cobuild message to conversation {conversation_id}...")

    def _run():
        with entry.turn_lock:
            record = _store().read_owned(
                conversation_id,
                instance_name=instance_name,
                project_key=project_key,
                owner_fingerprint=owner_fingerprint,
            )
            if record is None:
                raise ConversationStoreError(
                    f"Conversation '{conversation_id}' disappeared from durable state."
                )
            if record.get("pending_confirmation_id"):
                raise PendingConfirmationError(
                    "This conversation has an unanswered deletion proposal. "
                    "Answer or cancel it before sending another message."
                )
            # A retained handle must use the credential from this request, not
            # whichever request happened to create the conversation.
            entry.conversation.client = client
            response = entry.conversation.send_message(
                message,
                allow_edit_project=allow_edit_project,
            )
            payload = _serialize_response(conversation_id, entry, response)
            _persist_confirmation_or_fail_closed(conversation_id, entry, payload)
            return payload

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def answer_cobuild_confirmation(
    conversation_id: str,
    project_key: str,
    choice: str,
    confirmation_id: str,
    ctx: Context,
) -> str:
    """Answer the exact pending deletion proposal with APPROVE or CANCEL.

    ``confirmation_id`` is required and must match the id returned with the
    proposal's objects and impacts. It is consumed before the SDK request, so an
    ambiguous transport failure cannot be retried as a blind second approval.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    choice = _require_non_empty_string(choice, "choice")
    confirmation_id = _require_non_empty_string(confirmation_id, "confirmation_id")
    if choice not in {"APPROVE", "CANCEL"}:
        raise ValueError("choice must be 'APPROVE' or 'CANCEL'")
    instance_name, client, owner_fingerprint = _capture_binding()
    entry, _rehydrated = await run_blocking(
        _resolve_conversation_entry,
        conversation_id,
        project_key,
        instance_name,
        client,
        owner_fingerprint,
    )
    await ctx.info(
        f"Answering Cobuild confirmation for conversation {conversation_id} with {choice}..."
    )

    def _run():
        with entry.turn_lock:
            live_pending = getattr(
                entry.conversation, "_pending_confirmation_id", None
            )
            if live_pending is not None and not hmac.compare_digest(
                str(live_pending), confirmation_id
            ):
                raise PendingConfirmationError(
                    "confirmation_id does not match the live deletion proposal."
                )
            _store().consume_pending_confirmation(
                conversation_id,
                confirmation_id,
                instance_name=instance_name,
                project_key=project_key,
                owner_fingerprint=owner_fingerprint,
            )
            entry.conversation.client = client
            # A rehydrated SDK handle needs the consumed server id restored just
            # for this one answer call. The SDK clears it before sending.
            entry.conversation._pending_confirmation_id = confirmation_id
            response = entry.conversation.answer_confirmation(choice)
            payload = _serialize_response(conversation_id, entry, response)
            _persist_confirmation_or_fail_closed(conversation_id, entry, payload)
            return payload

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List this credential's retained conversations without approval tokens."""
    project_key = _require_non_empty_string(project_key, "project_key")
    instance_name, _client, owner_fingerprint = _capture_binding()
    await ctx.info(f"Listing retained Cobuild conversations for project {project_key}...")

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
                    "has_pending_confirmation",
                ],
            )
        }
    )
