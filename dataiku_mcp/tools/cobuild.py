"""Process-local Cobuild conversations with safe retained turns."""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking, run_cobuild_blocking
from .utils.auth import get_current_instance_for_tool, get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import require_non_empty_string as _require_non_empty_string

INLINE_WAIT_SECONDS = 240


@dataclass
class _Turn:
    id: str
    task: asyncio.Task[dict] = field(init=False)
    observed: bool = False
    started: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Conversation:
    instance_name: str
    project_key: str
    sdk_conversation: object
    created_at: str
    turn: _Turn | None = None


_conversations: dict[str, _Conversation] = {}


def _entry(conversation_id: str, project_key: str) -> _Conversation:
    entry = _conversations.get(conversation_id)
    if entry is None:
        raise ValueError(
            f"Unknown Cobuild conversation_id '{conversation_id}'. Start a new conversation first."
        )
    if entry.project_key != project_key:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to project "
            f"'{entry.project_key}', not '{project_key}'."
        )
    active_instance = get_current_instance_for_tool().name
    if entry.instance_name != active_instance:
        raise ValueError(
            f"Cobuild conversation '{conversation_id}' belongs to instance "
            f"'{entry.instance_name}', but the active instance is '{active_instance}'."
        )
    return entry


def _turn_result(
    conversation_id: str, entry: _Conversation, turn: _Turn, response
) -> dict:
    response_type = str(getattr(response, "type", ""))
    confirmation_requested = bool(
        getattr(response, "is_confirmation_request", False)
        or response_type == "delete_confirmation_request"
    )
    is_error = bool(getattr(response, "is_error", False))
    result = {
        "status": "failed" if is_error else "completed",
        "conversation_id": conversation_id,
        "turn_id": turn.id,
        "instance_name": entry.instance_name,
        "project_key": entry.project_key,
        "message": str(getattr(response, "message", "")),
        "response_type": response_type,
        "is_error": is_error,
        "is_confirmation_request": confirmation_requested,
        "objects_to_delete": getattr(response, "objects_to_delete", None),
        "deletion_impacts": getattr(response, "deletion_impacts", None),
    }
    if is_error:
        result["error_type"] = "cobuild_response"
    return omit_empty(result)


def _in_progress(conversation_id: str, entry: _Conversation, turn: _Turn) -> dict:
    status = "in_progress" if turn.started.is_set() else "queued"
    return {
        "status": status,
        "conversation_id": conversation_id,
        "turn_id": turn.id,
        "next_action": (
            "The turn is queued for a Cobuild worker; poll after a short interval."
            if status == "queued"
            else "Poll get_cobuild_turn_status with this exact turn_id."
        ),
    }


def _require_turn_available(conversation_id: str, entry: _Conversation) -> None:
    turn = entry.turn
    if turn is None:
        return

    poll_payload = compact_json(
        {
            "conversation_id": conversation_id,
            "project_key": entry.project_key,
            "turn_id": turn.id,
        }
    )
    if not turn.task.done():
        status = "in progress" if turn.started.is_set() else "queued"
        raise ValueError(
            f"Cannot start a new Cobuild turn: current turn '{turn.id}' is {status}. "
            f"First call get_cobuild_turn_status with {poll_payload}."
        )
    if not turn.observed:
        raise ValueError(
            f"Cannot start a new Cobuild turn: current turn '{turn.id}' has a "
            "terminal result that has not been observed. First call "
            f"get_cobuild_turn_status with {poll_payload}."
        )


def _start_turn(conversation_id: str, entry: _Conversation, check, call) -> _Turn:
    _require_turn_available(conversation_id, entry)

    check()
    turn = _Turn(uuid.uuid4().hex)

    def run_turn() -> dict:
        turn.started.set()
        try:
            response = call()
        except Exception as exc:
            return {
                "status": "failed",
                "conversation_id": conversation_id,
                "turn_id": turn.id,
                "error_type": type(exc).__name__,
                "message": str(exc) or type(exc).__name__,
            }
        return _turn_result(conversation_id, entry, turn, response)

    turn.task = asyncio.create_task(run_cobuild_blocking(run_turn))
    entry.turn = turn
    return turn


async def _wait_for_turn(conversation_id: str, entry: _Conversation, turn: _Turn) -> dict:
    try:
        result = await asyncio.wait_for(
            asyncio.shield(turn.task), timeout=INLINE_WAIT_SECONDS
        )
    except asyncio.TimeoutError:
        return _in_progress(conversation_id, entry, turn)
    turn.observed = True
    return result


@mcp.tool()
async def start_cobuild_conversation(project_key: str, ctx: Context) -> str:
    """Start a new process-local Cobuild conversation for a project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Starting Cobuild conversation for project {project_key}...")

    instance_name = get_current_instance_for_tool().name
    client = get_dss_client()
    conversation = await run_blocking(
        lambda: client.get_project(project_key).new_cobuild_conversation()
    )
    entry = _Conversation(
        instance_name,
        project_key,
        conversation,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    _conversations[conversation.conversation_id] = entry
    return compact_json(
        {
            "conversation_id": conversation.conversation_id,
            "instance_name": entry.instance_name,
            "project_key": entry.project_key,
            "created_at": entry.created_at,
        }
    )


@mcp.tool()
async def send_cobuild_message(
    conversation_id: str,
    project_key: str,
    message: str,
    ctx: Context,
    allow_edit_project: bool = False,
) -> str:
    """Send one retained Cobuild turn; project edits are opt-in for this message."""
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    message = _require_non_empty_string(message, "message")
    await ctx.info(f"Sending Cobuild message to conversation {conversation_id}...")
    entry = _entry(conversation_id, project_key)

    def check():
        current_turn = entry.turn
        if current_turn and current_turn.task.result()["is_confirmation_request"]:
            raise ValueError(
                f"Cobuild conversation '{conversation_id}' has a pending confirmation request with {current_turn.id}. "
                "Run get_cobuild_turn_status() to review the pending confirmation, followed by answer_cobuild_confirmation()."
            )

    def call():
        return entry.sdk_conversation.send_message(
            message, allow_edit_project=allow_edit_project
        )

    turn = _start_turn(conversation_id, entry, check, call)
    return compact_json(await _wait_for_turn(conversation_id, entry, turn))


@mcp.tool()
async def answer_cobuild_confirmation(
    conversation_id: str,
    project_key: str,
    turn_id: str,
    choice: str,
    ctx: Context,
) -> str:
    """Answer the confirmation request issued by the exact current Cobuild turn."""
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    turn_id = _require_non_empty_string(turn_id, "turn_id")
    choice = _require_non_empty_string(choice, "choice")
    if choice not in {"APPROVE", "CANCEL"}:
        raise ValueError("choice must be 'APPROVE' or 'CANCEL'")
    await ctx.info(
        f"Answering Cobuild confirmation for conversation {conversation_id} with {choice}..."
    )
    entry = _entry(conversation_id, project_key)

    def check():
        current_turn = entry.turn
        if current_turn is None or current_turn.id != turn_id:
            raise ValueError(
                f"turn_id '{turn_id}' is not the current turn_id for Cobuild conversation '{conversation_id}'."
            )
        if not current_turn.task.result()["is_confirmation_request"]:
            raise ValueError(
                f"Cobuild conversation '{conversation_id}' turn_id '{turn_id}' does not request a confirmation."
            )

    turn = _start_turn(
        conversation_id,
        entry,
        check,
        lambda: entry.sdk_conversation.answer_confirmation(choice),
    )
    return compact_json(await _wait_for_turn(conversation_id, entry, turn))


@mcp.tool()
async def get_cobuild_turn_status(
    conversation_id: str, project_key: str, turn_id: str, ctx: Context
) -> str:
    """Wait for the exact current retained Cobuild turn, up to the inline limit."""
    conversation_id = _require_non_empty_string(conversation_id, "conversation_id")
    project_key = _require_non_empty_string(project_key, "project_key")
    turn_id = _require_non_empty_string(turn_id, "turn_id")
    entry = _entry(conversation_id, project_key)
    turn = entry.turn
    if turn is None or turn.id != turn_id:
        raise ValueError(
            f"turn_id '{turn_id}' is not the current turn_id for Cobuild conversation '{conversation_id}'."
        )
    return compact_json(await _wait_for_turn(conversation_id, entry, turn))


@mcp.tool()
async def list_cobuild_conversations(project_key: str, ctx: Context) -> str:
    """List process-local conversations and their current turn IDs."""
    project_key = _require_non_empty_string(project_key, "project_key")
    active_instance = get_current_instance_for_tool().name
    rows = [
        {
            "conversation_id": conversation_id,
            "instance_name": entry.instance_name,
            "project_key": entry.project_key,
            "created_at": entry.created_at,
            "current_turn_id": entry.turn.id if entry.turn else None,
            "current_turn_status": (
                None
                if entry.turn is None
                else entry.turn.task.result()["status"]
                if entry.turn.task.done()
                else "in_progress"
                if entry.turn.started.is_set()
                else "queued"
            ),
        }
        for conversation_id, entry in _conversations.items()
        if entry.instance_name == active_instance and entry.project_key == project_key
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
                    "current_turn_id",
                    "current_turn_status",
                ],
            )
        }
    )
