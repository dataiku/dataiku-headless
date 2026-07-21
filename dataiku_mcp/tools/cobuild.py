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
import threading

from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client_and_principal
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
        entry = _CobuildConversationEntry(
            instance_name=instance_name,
            project_key=project_key,
            owner_fingerprint=owner_fingerprint,
            conversation=conversation,
            created_at=datetime.now(timezone.utc).isoformat(),
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
    entry = _get_conversation_entry(
        conversation_id, project_key, instance_name, owner_fingerprint
    )
    await ctx.info(f"Sending Cobuild message to conversation {conversation_id}...")

    def _run():
        with entry.turn_lock:
            # A retained handle must use the credential from this request, not
            # whichever request happened to create the conversation.
            entry.conversation.client = client
            response = entry.conversation.send_message(
                message,
                allow_edit_project=allow_edit_project,
            )
            return _serialize_response(conversation_id, entry, response)

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
    entry = _get_conversation_entry(
        conversation_id, project_key, instance_name, owner_fingerprint
    )
    await ctx.info(
        f"Answering Cobuild confirmation for conversation {conversation_id} with {choice}..."
    )

    def _run():
        with entry.turn_lock:
            pending = getattr(entry.conversation, "_pending_confirmation_id", None)
            if pending is None:
                raise ValueError(
                    f"No pending confirmation for conversation '{conversation_id}'. "
                    "Re-read a needs-confirmation response before answering."
                )
            if not hmac.compare_digest(str(pending), confirmation_id):
                raise ValueError(
                    "confirmation_id does not match the pending deletion proposal. "
                    "Inspect the latest objects_to_delete and deletion_impacts, then "
                    "pass its exact confirmation_id."
                )
            entry.conversation.client = client
            response = entry.conversation.answer_confirmation(choice)
            return _serialize_response(conversation_id, entry, response)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List this credential's retained conversations without approval tokens."""
    project_key = _require_non_empty_string(project_key, "project_key")
    instance_name, _client, owner_fingerprint = _capture_binding()
    await ctx.info(f"Listing retained Cobuild conversations for project {project_key}...")

    with _registry_lock:
        rows = [
            {
                "conversation_id": conversation_id,
                "instance_name": entry.instance_name,
                "project_key": entry.project_key,
                "created_at": entry.created_at,
                "has_pending_confirmation": bool(
                    getattr(entry.conversation, "_pending_confirmation_id", None)
                ),
            }
            for conversation_id, entry in _conversations.items()
            if entry.instance_name == instance_name
            and entry.project_key == project_key
            and hmac.compare_digest(entry.owner_fingerprint, owner_fingerprint)
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
