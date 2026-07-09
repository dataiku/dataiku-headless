"""Cross-project sharing of flow items via DSS shared objects."""

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
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
        except DataikuException as e:
            _raise_if_forbidden(project_key, e)
            raise
        return [
            {"type": o.get("type"), "local_name": o.get("localName"),
             "target_projects": [r.get("targetProject") for r in o.get("rules", [])]}
            for o in settings.get_raw().get("exposedObjects", {}).get("objects", [])
        ]

    return compact_json(columnar(await run_blocking(_run), ["type", "local_name", "target_projects"]))


@mcp.tool()
async def share_objects(
    project_key: str,
    items: list[dict],
    target_project: str,
    ctx: Context,
) -> str:
    """Share objects from this project to one target project as read-only inputs. Idempotent.

    Args:
        items: List of `{"type", "local_name"}` dicts. See the cross-project-sharing skill for `local_name` semantics per type.
        target_project: Project key that should receive the shares.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    target_project = _require_non_empty_string(target_project, "target_project")
    await ctx.info(f"Sharing {len(items)} object(s) from {project_key} to {target_project}...")

    def _run():
        try:
            settings = get_dss_client().get_project(project_key).get_settings()
            for it in items:
                settings.add_exposed_object(it["type"], it["local_name"], target_project)
            settings.save()
        except DataikuException as e:
            _raise_if_forbidden(project_key, e)
            raise

    await run_blocking(_run)
    return compact_json({"project_key": project_key})


@mcp.tool()
async def unshare_objects(
    project_key: str,
    items: list[dict],
    target_project: str,
    ctx: Context,
) -> str:
    """Remove shares for the given items toward target_project. Idempotent.

    Args:
        items: List of `{"type", "local_name"}` dicts.
        target_project: Project key whose share rules should be removed.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    target_project = _require_non_empty_string(target_project, "target_project")
    keys = {(i["type"], i["local_name"]) for i in items}
    await ctx.info(f"Unsharing {len(items)} object(s) from {project_key} toward {target_project}...")

    def _run():
        try:
            settings = get_dss_client().get_project(project_key).get_settings()
            raw = settings.get_raw()
            eo = raw.setdefault("exposedObjects", {}).setdefault("objects", [])
            for obj in eo:
                if (obj.get("type"), obj.get("localName")) in keys:
                    obj["rules"] = [r for r in obj.get("rules", []) if r.get("targetProject") != target_project]
            raw["exposedObjects"]["objects"] = [
                o for o in eo if (o.get("type"), o.get("localName")) not in keys or o.get("rules")
            ]
            settings.save()
        except DataikuException as e:
            _raise_if_forbidden(project_key, e)
            raise

    await run_blocking(_run)
    return compact_json({"project_key": project_key})
