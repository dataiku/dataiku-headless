"""dku library — list, read, write, delete, mkdir."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, resolve_output_format, success

app = typer.Typer(help="Manage DSS project library files.")


def _get_or_create_folder(lib, folder_path: str):
    """Navigate to a folder, creating intermediate dirs as needed."""
    parts = PurePosixPath(folder_path).parts
    current = lib
    for part in parts:
        try:
            current = current.get_folder(part)
        except Exception:
            current = current.add_folder(part)
    return current


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

        if path == "/":
            contents = lib.list()
        else:
            folder = lib.get_folder(path)
            contents = folder.list()

        data = []
        for item in contents:
            data.append({
                "path": item.path,
            })

        render(
            data,
            ["path"],
            output_format=output,
            title=f"Library ({project_key})",
            headers={"path": "PATH"},
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
        f = lib.get_file(path)
        content = f.read(as_type="bytes")

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

        p = PurePosixPath(path)
        parent = str(p.parent)
        filename = p.name

        try:
            # Try updating existing file
            f = lib.get_file(path)
        except Exception:
            # File doesn't exist — create it in the appropriate folder
            if parent and parent != ".":
                folder = _get_or_create_folder(lib, parent)
                f = folder.add_file(filename)
            else:
                f = lib.add_file(filename)

        f.write(content_bytes)
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
        f = lib.get_file(path)
        f.delete()

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
        _get_or_create_folder(lib, path)

        success(f"Created directory {path}")
    except Exception as e:
        handle_api_error(e)
