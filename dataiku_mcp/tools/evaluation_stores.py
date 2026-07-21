"""Inspection tools for Dataiku DSS Evaluation Stores."""

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_allowed_value,
    require_non_empty_string,
)


@mcp.tool()
async def list_evaluation_stores(
    project_key: str,
    flavor: str,
    ctx: Context,
) -> str:
    """List the Evaluation Stores in the project with IDs, names, flavors, and evaluation counts."""
    project_key = require_non_empty_string(project_key, "project_key")
    flavor = require_allowed_value(flavor, "flavor", {"TABULAR", "AGENT", "LLM"})
    await ctx.info(f"Listing {flavor} evaluation stores in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        stores = project.list_evaluation_stores(flavor=flavor)
        result = []
        for store in stores:
            try:
                settings = store.get_settings().settings
                result.append(
                    {
                        "evaluation_store_id": store.id,
                        "name": settings.get("name", ""),
                        "flavor": settings.get("mesFlavor", ""),
                        "evaluation_count": len(store.list_evaluations()),
                    }
                )
            except DataikuException as exc:
                result.append(
                    {"evaluation_store_id": store.id, "error": str(exc)}
                )
        return columnar(
            result,
            ["evaluation_store_id", "name", "flavor", "evaluation_count", "error"],
        )

    return compact_json(await run_blocking(_run))
