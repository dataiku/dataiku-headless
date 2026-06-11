"""dku project — list, get, export, create, delete, duplicate, variables, permissions, tags, ai-describe, timeline."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    filter_fields,
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
    fields: str = typer.Option(
        None,
        "--fields",
        help="Comma-separated fields to include (key,name,short_desc)",
    ),
) -> None:
    """List all projects."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        # Single GET /projects/ returns all metadata; do NOT fetch per-project
        # (an N+1 that takes ~25s on instances with many projects and makes
        # agents wrapping calls in `timeout` give up). Verified live: the list
        # payload populates `name` and `shortDesc` directly, so no per-project
        # get_metadata() call is needed for names to render.
        projects = client.list_projects()
        data = [
            {
                "key": p["projectKey"],
                "name": p.get("name", p["projectKey"]),
                "short_desc": p.get("shortDesc", ""),
            }
            for p in projects
        ]

        data, keys = filter_fields(data, ["key", "name", "short_desc"], fields)

        render(
            data,
            keys,
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
) -> None:
    """Get project details.

    Output contract:
      - Default/quiet: compact JSON, because this is a single object.
      - JSON: the same canonical project dict, indented for `jq`/inspection.
      - CSV: a Field/Value summary.
      - IDs: the project key.
    """
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        meta = proj.get_metadata()

        payload = dict(meta)
        payload["key"] = project_key
        payload["counts"] = {
            "datasets": len(proj.list_datasets()),
            "recipes": len(proj.list_recipes()),
            "scenarios": len(proj.list_scenarios()),
        }

        if output in ("dense", "quiet", "json"):
            render_raw(payload, output_format=output)
            return

        if output == "ids":
            render([{"key": project_key}], ["key"], output_format="ids")
            return

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
        handle_api_error(e, project_key=project_key)


@app.command()
def inspect(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """One-shot project summary: datasets, recipes, flow, scenarios, jobs, wiki, variables."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format()
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

        # Managed folders
        try:
            folders = proj.list_managed_folders()
        except Exception as exc:
            folders = []
            warn(f"Could not fetch folders: {exc}")
        folder_info = [
            {"id": f.get("id", ""), "name": f.get("name", "")} for f in folders
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

        result_data = {
            "key": key,
            "name": meta.get("label", key),
            "description": meta.get("shortDesc", ""),
            "datasets": ds_info,
            "recipes": recipe_info,
            "folders": folder_info,
            "scenarios": scen_info,
            "flow_sources": source_nodes,
            "recent_jobs": job_info,
            "wiki_articles": wiki_info,
            "variables": standard_vars,
            "counts": {
                "datasets": len(datasets),
                "recipes": len(recipes),
                "folders": len(folders),
                "scenarios": len(scenarios),
                "jobs": len(jobs),
                "wiki_articles": len(articles),
            },
        }
        if output in ("dense", "quiet", "json"):
            render_raw(result_data, output_format=output)
            return

        if output == "ids":
            render([{"key": key}], ["key"], output_format="ids")
            return

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
                "section": "Folders",
                "detail": f"{len(folders)}: {', '.join(f['name'] for f in folder_info[:10])}"
                + ("..." if len(folder_info) > 10 else ""),
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
            output_format=output,
            title=f"Project Inspect: {key}",
            headers={"section": "SECTION", "detail": "DETAIL"},
        )
    except Exception as e:
        handle_api_error(e, project_key=key)


@app.command()
def export(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    dest: Path = typer.Option(".", "--dest", "-d", help="Destination directory"),
    with_data: bool = typer.Option(
        False,
        "--with-data/--no-with-data",
        help="Shortcut: export uploaded + managed-FS + all dataset data",
    ),
    uploads: bool = typer.Option(
        False, "--uploads", help="Export data of Uploaded datasets"
    ),
    managed_fs: bool = typer.Option(
        False, "--managed-fs", help="Export data of managed Filesystem datasets"
    ),
    managed_folders: bool = typer.Option(
        False, "--managed-folders", help="Export data of managed folders"
    ),
    all_datasets: bool = typer.Option(
        False, "--all-datasets", help="Export data of all datasets"
    ),
    all_input_datasets: bool = typer.Option(
        False, "--all-input-datasets", help="Export data of all input datasets"
    ),
    insights_data: bool = typer.Option(
        False, "--insights-data", help="Export data of static insights"
    ),
) -> None:
    """Export project as ZIP.

    By default no dataset/folder data is included (settings-only). Use
    --with-data for the common case, or the granular flags to pick exactly
    which data to bundle.
    """
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{project_key}.zip"

        # Map flags to export_to_file() option keys (verified against
        # dataikuapi DSSProject.export_to_file docstring). --with-data is a
        # convenience that turns on uploads + managed-FS + all datasets.
        options: dict = {}
        if uploads or with_data:
            options["exportUploads"] = True
        if managed_fs or with_data:
            options["exportManagedFS"] = True
        if all_datasets or with_data:
            options["exportAllDatasets"] = True
        if managed_folders:
            options["exportManagedFolders"] = True
        if all_input_datasets:
            options["exportAllInputDatasets"] = True
        if insights_data:
            options["exportInsightsData"] = True

        # Preserve the original settings-only behavior when no data flag is
        # set: call without options= so DSS uses its defaults.
        if options:
            proj.export_to_file(str(out_path), options=options)
        else:
            proj.export_to_file(str(out_path))

        success(f"Exported to {out_path}")
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command("import")
def import_project(
    ctx: typer.Context,
    archive_path: Path = typer.Argument(
        help="Path to the project archive (.zip) to import"
    ),
    target_key: Optional[str] = typer.Option(
        None,
        "--as",
        "-k",
        help="Project key to import under (default: original key in the archive)",
    ),
    remap_connection: List[str] = typer.Option(
        [],
        "--remap-connection",
        help="Connection remap SRC=TGT (repeatable, e.g. --remap-connection pg_old=pg_new)",
    ),
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Block until the import finishes (import is already synchronous; "
        "this is accepted for symmetry with other commands)",
    ),
) -> None:
    """Import a project from a ZIP archive (design node only).

    Remap source connections to existing target connections with
    --remap-connection SRC=TGT (repeatable). If the archive references a
    connection that does not exist on this node and is not remapped, DSS
    silently no-ops — this command detects that and tells you how to fix it.
    """
    try:
        client = get_client_from_ctx(ctx)

        if not archive_path.is_file():
            exit_with_error(
                f"Archive not found: {archive_path}",
                details=[
                    "Pass a path to an existing project export .zip.",
                    "Create one with: dku project export <KEY> --with-data --dest .",
                ],
            )

        # Parse --remap-connection SRC=TGT pairs into the remapping shape DSS
        # expects (verified against dataikuapi TemporaryImportHandle.execute:
        # settings["remapping"]["connections"] = [{"source":..,"target":..}]).
        connections = []
        for pair in remap_connection:
            if "=" not in pair:
                exit_with_error(
                    f"Invalid --remap-connection value: {pair!r}",
                    details=[
                        "Use SRC=TGT, e.g. --remap-connection pg_old=pg_new",
                    ],
                )
            src, tgt = pair.split("=", 1)
            src, tgt = src.strip(), tgt.strip()
            if not src or not tgt:
                exit_with_error(
                    f"Invalid --remap-connection value: {pair!r}",
                    details=[
                        "Both sides are required: --remap-connection SRC=TGT",
                    ],
                )
            connections.append({"source": src, "target": tgt})

        settings: dict = {}
        if target_key:
            settings["targetProjectKey"] = target_key
        if connections:
            settings["remapping"] = {"connections": connections}

        with open(archive_path, "rb") as f:
            handle = client.prepare_project_import(f)
            res = handle.execute(settings=settings if settings else None)

        # execute() returns {"success": bool, ...} and does NOT raise when a
        # target connection is missing — it silently no-ops. Always check the
        # flag (the dataikuapi docstring warns about this).
        res = res or {}
        if not res.get("success"):
            messages = []
            for m in res.get("messages", []) or []:
                if isinstance(m, dict):
                    text = m.get("message") or m.get("details") or str(m)
                else:
                    text = str(m)
                if text:
                    messages.append(text)
            details = list(messages)
            details.append("")
            details.append("Likely a connection/code-env referenced by the archive")
            details.append("does not exist on this node. Fix by either:")
            details.append(
                "  - creating the missing connection: dku connection create ..."
            )
            details.append(
                "  - re-running with a remap: "
                "dku project import "
                f"{archive_path} --remap-connection SRC=TGT"
            )
            exit_with_error(
                "Project import failed (DSS reported success=false).",
                details=details,
            )

        imported_key = (
            res.get("targetProjectKey")
            or res.get("projectKey")
            or target_key
            or "(original key from archive)"
        )
        success(f"Imported project {imported_key}")
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
) -> None:
    """Create a new project."""
    output = resolve_output_format()
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
        from dku_cli.output import hint

        hint(f"dku project get {project_key}")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(f"Project '{project_key}' already exists, skipping create")
            return
        if is_already_exists_error(e):
            exit_with_error(
                f"Project '{project_key}' already exists.",
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
    yes: bool = typer.Option(
        False, "--yes", "-y", "--confirm", help="Skip safety guard"
    ),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must match PROJECT_KEY literally to proceed (tier-3 guard).",
    ),
    drop_data: bool = typer.Option(
        False,
        "--drop-data",
        "--clear-managed",
        help="Also drop the backing storage of managed datasets and managed folders (physical SQL tables, managed folder contents). Without this flag, managed datasets' backing tables are orphaned on the target connection.",
    ),
) -> None:
    """Delete a project. Tier-3 guard: requires --yes and --confirm-name matching the project key.

    By default, backing storage of managed datasets (e.g. physical PostgreSQL
    tables for managed SQL datasets) is NOT dropped. Pass --drop-data to also
    clear them.
    """
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.CASCADE,
        action="project.delete",
        subject=f"project {project_key}"
        + (
            " (WITH --drop-data, managed tables will be destroyed)" if drop_data else ""
        ),
        yes=yes,
        target_id=project_key,
        confirm_name=confirm_name,
        prompt=(
            f"Permanently delete project '{project_key}'"
            + (
                " AND drop the backing storage of all managed datasets/folders"
                if drop_data
                else ""
            )
            + "? This cannot be undone."
        ),
    )
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
        handle_api_error(e, project_key=project_key)


@app.command()
def duplicate(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Source project key"),
    target_key: str = typer.Option(..., "--target-key", help="New project key"),
    target_name: str = typer.Option(..., "--target-name", help="New project name"),
) -> None:
    """Duplicate a project."""
    output = resolve_output_format()
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
        handle_api_error(e, project_key=project_key)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="New short description"
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update project name, description, and/or tags."""
    if name is None and description is None and tags is None:
        error("Provide --name, --description, and/or --tags to update.")
        raise typer.Exit(1)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        meta = proj.get_metadata()

        if name is not None:
            meta["label"] = name
        if description is not None:
            # DSS metadata serializes the project description under BOTH
            # 'description' (multiline) and 'shortDesc' (UI tagline) on
            # different versions; write both so the field that's actually
            # honored at PUT lands either way.
            meta["description"] = description
            meta["shortDesc"] = description
        if tags is not None:
            meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        proj.set_metadata(meta)

        # Verify the write landed: re-GET and compare. PUT
        # /projects/<key>/metadata silently drops unknown fields on some DSS
        # versions, so a success log without verification has misled agents
        # in the past (PENDING entry 2026-05-11 AYX HTML extractor).
        try:
            after = proj.get_metadata() or {}
        except Exception:
            after = None

        if after is not None:
            mismatches = []
            if name is not None and after.get("label") != name:
                mismatches.append(f"label='{after.get('label', '')}' (sent '{name}')")
            if description is not None:
                got = after.get("description") or after.get("shortDesc") or ""
                if got != description:
                    mismatches.append(f"description='{got}' (sent '{description}')")
            if tags is not None:
                sent_tags = [t.strip() for t in tags.split(",") if t.strip()]
                if (after.get("tags") or []) != sent_tags:
                    mismatches.append(
                        f"tags={after.get('tags', [])} (sent {sent_tags})"
                    )
            if mismatches:
                warn(
                    "set-metadata reported success but the server returned "
                    "different values on re-read:"
                )
                for m in mismatches:
                    warn(f"  {m}")
                warn(
                    "If this is a project description, try setting it at "
                    "creation time via 'dku project create -d \"...\"' — some "
                    "DSS versions ignore description updates on the metadata "
                    "endpoint."
                )
                raise typer.Exit(1)
        success(f"Updated metadata for {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command("get-variables")
def variables(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show project variables (pairs with set-variables)."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        vars_data = proj.get_variables()
        render_raw(vars_data, output_format=output)
    except Exception as e:
        handle_api_error(e, project_key=key)


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
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip safety guard (required with --definition)"
    ),
) -> None:
    """Set project variables. Use --set for individual standard vars or --definition to replace all."""
    key = project_key or project
    key = resolve_project(key)
    if definition is not None:
        from dku_cli.safety import Tier, guard

        guard(
            ctx,
            tier=Tier.DELETE,
            action="project.set_variables",
            subject=f"all variables on project {key} (wholesale replace)",
            yes=yes,
            prompt=f"Replace ALL variables on project {key}? Existing variables not in the new definition will be removed.",
        )
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
        handle_api_error(e, project_key=key)


@app.command()
def permissions(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show project permissions."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        perms = proj.get_permissions()
        render_raw(perms, output_format=output)
    except Exception as e:
        handle_api_error(e, project_key=key)


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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Set project permissions from JSON definition (wholesale replace)."""
    from dku_cli.safety import Tier, guard

    key = project_key or project
    key = resolve_project(key)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="project.set_permissions",
        subject=f"permissions on project {key} (wholesale replace)",
        yes=yes,
        prompt=f"Replace ALL permissions on project {key}? Users/groups not in the new definition will lose access.",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        perms = read_json_input(definition)
        proj.set_permissions(perms)
        success(f"Updated permissions for {key}")
    except Exception as e:
        handle_api_error(e, project_key=key)


@app.command()
def tags(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key (or use -P)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show project tags."""
    key = project_key or project
    key = resolve_project(key)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(key)
        meta = proj.get_metadata()
        tag_list = meta.get("tags", [])
        render_raw(tag_list, output_format=output)
    except Exception as e:
        handle_api_error(e, project_key=key)


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
) -> None:
    """Generate AI-powered description for a project.

    Requires 'Generate Metadata' enabled in DSS AI Services admin settings.

    Example:
      dku project ai-describe PROJ
      dku project ai-describe PROJ --purpose technical --save
    """
    key = project_key or project
    key = resolve_project(key)
    fmt = resolve_output_format()
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
        handle_api_error(e, project_key=key)


def _scan_text_for_column(text: str, column: str) -> bool:
    """True if `column` appears as a token in `text`. Word-boundary check
    on letters/digits/underscore — avoids matching 'price' inside 'prices'.
    """
    import re

    if not isinstance(text, str) or not text:
        return False
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(column)}(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def _walk_recipe_payload_columns(payload, column: str) -> list[str]:
    """Walk a parsed recipe payload looking for `column` references.

    Returns a list of human-readable JSON-paths where the column appeared.
    Handles the common visual recipe shapes: Group `values[]`, Prepare
    `columnsSelection.list[]` + `columnWidthsByName` keys, Window
    `partitioningColumns`/`orderingColumns`, Join `joinConditions`/
    `eqConditions`, Sort `orderingColumns`, Pivot `aggregations`/`rowKey`,
    plus a generic fallback that scans every leaf string for word-boundary
    matches.
    """
    hits: list[str] = []

    def _walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                # Dict KEY itself can be a column name (e.g. columnWidthsByName).
                if isinstance(k, str) and k == column:
                    hits.append(f"{path}.{k}")
                _walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")
        elif isinstance(node, str):
            # A bare string that exactly equals the column name OR contains
            # it as a token (formula expressions, GREL code).
            if node == column or _scan_text_for_column(node, column):
                hits.append(path or "<root>")

    _walk(payload, "")
    return hits


@app.command("find-column-refs")
def find_column_refs(
    ctx: typer.Context,
    column: str = typer.Argument(help="Column name to search for"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    types: str = typer.Option(
        "recipe,insight,scenario,dataset",
        "--types",
        "-t",
        help="Comma-separated kinds to scan: recipe, insight, scenario, dataset (chart configs).",
    ),
) -> None:
    """Find every reference to a column name across the project.

    Walks recipe payloads (Python body strings, visual recipe configs),
    insight params (chart `columnsSelection`), dataset embedded charts,
    and scenario `custom_python` step bodies. Closes the recurring "is
    this column still used?" question that previously needed 6+ ad-hoc
    Python walkers.

    Performance: O(recipes + insights + scenarios + datasets) API calls.
    Run only when you actually need the trace — for an "any consumers?"
    yes/no check, prefer `dataset usages --include-charts`.

    Example:
      dku project find-column-refs projects_count -P SOL_SAS_INVENTORY_SCORER
      dku project find-column-refs price -P PROJ -t recipe
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    kinds = {k.strip().lower() for k in types.split(",") if k.strip()}

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        rows: list[dict] = []

        if "recipe" in kinds:
            try:
                recipes = proj.list_recipes() or []
            except Exception:
                recipes = []
            for r in recipes:
                rname = r.get("name") or r.get("id")
                if not rname:
                    continue
                try:
                    recipe = proj.get_recipe(rname)
                    rs = recipe.get_settings()
                    raw_def = rs.get_recipe_raw_definition()
                except Exception:
                    continue
                # Visual payload (dict) or text payload (string).
                paths: list[str] = []
                # First try str_payload (text body for python/sql/r recipes).
                str_payload = getattr(rs, "_str_payload", None)
                if str_payload and _scan_text_for_column(str_payload, column):
                    paths.append("payload (text)")
                # Then visual payload as dict.
                try:
                    obj_payload = rs.obj_payload
                    if isinstance(obj_payload, dict):
                        paths.extend(_walk_recipe_payload_columns(obj_payload, column))
                except Exception:
                    pass
                if paths:
                    rows.append(
                        {
                            "kind": "RECIPE",
                            "id": rname,
                            "type": raw_def.get("type", "")
                            if isinstance(raw_def, dict)
                            else "",
                            "where": "; ".join(sorted(set(paths))[:5]),
                        }
                    )

        if "insight" in kinds:
            try:
                insights = proj.list_insights() or []
            except Exception:
                insights = []
            for i in insights:
                iid = i.get("id", "")
                if not iid:
                    continue
                try:
                    raw = proj.get_insight(iid).get_settings().get_raw()
                except Exception:
                    continue
                paths = _walk_recipe_payload_columns(raw, column)
                if paths:
                    rows.append(
                        {
                            "kind": "INSIGHT",
                            "id": iid,
                            "type": raw.get("type", ""),
                            "where": "; ".join(sorted(set(paths))[:5]),
                        }
                    )

        if "scenario" in kinds:
            try:
                scenarios = proj.list_scenarios() or []
            except Exception:
                scenarios = []
            for s in scenarios:
                sid = s.get("id", "")
                if not sid:
                    continue
                try:
                    sraw = proj.get_scenario(sid).get_settings().get_raw()
                except Exception:
                    continue
                paths = _walk_recipe_payload_columns(sraw, column)
                if paths:
                    rows.append(
                        {
                            "kind": "SCENARIO",
                            "id": sid,
                            "type": sraw.get("type", ""),
                            "where": "; ".join(sorted(set(paths))[:5]),
                        }
                    )

        if "dataset" in kinds:
            try:
                datasets = proj.list_datasets() or []
            except Exception:
                datasets = []
            for d in datasets:
                dname = d.get("name") or d.get("id")
                if not dname:
                    continue
                try:
                    raw = proj.get_dataset(dname).get_definition()
                except Exception:
                    continue
                # Embedded chart configs only — skip schema (we look for
                # USES of the column, not its definition).
                charts = raw.get("charts") if isinstance(raw, dict) else None
                if not charts:
                    continue
                paths = _walk_recipe_payload_columns({"charts": charts}, column)
                if paths:
                    rows.append(
                        {
                            "kind": "DATASET_CHART",
                            "id": dname,
                            "type": raw.get("type", ""),
                            "where": "; ".join(sorted(set(paths))[:5]),
                        }
                    )

        if fmt == "json":
            render_raw(rows, output_format="json")
            return

        if not rows:
            info(f"No references to column '{column}' found in {project_key}.")
            return
        render(
            rows,
            ["kind", "id", "type", "where"],
            output_format=fmt,
            title=f"References to '{column}' in {project_key}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def timeline(
    ctx: typer.Context,
    project_key: str = typer.Argument(None, help="Project key"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    limit: int = typer.Option(20, "--limit", help="Max number of timeline items"),
) -> None:
    """Show project timeline: creation, contributors, recent modifications.

    Example:
      dku project timeline PROJ
      dku project timeline PROJ --limit 50
    """
    key = project_key or project
    key = resolve_project(key)
    fmt = resolve_output_format()
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
        handle_api_error(e, project_key=key)
