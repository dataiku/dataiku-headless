"""Saved model inspection tools."""

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.auth import get_dss_client
from ..utils.serialization import columnar, compact_json
from ..utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool()
async def list_saved_models(project_key: str, ctx: Context) -> str:
    """List the saved models in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    raw_models = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_saved_models()
    )
    result = [
        {
            "id": model["id"],
            "name": model.get("name", ""),
            "type": model.get("type", ""),
            "miniTask": model.get("miniTask", {}).get("taskType", ""),
        }
        for model in raw_models
    ]
    return compact_json(columnar(result, ["id", "name", "type", "miniTask"]))
