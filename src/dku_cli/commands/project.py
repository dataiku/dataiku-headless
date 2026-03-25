"""dku project — list, get, export, create, delete, duplicate, variables, permissions, tags."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
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
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if project already exists"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new project."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        owner = client.get_auth_info()["authIdentifier"]
        client.create_project(project_key, name, owner, description=description)

        data = [
            {"field": "Key", "value": project_key},
            {"field": "Name", "value": name},
            {"field": "Owner", "value": owner},
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
) -> None:
    """Delete a project. Requires --confirm / --yes flag."""
    if not confirm:
        error(
            "Deletion requires --confirm (or --yes / -y) flag. This action is irreversible."
        )
        raise typer.Exit(1)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.delete()
        success(f"Deleted project {project_key}")
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
        proj.duplicate(
            target_project_key=target_key, target_project_name=target_name
        )

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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project variables."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        vars_data = proj.get_variables()
        render_raw(vars_data, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-variables")
def set_variables(
    ctx: typer.Context,
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
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        if definition is not None:
            new_vars = read_json_input(definition)
            proj.set_variables(new_vars)
            success(f"Replaced variables for {project_key}")
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
            success(f"Updated standard variables for {project_key}")
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
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project permissions."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        perms = proj.get_permissions()
        render_raw(perms, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-permissions")
def set_permissions(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Permissions JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Set project permissions from JSON definition."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        perms = read_json_input(definition)
        proj.set_permissions(perms)
        success(f"Updated permissions for {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def tags(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show project tags."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        meta = proj.get_metadata()
        tag_list = meta.get("tags", [])
        render_raw(tag_list, output_format=output)
    except Exception as e:
        handle_api_error(e)
