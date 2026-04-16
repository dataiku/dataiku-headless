"""dku project — list, get, export, create, delete, duplicate, variables, permissions, tags, ai-describe, timeline."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS projects.")


@app.command("list")
def list_projects(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all projects."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        projects = client.list_project_keys()
        data = []
        for key in projects:
            try:
                proj = client.get_project(key)
                meta = proj.get_metadata()
                data.append(
                    {
                        "key": key,
                        "name": meta.get("label", key),
                        "short_desc": meta.get("shortDesc", ""),
                    }
                )
            except Exception:
                data.append({"key": key, "name": key, "short_desc": ""})

        render(
            data,
            ["key", "name", "short_desc"],
            output_format=output,
            title="Projects",
            headers={"key": "KEY", "name": "NAME", "short_desc": "DESCRIPTION"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get project details."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        meta = proj.get_metadata()

        data = [
            {"field": "Key", "value": project_key},
            {"field": "Name", "value": meta.get("label", project_key)},
            {"field": "Description", "value": meta.get("shortDesc", "")},
            {"field": "Datasets", "value": str(len(proj.list_datasets()))},
            {"field": "Recipes", "value": str(len(proj.list_recipes()))},
            {"field": "Scenarios", "value": str(len(proj.list_scenarios()))},
        ]

        render(
            data,
            ["field", "value"],
            output_format=output,
            title=f"Project: {project_key}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def inspect(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """One-shot project summary: datasets, recipes, flow, scenarios, jobs, wiki, variables."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        meta = proj.get_metadata()

        # Datasets
        datasets = proj.list_datasets()
        ds_info = [
            {"name": d.get("name", d.get("id", "")), "type": d.get("type", "")}
            for d in datasets
        ]

        # Recipes
        recipes = proj.list_recipes()
        recipe_info = [
            {"name": r.get("name", ""), "type": r.get("type", "")} for r in recipes
        ]

        # Scenarios
        scenarios = proj.list_scenarios()
        scen_info = []
        for s in scenarios:
            scen_info.append(
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "active": s.get("active", False),
                }
            )

        # Flow sources
        try:
            flow = proj.get_flow()
            graph_obj = flow.get_graph()
            downstream_nodes: set = set()
            for node_id, node in graph_obj.nodes.items():
                downstream_nodes.update(node.get("successors", []))
            source_nodes = [
                node_id
                for node_id, node in graph_obj.nodes.items()
                if node_id not in downstream_nodes
                and node.get("type") == "COMPUTABLE_DATASET"
            ]
        except Exception:
            source_nodes = []

        # Jobs (last 5)
        jobs = proj.list_jobs()
        job_info = []
        for j in jobs[:5]:
            job_info.append(
                {
                    "id": j.get("def", {}).get("id", ""),
                    "state": j.get("state", ""),
                }
            )

        # Wiki
        try:
            wiki = proj.get_wiki()
            articles = wiki.list_articles()
            wiki_info = []
            for a in articles:
                article_data = a.get_data()
                wiki_info.append({"id": a.article_id, "title": article_data.get_name()})
        except Exception as exc:
            articles = []
            wiki_info = []
            warn(f"Could not fetch wiki: {exc}")

        # Variables
        try:
            variables = proj.get_variables()
            standard_vars = variables.get("standard", {})
        except Exception as exc:
            standard_vars = {}
            warn(f"Could not fetch variables: {exc}")

        if output == "json":
            result_data = {
                "key": key,
                "name": meta.get("label", key),
                "description": meta.get("shortDesc", ""),
                "datasets": ds_info,
                "recipes": recipe_info,
                "scenarios": scen_info,
                "flow_sources": source_nodes,
                "recent_jobs": job_info,
                "wiki_articles": wiki_info,
                "variables": standard_vars,
                "counts": {
                    "datasets": len(datasets),
                    "recipes": len(recipes),
                    "scenarios": len(scenarios),
                    "jobs": len(jobs),
                    "wiki_articles": len(articles),
                },
            }
            render_raw(result_data, output_format="json")
        else:
            data = [
                {"section": "Name", "detail": meta.get("label", key)},
                {"section": "Description", "detail": meta.get("shortDesc", "")},
                {
                    "section": "Datasets",
                    "detail": f"{len(datasets)}: {', '.join(d['name'] for d in ds_info[:10])}"
                    + ("..." if len(ds_info) > 10 else ""),
                },
                {
                    "section": "Recipes",
                    "detail": f"{len(recipes)}: {', '.join(r['name'] for r in recipe_info[:10])}"
                    + ("..." if len(recipe_info) > 10 else ""),
                },
                {
                    "section": "Scenarios",
                    "detail": f"{len(scenarios)}: {', '.join(s['id'] for s in scen_info[:10])}"
                    + ("..." if len(scen_info) > 10 else ""),
                },
                {
                    "section": "Flow Sources",
                    "detail": ", ".join(source_nodes[:10]) or "(none)",
                },
                {
                    "section": "Recent Jobs",
                    "detail": ", ".join(f"{j['id']}({j['state']})" for j in job_info)
                    or "(none)",
                },
                {
                    "section": "Wiki Articles",
                    "detail": f"{len(articles)}: {', '.join(w['title'] for w in wiki_info[:10])}"
                    + ("..." if len(wiki_info) > 10 else ""),
                },
                {
                    "section": "Variables",
                    "detail": ", ".join(
                        f"{k}={v}" for k, v in list(standard_vars.items())[:10]
                    )
                    or "(none)",
                },
            ]
            render(
                data,
                ["section", "detail"],
                output_format="table",
                title=f"Project Inspect: {key}",
                headers={"section": "SECTION", "detail": "DETAIL"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def export(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    dest: Path = typer.Option(".", "--dest", "-d", help="Destination directory"),
) -> None:
    """Export project as ZIP."""
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{project_key}.zip"

        proj.export_to_file(str(out_path))

        success(f"Exported to {out_path}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    description: str = typer.Option(
        "", "--description", "-d", help="Short description"
    ),
    owner: Optional[str] = typer.Option(
        None, "--owner", help="Project owner login (default: current user)"
    ),
    folder_id: Optional[str] = typer.Option(
        None, "--folder", help="Project folder ID to create in"
    ),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if project already exists"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new project."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        project_owner = owner or client.get_auth_info()["authIdentifier"]
        kwargs: dict = {}
        if folder_id:
            kwargs["project_folder_id"] = folder_id
        if tags:
            kwargs["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        client.create_project(
            project_key, name, project_owner, description=description, **kwargs
        )

        data = [
            {"field": "Key", "value": project_key},
            {"field": "Name", "value": name},
            {"field": "Owner", "value": project_owner},
            {"field": "Description", "value": description},
        ]

        render(
            data,
            ["field", "value"],
            output_format=output,
            title="Project Created",
        )
        success(f"Created project {project_key}")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(f"Project '{project_key}' already exists, skipping create")
            return
        if is_already_exists_error(e):
            exit_with_error(
                f"Project '{project_key}' already exists.",
                code="already_exists",
                details=[
                    "Use --if-not-exists to skip creation when the project exists.",
                    f"Or delete first: dku project delete {project_key} --yes",
                ],
            )
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
    drop_data: bool = typer.Option(
        False,
        "--drop-data",
        "--clear-managed",
        help="Also drop the backing storage of managed datasets and managed folders (physical SQL tables, managed folder contents). Without this flag, managed datasets' backing tables are orphaned on the target connection.",
    ),
) -> None:
    """Delete a project. Requires --confirm / --yes flag.

    By default, backing storage of managed datasets (e.g. physical PostgreSQL
    tables for managed SQL datasets) is NOT dropped. Pass --drop-data to also
    clear them.
    """
    if not confirm:
        error(
            "Deletion requires --confirm (or --yes / -y) flag. This action is irreversible."
        )
        raise typer.Exit(1)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.delete(
            clear_managed_datasets=drop_data,
            clear_output_managed_folders=drop_data,
        )
        success(f"Deleted project {project_key}")
        if not drop_data:
            info(
                "Managed datasets' backing storage was NOT dropped. "
                "Re-run with --drop-data to also clear backing SQL tables and managed folder contents."
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def duplicate(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Source project key"),
    target_key: str = typer.Option(..., "--target-key", help="New project key"),
    target_name: str = typer.Option(..., "--target-name", help="New project name"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Duplicate a project."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.duplicate(target_project_key=target_key, target_project_name=target_name)

        data = [
            {"field": "Source", "value": project_key},
            {"field": "Target Key", "value": target_key},
            {"field": "Target Name", "value": target_name},
        ]

        render(
            data,
            ["field", "value"],
            output_format=output,
            title="Project Duplicated",
        )
        success(f"Duplicated {project_key} → {target_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="New short description"
    ),
) -> None:
    """Update project name and/or description."""
    if name is None and description is None:
        error("Provide --name and/or --description to update.")
        raise typer.Exit(1)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        meta = proj.get_metadata()

        if name is not None:
            meta["label"] = name
        if description is not None:
            meta["shortDesc"] = description

        proj.set_metadata(meta)
        success(f"Updated metadata for {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def variables(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project variables."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        vars_data = proj.get_variables()
        render_raw(vars_data, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-variables")
def set_variables(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    set_var: Optional[List[str]] = typer.Option(
        None, "--set", help="Set standard variable (key=value)"
    ),
    definition: Optional[str] = typer.Option(
        None,
        "--definition",
        help="Full variables JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Set project variables. Use --set for individual standard vars or --definition to replace all."""
    key = project_key or project
    key = resolve_project(key)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)

        if definition is not None:
            new_vars = read_json_input(definition)
            proj.set_variables(new_vars)
            success(f"Replaced variables for {key}")
        elif set_var:
            current = proj.get_variables()
            standard = current.get("standard", {})
            for item in set_var:
                if "=" not in item:
                    error(f"Invalid format: {item}. Use key=value.")
                    raise typer.Exit(1)
                k, v = item.split("=", 1)
                standard[k] = v
            current["standard"] = standard
            proj.set_variables(current)
            success(f"Updated standard variables for {key}")
        else:
            error("Provide --set key=value or --definition JSON.")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def permissions(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project permissions."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        perms = proj.get_permissions()
        render_raw(perms, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-permissions")
def set_permissions(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Permissions JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Set project permissions from JSON definition."""
    key = project_key or project
    key = resolve_project(key)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        perms = read_json_input(definition)
        proj.set_permissions(perms)
        success(f"Updated permissions for {key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def tags(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project tags."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        meta = proj.get_metadata()
        tag_list = meta.get("tags", [])
        render_raw(tag_list, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("ai-describe")
def ai_describe(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    language: str = typer.Option(
        "english",
        "--language",
        "-l",
        help="Language (english, french, german, dutch, portuguese, spanish, japanese)",
    ),
    purpose: str = typer.Option(
        "generic",
        "--purpose",
        help="Purpose: generic, technical, business_oriented, executive",
    ),
    length: str = typer.Option(
        "medium",
        "--length",
        help="Length: low, medium, high",
    ),
    save: bool = typer.Option(
        False, "--save", help="Save generated description to the project"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Generate AI-powered description for a project.

    Requires 'Generate Metadata' enabled in DSS AI Services admin settings.

    Example:
      dku project ai-describe PROJ
      dku project ai-describe PROJ --purpose technical --save
    """
    key = project_key or project
    key = resolve_project(key)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        result = proj.generate_ai_description(
            language=language,
            purpose=purpose,
            length=length,
            save_description=save,
        )

        if fmt == "json":
            render_raw(result, output_format="json")
        else:
            if save:
                success(f"AI description saved for project '{key}'")
            else:
                info("AI-generated description (not saved — use --save to persist):")
            msg = result.get("msg", "")
            if msg:
                info(msg)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def timeline(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    limit: int = typer.Option(20, "--limit", help="Max number of timeline items"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project timeline: creation, contributors, recent modifications.

    Example:
      dku project timeline PROJ
      dku project timeline PROJ --limit 50 -o json
    """
    key = project_key or project
    key = resolve_project(key)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        tl = proj.get_timeline(item_count=limit)

        if fmt == "json":
            render_raw(tl, output_format="json")
        else:
            # Format timestamps
            def _fmt_ts(ts):
                if not ts:
                    return ""
                try:
                    from datetime import datetime, timezone

                    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )
                except Exception:
                    return str(ts)

            created_by = tl.get("createdBy", {}).get("login", "unknown")
            last_by = tl.get("lastModifiedBy", {}).get("login", "unknown")

            info(f"Created by: {created_by} on {_fmt_ts(tl.get('createdOn'))}")
            info(f"Last modified by: {last_by} on {_fmt_ts(tl.get('lastModifiedOn'))}")

            contributors = tl.get("allContributors", [])
            if contributors:
                logins = [c.get("login", "") for c in contributors]
                info(f"Contributors: {', '.join(logins)}")

            items = tl.get("items", [])
            if items:
                data = []
                for item in items[:limit]:
                    data.append(
                        {
                            "time": _fmt_ts(item.get("time")),
                            "user": item.get("user", ""),
                            "action": item.get("action", ""),
                            "object": item.get("objectId", ""),
                        }
                    )
                render(
                    data,
                    ["time", "user", "action", "object"],
                    output_format=fmt,
                    title=f"Timeline ({key})",
                    headers={
                        "time": "TIME",
                        "user": "USER",
                        "action": "ACTION",
                        "object": "OBJECT",
                    },
                )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
