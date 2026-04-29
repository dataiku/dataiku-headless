"""dku govern file — upload, get, download."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render_raw, resolve_output_format, success

app = typer.Typer(help="Manage Govern uploaded files.")


@app.command()
def upload(
    ctx: typer.Context,
    file_path: str = typer.Argument(help="Path to the file to upload"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Upload a file to Govern."""
    import os

    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            uploaded = govern.upload_file(file_name, f)
        success(f"Uploaded file '{file_name}' (id: {uploaded.uploaded_file_id})")
        desc = uploaded.get_description()
        render_raw(desc, output_format=output)
    except SystemExit:
        raise
    except FileNotFoundError:
        from dku_cli.errors import exit_with_error

        exit_with_error(
            f"File not found: {file_path}",
            code="file_not_found",
            details=[f"Check the path and try again: {file_path}"],
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    file_id: str = typer.Argument(help="Uploaded file ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get metadata for an uploaded file."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        uploaded = govern.get_uploaded_file(file_id)
        desc = uploaded.get_description()
        render_raw(desc, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def download(
    ctx: typer.Context,
    file_id: str = typer.Argument(help="Uploaded file ID (e.g. uf.1)"),
    dest: Optional[str] = typer.Option(
        None,
        "--dest",
        "-d",
        help="Destination path (default: original filename in current dir)",
    ),
) -> None:
    """Download an uploaded file from Govern."""
    import shutil

    try:
        govern = get_govern_client_from_ctx(ctx)
        uploaded = govern.get_uploaded_file(file_id)
        desc = uploaded.get_description()
        file_name = desc.get("name", file_id)
        out_path = dest or file_name

        stream = uploaded.download()
        with open(out_path, "wb") as f:
            shutil.copyfileobj(stream, f)
        success(f"Downloaded '{file_name}' to '{out_path}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
