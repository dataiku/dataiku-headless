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
    """Get the project's standard variables, with credential-like values redacted.

    Values whose key matches the sensitive patterns (password/secret/token/key/
    credential families) are replaced with '***REDACTED***'. Local variables are
    opt-in via ``include_local=True`` because they more often hold credentials;
    they are redacted the same way.

    Returns ``{'standard': {...}}`` by default, or ``{'standard': {...},
    'local': {...}}`` when ``include_local=True``.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(
        f"Fetching variables for project {project_key} (include_local={include_local})..."
    )
    variables = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_variables()
    )
    result = {"standard": redact_sensitive_values(variables.get("standard", {}) or {})}
    if include_local:
        result["local"] = redact_sensitive_values(variables.get("local", {}) or {})
    return compact_json(result)


def _project_identity(project) -> dict:
    meta = project.get_metadata()
    return omit_empty(
        {"name": meta.get("label", ""), "description": meta.get("shortDesc", "")}
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
        {"id": article.article_id, "title": article.get_data().get_name()}
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
    warnings,
) -> dict:
    def table(rows, columns):
        return columnar(rows, columns) if rows else None

    counts = omit_empty(
        {
            "datasets": len(datasets) if datasets is not None else None,
            "recipes": len(recipes) if recipes is not None else None,
            "folders": len(folders) if folders is not None else None,
            "scenarios": len(scenarios) if scenarios is not None else None,
            "wiki_articles": len(wiki_articles) if wiki_articles is not None else None,
        }
    )

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
            "counts": counts or None,
            "warnings": warnings or None,
        }
    )


@mcp.tool()
async def get_project_overview(
    project_key: str,
    ctx: Context,
    jobs_limit: int = 5,
) -> str:
    """Call this first when orienting on a project — one call replaces the list_* fan-out.

    Returns identity, datasets, recipes, folders, scenarios, flow sources, recent jobs,
    wiki articles, standard variables, and counts as one dense payload. Each section is
    fetched independently: if one fails it is set to null and the reason is appended to
    ``warnings`` rather than failing the whole call.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    jobs_limit = _require_positive_int(jobs_limit, "jobs_limit")
    await ctx.info(f"Building project overview for {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        warnings: list[str] = []

        def section(name, producer):
            try:
                return producer()
            except Exception as exc:  # failure-isolated: never abort the whole tool
                warnings.append(f"{name}: {exc}")
                return None

        identity = section("identity", lambda: _project_identity(project))
        datasets = section(
            "datasets",
            lambda: [
                {"name": d.get("name", d.get("id", "")), "type": d.get("type", "")}
                for d in project.list_datasets()
            ],
        )
        recipes = section(
            "recipes",
            lambda: [
                {"name": r.get("name", ""), "type": r.get("type", "")}
                for r in project.list_recipes()
            ],
        )
        folders = section(
            "folders",
            lambda: [
                {"id": f.get("id", ""), "name": f.get("name", "")}
                for f in project.list_managed_folders()
            ],
        )
        scenarios = section(
            "scenarios",
            lambda: [
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "active": s.get("active", False),
                }
                for s in project.list_scenarios()
            ],
        )
        flow_sources = section("flow_sources", lambda: _flow_source_datasets(project))
        recent_jobs = section(
            "recent_jobs",
            lambda: [
                {"id": j.get("def", {}).get("id", ""), "state": j.get("state", "")}
                for j in project.list_jobs()[:jobs_limit]
            ],
        )
        wiki_articles = section("wiki_articles", lambda: _wiki_articles(project))
        variables = section(
            "variables",
            lambda: redact_sensitive_values(
                project.get_variables().get("standard", {}) or {}
            ),
        )

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
            warnings=warnings,
        )

    return compact_json(await run_blocking(_run))
