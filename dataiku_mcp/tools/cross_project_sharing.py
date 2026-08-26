"""Cross-project sharing inspection for Dataiku shared objects."""

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _raise_if_forbidden(project_key: str, exc: DataikuException) -> None:
    msg = str(exc)
    if "forbidden" in msg.lower() or "unauthorized" in msg.lower():
        raise PermissionError(
            f"Forbidden on source '{project_key}'. "
            f"Needs `Read project conf` + `Write project conf`."
        ) from exc


@mcp.tool()
async def list_shared_objects(project_key: str, ctx: Context) -> str:
    """List the objects this project shares with other projects."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing shared objects in {project_key}...")

    def _run():
        try:
            settings = get_dss_client().get_project(project_key).get_settings()
        except DataikuException as exc:
            _raise_if_forbidden(project_key, exc)
            raise
        return [
            {
                "type": obj.get("type"),
                "local_name": obj.get("localName"),
                "target_projects": [
                    rule.get("targetProject") for rule in obj.get("rules", [])
                ],
            }
            for obj in settings.get_raw().get("exposedObjects", {}).get("objects", [])
        ]

    rows = await run_blocking(_run)
    return compact_json(columnar(rows, ["type", "local_name", "target_projects"]))
