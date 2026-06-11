"""dku project-folder — list, create, move-project for project folder management."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import hint, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS project folders.")


def _collect_tree(folder, depth=0):
    """Recursively collect folder tree into flat list."""
    result = [
        {
            "id": folder.id,
            "name": folder.name or "(root)",
            "depth": depth,
            "projects": ", ".join(folder.list_project_keys()),
        }
    ]
    for child in folder.list_child_folders():
        result.extend(_collect_tree(child, depth + 1))
    return result


@app.command("list")
def list_folders(
    ctx: typer.Context,
) -> None:
    """List all project folders (recursive tree from root).

    Example:
      dku project-folder list
      dku project-folder list
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        root = client.get_root_project_folder()

        if fmt == "json":
            tree = _collect_tree(root)
            render_raw(tree, output_format="json")
        else:
            tree = _collect_tree(root)
            # Indent names by depth for visual hierarchy
            for item in tree:
                item["name"] = "  " * item["depth"] + item["name"]
            render(
                tree,
                ["name", "id", "projects"],
                output_format=fmt,
                title="Project Folders",
                headers={"name": "NAME", "id": "ID", "projects": "PROJECTS"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Folder name"),
    parent: str = typer.Option(
        "ROOT", "--parent", help="Parent folder ID (default: ROOT)"
    ),
) -> None:
    """Create a project subfolder.

    Example:
      dku project-folder create "Analytics"
      dku project-folder create "ML Models" --parent PARENT_FOLDER_ID
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        parent_folder = client.get_project_folder(parent)
        new_folder = parent_folder.create_sub_folder(name)

        if fmt == "json":
            render_raw(
                {"id": new_folder.id, "name": name, "parent": parent},
                output_format="json",
            )
        else:
            success(f"Created project folder '{name}' (ID: {new_folder.id})")
            hint("dku project-folder list")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("move-project")
def move_project(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key to move"),
    folder_id: str = typer.Option(..., "--folder", "-f", help="Target folder ID"),
) -> None:
    """Move a project to a different folder.

    Example:
      dku project-folder move-project MYPROJ --folder FOLDER_ID
    """
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dest = client.get_project_folder(folder_id)
        proj.move_to_folder(dest)
        success(f"Moved project '{project_key}' to folder '{folder_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
