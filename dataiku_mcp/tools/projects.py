"""Project exploration, listing, and limited creation tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.redaction import redact_sensitive_values
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

_DEFAULT_OVERVIEW_ITEMS = 200
_MAX_OVERVIEW_ITEMS = 1_000
_MAX_OVERVIEW_JOBS = 100
_MAX_TEXT_CHARS = 2_000


@mcp.tool()
async def count_projects(ctx: Context) -> str:
    """Count projects on the Dataiku instance without listing project metadata."""
    await ctx.info("Counting Dataiku projects...")
    project_keys = await run_blocking(lambda: get_dss_client().list_project_keys())
    return compact_json({"project_count": len(project_keys)})


@mcp.tool()
async def list_projects(ctx: Context, search: str = "") -> str:
    """List the projects on the Dataiku instance."""
    await ctx.info("Listing Dataiku projects...")
    raw_projects = await run_blocking(lambda: get_dss_client().list_projects())
    projects = [
        {
            "projectKey": project["projectKey"],
            "name": project.get("name", ""),
            "shortDesc": project.get("shortDesc", ""),
        }
        for project in raw_projects
    ]
    if search:
        q = search.lower()
        projects = [
            project
            for project in projects
            if q in project["projectKey"].lower()
            or q in project["name"].lower()
            or q in project["shortDesc"].lower()
        ]
    return compact_json({"projects": columnar(projects, ["projectKey", "name", "shortDesc"])})


@mcp.tool()
async def create_project(
    project_key: str,
    name: str,
    ctx: Context,
    short_desc: str = "",
) -> str:
    """Create a new project on the Dataiku instance."""
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Creating project '{project_key}'...")

    def _run():
        client = get_dss_client()
        auth_info = client.get_auth_info()
        owner = auth_info.get("authIdentifier", "")
        client.create_project(project_key, name, owner=owner, description=short_desc)
        return omit_empty({"projectKey": project_key, "name": name, "owner": owner})

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_project_metadata(project_key: str, ctx: Context) -> str:
    """Get project metadata: label, descriptions, tags, and checklists."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching metadata for project {project_key}...")
    metadata = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_metadata()
    )
    return compact_json(metadata)


@mcp.tool()
async def get_project_variables(
    project_key: str,
    ctx: Context,
    include_local: bool = False,
) -> str:
    """Get redacted project variables; local overrides are opt-in.

    Credential-like values are replaced with ``***REDACTED***``. Local variables
    are excluded unless ``include_local=True`` because they often contain
    instance-specific credentials.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    client = get_dss_client()
    await ctx.info(
        f"Fetching variables for project {project_key} "
        f"(include_local={include_local})..."
    )
    variables = await run_blocking(
        lambda: client.get_project(project_key).get_variables()
    )
    result = {"standard": _redact_variables(variables.get("standard", {}))}
    if include_local:
        result["local"] = _redact_variables(variables.get("local", {}))
    return compact_json(result)


def _clip_text(value, limit: int = _MAX_TEXT_CHARS) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _redact_variables(section) -> dict:
    """Field-name redact a variables section, then clip oversized top-level strings.

    Variables are conventionally flat key/value pairs. The shared recursive
    redactor masks any credential-shaped field (nested included); the clip only
    bounds top-level string values so a giant blob can't blow up the response.
    """
    redacted = redact_sensitive_values(section or {})
    if not isinstance(redacted, dict):
        return redacted
    return {
        key: _clip_text(value) if isinstance(value, str) else value
        for key, value in redacted.items()
    }


def _limit_rows(rows: list, limit: int, warnings: list[str], section: str) -> list:
    if len(rows) > limit:
        warnings.append(f"{section}: returning {limit} of {len(rows)} items")
    return rows[:limit]


def _project_identity(project) -> dict:
    meta = project.get_metadata()
    return omit_empty(
        {
            "name": _clip_text(meta.get("label", ""), 512),
            "description": _clip_text(meta.get("shortDesc", "")),
        }
    )


def _flow_source_datasets(project) -> list:
    graph = project.get_flow().get_graph()
    return [
        node.get("ref")
        for node in graph.nodes.values()
        if node.get("type") == "COMPUTABLE_DATASET" and not node.get("predecessors")
    ]


def _wiki_articles(project) -> list:
    wiki = project.get_wiki()
    return [
        {
            "id": _clip_text(article.article_id, 512),
            "title": _clip_text(article.get_data().get_name(), 512),
        }
        for article in wiki.list_articles()
    ]


def _assemble_overview(
    project_key: str,
    *,
    identity,
    datasets,
    recipes,
    folders,
    scenarios,
    flow_sources,
    recent_jobs,
    wiki_articles,
    variables,
    counts,
    warnings,
) -> dict:
    def table(rows, columns):
        return columnar(rows, columns) if rows else None

    return omit_empty(
        {
            "project_key": project_key,
            "identity": identity or None,
            "datasets": table(datasets, ["name", "type"]),
            "recipes": table(recipes, ["name", "type"]),
            "folders": table(folders, ["id", "name"]),
            "scenarios": table(scenarios, ["id", "name", "active"]),
            "flow_sources": flow_sources or None,
            "recent_jobs": table(recent_jobs, ["id", "state"]),
            "wiki_articles": table(wiki_articles, ["id", "title"]),
            "variables": variables or None,
            "counts": omit_empty(counts) or None,
            "warnings": warnings or None,
        }
    )


@mcp.tool()
async def get_project_overview(
    project_key: str,
    ctx: Context,
    jobs_limit: int = 5,
    items_limit: int = _DEFAULT_OVERVIEW_ITEMS,
) -> str:
    """Call this first when orienting on a project — one call replaces the list_* fan-out.

    Returns identity, datasets, recipes, folders, scenarios, flow sources, recent jobs,
    wiki articles, standard variables, and counts as one dense payload. Each section is
    fetched independently: if one fails it is omitted and the reason is appended to
    ``warnings`` rather than failing the whole call. ``items_limit`` bounds each asset
    list (maximum 1000); counts still report the full section size. Standard variables
    have credential-shaped fields redacted; oversized values are clipped. Local
    variables are never returned here.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    jobs_limit = _require_positive_int(jobs_limit, "jobs_limit")
    items_limit = _require_positive_int(items_limit, "items_limit")
    if jobs_limit > _MAX_OVERVIEW_JOBS:
        raise ValueError(f"'jobs_limit' must be <= {_MAX_OVERVIEW_JOBS}")
    if items_limit > _MAX_OVERVIEW_ITEMS:
        raise ValueError(f"'items_limit' must be <= {_MAX_OVERVIEW_ITEMS}")
    # Bind the request to one DSS instance before the first await. A concurrent
    # switch_instance call cannot retarget the work halfway through this tool.
    client = get_dss_client()
    await ctx.info(f"Building project overview for {project_key}...")

    def _run():
        project = client.get_project(project_key)
        warnings: list[str] = []

        def section(name, producer):
            try:
                return producer()
            except Exception as exc:  # failure-isolated: never abort the whole tool
                # Backend exception text can include URLs or connection details.
                # The exception class identifies the failure without echoing it.
                warnings.append(f"{name}: read failed ({type(exc).__name__})")
                return None

        identity = section("identity", lambda: _project_identity(project))
        datasets = section(
            "datasets",
            lambda: project.list_datasets(),
        )
        recipes = section(
            "recipes",
            lambda: project.list_recipes(),
        )
        folders = section(
            "folders",
            lambda: project.list_managed_folders(),
        )
        scenarios = section(
            "scenarios",
            lambda: project.list_scenarios(),
        )
        flow_sources = section("flow_sources", lambda: _flow_source_datasets(project))
        recent_jobs = section(
            "recent_jobs",
            lambda: project.list_jobs(),
        )
        wiki_articles = section("wiki_articles", lambda: _wiki_articles(project))
        variables = section("variables", lambda: project.get_variables().get("standard", {}))

        counts = {
            "datasets": len(datasets) if datasets is not None else None,
            "recipes": len(recipes) if recipes is not None else None,
            "folders": len(folders) if folders is not None else None,
            "scenarios": len(scenarios) if scenarios is not None else None,
            "wiki_articles": len(wiki_articles) if wiki_articles is not None else None,
        }

        if datasets is not None:
            datasets = _limit_rows(datasets, items_limit, warnings, "datasets")
            datasets = [
                {
                    "name": _clip_text(d.get("name", d.get("id", "")), 512),
                    "type": _clip_text(d.get("type", ""), 256),
                }
                for d in datasets
            ]
        if recipes is not None:
            recipes = _limit_rows(recipes, items_limit, warnings, "recipes")
            recipes = [
                {
                    "name": _clip_text(r.get("name", ""), 512),
                    "type": _clip_text(r.get("type", ""), 256),
                }
                for r in recipes
            ]
        if folders is not None:
            folders = _limit_rows(folders, items_limit, warnings, "folders")
            folders = [
                {
                    "id": _clip_text(f.get("id", ""), 512),
                    "name": _clip_text(f.get("name", ""), 512),
                }
                for f in folders
            ]
        if scenarios is not None:
            scenarios = _limit_rows(scenarios, items_limit, warnings, "scenarios")
            scenarios = [
                {
                    "id": _clip_text(s.get("id", ""), 512),
                    "name": _clip_text(s.get("name", ""), 512),
                    "active": s.get("active", False),
                }
                for s in scenarios
            ]
        if flow_sources is not None:
            flow_sources = [
                _clip_text(item, 512)
                for item in _limit_rows(
                    flow_sources, items_limit, warnings, "flow_sources"
                )
            ]
        if recent_jobs is not None:
            recent_jobs = [
                {
                    "id": _clip_text(j.get("def", {}).get("id", ""), 512),
                    "state": _clip_text(j.get("state", ""), 128),
                }
                for j in recent_jobs[:jobs_limit]
            ]
        if wiki_articles is not None:
            wiki_articles = _limit_rows(
                wiki_articles, items_limit, warnings, "wiki_articles"
            )
        if variables is not None:
            variables = _redact_variables(variables)

        return _assemble_overview(
            project_key,
            identity=identity,
            datasets=datasets,
            recipes=recipes,
            folders=folders,
            scenarios=scenarios,
            flow_sources=flow_sources,
            recent_jobs=recent_jobs,
            wiki_articles=wiki_articles,
            variables=variables,
            counts=counts,
            warnings=warnings,
        )

    return compact_json(await run_blocking(_run))
