"""dku library — list, read, write, delete, mkdir."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, resolve_output_format, success

app = typer.Typer(help="Manage DSS project library files.")


@app.command("list")
def list_files(
    ctx: typer.Context,
    path: str = typer.Option("/", "--path", help="Directory path to list"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List files in the project library."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        contents = lib.list_contents(path)

        data = []
        for item in contents:
            data.append({
                "path": item.get("path", ""),
                "size": item.get("size", ""),
            })

        render(
            data,
            ["path", "size"],
            output_format=output,
            title=f"Library ({project_key})",
            headers={"path": "PATH", "size": "SIZE"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def read(
    ctx: typer.Context,
    path: str = typer.Argument(help="File path in the library"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Read a file from the project library (prints to stdout)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        content = lib.get_file(path)

        # Write raw bytes to stdout for clean piping
        sys.stdout.buffer.write(content)
    except Exception as e:
        handle_api_error(e)


@app.command()
def write(
    ctx: typer.Context,
    path: str = typer.Argument(help="File path in the library"),
    content: str = typer.Option(..., "--content", "-c", help="Content: literal string, @file.py to read from file, or - for stdin"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Write a file to the project library."""
    project_key = resolve_project(project)

    # Resolve content source
    if content == "-":
        content_bytes = sys.stdin.buffer.read()
    elif content.startswith("@"):
        local_path = Path(content[1:])
        if not local_path.exists():
            from dku_cli.output import error

            error(f"File not found: {local_path}")
            raise typer.Exit(1)
        content_bytes = local_path.read_bytes()
    else:
        content_bytes = content.encode("utf-8")

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        lib.put_file(path, content_bytes)

        success(f"Wrote {len(content_bytes)} bytes to {path}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    path: str = typer.Argument(help="File path in the library"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a file from the project library."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        lib.delete_file(path)

        success(f"Deleted {path}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def mkdir(
    ctx: typer.Context,
    path: str = typer.Argument(help="Directory path to create"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a directory in the project library."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        lib.add_folder(path)

        success(f"Created directory {path}")
    except Exception as e:
        handle_api_error(e)
