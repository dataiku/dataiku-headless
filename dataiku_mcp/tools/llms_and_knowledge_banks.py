"""LLM inspection tools."""

from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
)

LLM_PURPOSES = {
    "GENERIC_COMPLETION",
    "TEXT_EMBEDDING_EXTRACTION",
    "IMAGE_EMBEDDING_EXTRACTION",
    "RERANKING",
    "IMAGE_GENERATION",
}


def _serialize_llm_item(item: dict[str, Any], available_purposes: list[str]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("friendlyNameShort", ""),
        "type": item.get("type"),
        "connection": item.get("connection"),
        "model": item.get("model"),
        "available_purposes": available_purposes,
    }


def _list_llm_items(project_key: str, purpose: str) -> list:
    project = get_dss_client().get_project(project_key)
    return project.list_llms(purpose=purpose)


def _collect_llms(project_key: str, purpose: str | None) -> list[dict[str, Any]]:
    purposes = [purpose] if purpose is not None else sorted(LLM_PURPOSES)
    items_by_id: dict[str, dict[str, Any]] = {}
    purposes_by_id: dict[str, set[str]] = {}
    for current_purpose in purposes:
        for item in _list_llm_items(project_key, current_purpose):
            llm_id = item.get("id")
            if not isinstance(llm_id, str) or not llm_id.strip():
                continue
            if llm_id not in items_by_id:
                items_by_id[llm_id] = dict(item)
                purposes_by_id[llm_id] = set()
            purposes_by_id[llm_id].add(current_purpose)
    return [
        _serialize_llm_item(items_by_id[llm_id], sorted(purposes_by_id[llm_id]))
        for llm_id in sorted(items_by_id)
    ]


@mcp.tool()
async def list_llms(
    project_key: str,
    ctx: Context,
    purpose: str = "ALL",
) -> str:
    """List DSS-managed LLMs available in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    purpose = _require_non_empty_string(purpose, "purpose").upper()
    normalized_purpose = None if purpose == "ALL" else _require_allowed_value(
        purpose, "purpose", LLM_PURPOSES
    )
    await ctx.info(f"Listing LLMs in {project_key} for purpose={purpose}...")
    llms = await run_blocking(_collect_llms, project_key, normalized_purpose)
    return compact_json(
        {
            "purpose": purpose,
            "llms": columnar(
                llms,
                ["id", "name", "type", "connection", "model", "available_purposes"],
            ),
        }
    )
