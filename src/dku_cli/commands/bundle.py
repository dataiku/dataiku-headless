"""dku bundle — list, export, download, import, activate."""

from __future__ import annotations

from pathlib import Path

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import error, render, resolve_output_format, success

app = typer.Typer(help="Manage DSS project bundles.")


@app.command("list")
def list_bundles(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List exported bundles for a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        bundles_raw = proj.list_exported_bundles()

        # dataikuapi may return a dict {"bundles": [...]} or a list directly
        if isinstance(bundles_raw, dict) and "bundles" in bundles_raw:
            bundles = bundles_raw["bundles"]
        elif isinstance(bundles_raw, list):
            bundles = bundles_raw
        else:
            bundles = list(bundles_raw) if bundles_raw else []

        data = []
        for b in bundles:
            if isinstance(b, dict):
                bid = b.get("id", b.get("bundleId", b.get("name", str(b))))
            elif hasattr(b, "id"):
                bid = b.id
            elif hasattr(b, "bundleId"):
                bid = b.bundleId
            else:
                bid = str(b)
            data.append({"id": bid})

        render(
            data,
            ["id"],
            output_format=output,
            title=f"Bundles ({project_key})",
            headers={"id": "ID"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command("export")
def export_bundle(
    ctx: typer.Context,
    bundle_id: str = typer.Argument(help="Bundle ID to export"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Export (create) a bundle snapshot."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.export_bundle(bundle_id)
        success(f"Exported bundle '{bundle_id}' in project {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("download")
def download_bundle(
    ctx: typer.Context,
    bundle_id: str = typer.Argument(help="Bundle ID to download"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    dest: Path = typer.Option(".", "--dest", "-d", help="Destination directory"),
) -> None:
    """Download an exported bundle archive to a local file."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{project_key}-{bundle_id}.zip"

        proj.download_exported_bundle_archive_to_file(bundle_id, str(out_path))
        success(f"Downloaded bundle '{bundle_id}' to {out_path}")
    except Exception as e:
        handle_api_error(e)


@app.command("import")
def import_bundle(
    ctx: typer.Context,
    archive_path: Path = typer.Argument(help="Path to bundle archive (ZIP)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Import a bundle archive into a project."""
    project_key = resolve_project(project)

    if not archive_path.exists():
        error(f"File not found: {archive_path}")
        raise typer.Exit(1)

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        with archive_path.open("rb") as f:
            proj.import_bundle_from_archive(f)

        success(f"Imported bundle from {archive_path.name} into {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("activate")
def activate_bundle(
    ctx: typer.Context,
    bundle_id: str = typer.Argument(help="Bundle ID to activate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Activate (preload and apply) a bundle on a project."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        proj.preload_bundle(bundle_id)
        proj.activate_bundle(bundle_id)

        success(f"Activated bundle '{bundle_id}' in project {project_key}")
    except Exception as e:
        handle_api_error(e)
