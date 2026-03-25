"""dku folder — list, ls, upload, download."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, resolve_output_format, success

app = typer.Typer(help="Manage DSS managed folders.")


@app.command("list")
def list_folders(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List managed folders in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        # dataikuapi quirk: returns dicts with 'id' key
        folders = proj.list_managed_folders()

        data = []
        for f in folders:
            data.append(
                {
                    "id": f.get("id", ""),
                    "name": f.get("name", ""),
                    "type": f.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Managed Folders ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def ls(
    ctx: typer.Context,
    folder_id: str = typer.Argument(help="Managed folder ID"),
    prefix: str = typer.Option("/", "--prefix", help="Path prefix to list"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List contents of a managed folder."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = proj.get_managed_folder(folder_id)
        contents = folder.list_contents()

        items = contents.get("items", [])
        data = []
        for item in items:
            path = item.get("path", "")
            if not path.startswith(prefix):
                continue
            ts = item.get("lastModified", 0)
            if ts:
                modified = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M"
                )
            else:
                modified = ""
            size_bytes = item.get("size", 0)
            if size_bytes >= 1_048_576:
                size_str = f"{size_bytes / 1_048_576:.1f} MB"
            elif size_bytes >= 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} B"
            data.append(
                {
                    "path": path,
                    "size": size_str,
                    "last_modified": modified,
                }
            )

        render(
            data,
            ["path", "size", "last_modified"],
            output_format=output,
            title=f"Folder: {folder_id}",
            headers={"path": "PATH", "size": "SIZE", "last_modified": "MODIFIED"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def upload(
    ctx: typer.Context,
    folder_id: str = typer.Argument(help="Managed folder ID"),
    local_path: Path = typer.Argument(help="Local file to upload"),
    remote_path: str = typer.Option(
        None, "--path", help="Remote path (defaults to filename)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Upload a file to a managed folder."""
    project_key = resolve_project(project)

    if not local_path.exists():
        from dku_cli.output import error

        error(f"File not found: {local_path}")
        raise typer.Exit(1)

    target = remote_path or f"/{local_path.name}"
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = proj.get_managed_folder(folder_id)

        with local_path.open("rb") as f:
            folder.put_file(target, f)

        success(f"Uploaded {local_path.name} → {target}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def download(
    ctx: typer.Context,
    folder_id: str = typer.Argument(help="Managed folder ID"),
    remote_path: str = typer.Argument(help="Remote file path"),
    dest: Path = typer.Option(".", "--dest", "-d", help="Local destination directory"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Download a file from a managed folder."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = proj.get_managed_folder(folder_id)

        stream = folder.get_file(remote_path)

        dest.mkdir(parents=True, exist_ok=True)
        filename = Path(remote_path).name
        out_path = dest / filename

        with out_path.open("wb") as f:
            for chunk in stream.iter_content(chunk_size=8192):
                f.write(chunk)

        success(f"Downloaded {remote_path} → {out_path}")
    except Exception as e:
        handle_api_error(e)
