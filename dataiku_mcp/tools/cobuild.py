"""Cobuild conversation tools.

Edits are opt-in per message (``allow_edit_project`` defaults to ``False``) and
deletion consent is bound to the exact pending proposal id. Conversations are
retained in-memory and bound to their originating instance and project.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)


@dataclass
class _CobuildConversationEntry:
    instance_name: str
    project_key: str
    conversation: object
    created_at: str


_conversations: dict[str, _CobuildConversationEntry] = {}


def _get_conversation_entry(conversation_id: str, project_key: str) -> _CobuildConversationEntry:
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

    current_instance_name = config.get_current_instance_name()
    if entry.instance_name != current_instance_name:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to instance "
            f"'{entry.instance_name}', but the active instance is '{current_instance_name}'. "
            "Switch back to the original instance before reusing this conversation."
        )
    return entry


def _serialize_response(
    conversation_id: str,
    entry: _CobuildConversationEntry,
    response,
) -> dict:
    confirmation_id = (
        getattr(entry.conversation, "_pending_confirmation_id", None)
        if response.is_confirmation_request
        else None
    )
    return omit_empty(
        {
            "conversation_id": conversation_id,
            "instance_name": entry.instance_name,
            "project_key": entry.project_key,
            "message": response.message,
            "response_type": response.type,
            "is_error": response.is_error,
            "is_confirmation_request": response.is_confirmation_request,
            "confirmation_id": confirmation_id,
            "objects_to_delete": response.objects_to_delete,
            "deletion_impacts": response.deletion_impacts,
        }
    )


@mcp.tool()
async def start_cobuild_conversation(project_key: str, ctx: Context) -> str:
    """Start a new Cobuild conversation for a project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Starting Cobuild conversation for project {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        conversation = project.new_cobuild_conversation()
        entry = _CobuildConversationEntry(
            instance_name=config.get_current_instance_name(),
            project_key=project_key,
            conversation=conversation,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
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
    """Send one Cobuild message; project editing is opt-in for this message only.

    ``allow_edit_project`` defaults to ``False`` (read-only supervision). Pass
    ``True`` only for the single message that should be allowed to create or
    edit project objects; the grant does not carry over to later messages.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    message = _require_non_empty_string(message, "message")
    await ctx.info(f"Sending Cobuild message to conversation {conversation_id}...")

    entry = _get_conversation_entry(conversation_id, project_key)

    def _run():
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
    proposal's ``objects_to_delete`` and ``deletion_impacts``. A mismatched or
    already-consumed id is rejected before any SDK call, so an ambiguous
    transport failure cannot be retried as a blind second approval.
    """
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    choice = _require_non_empty_string(choice, "choice")
    confirmation_id = _require_non_empty_string(confirmation_id, "confirmation_id")
    if choice not in {"APPROVE", "CANCEL"}:
        raise ValueError("choice must be 'APPROVE' or 'CANCEL'")
    await ctx.info(
        f"Answering Cobuild confirmation for conversation {conversation_id} with {choice}..."
    )

    entry = _get_conversation_entry(conversation_id, project_key)

    pending = getattr(entry.conversation, "_pending_confirmation_id", None)
    if pending is None:
        raise ValueError(
            f"No pending confirmation for conversation '{conversation_id}'. "
            "Re-read a needs-confirmation response before answering."
        )
    # The confirmation id is not a secret, so a plain equality check is correct
    # here; it exists to bind the approval to the exact proposal, not to resist
    # timing attacks.
    if str(pending) != confirmation_id:
        raise ValueError(
            "confirmation_id does not match the pending deletion proposal. "
            "Inspect the latest objects_to_delete and deletion_impacts, then "
            "pass its exact confirmation_id."
        )

    def _run():
        response = entry.conversation.answer_confirmation(choice)
        return _serialize_response(conversation_id, entry, response)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List retained Cobuild conversations in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing retained Cobuild conversations for project {project_key}...")

    current_instance_name = config.get_current_instance_name()
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
        if entry.instance_name == current_instance_name
        and entry.project_key == project_key
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
