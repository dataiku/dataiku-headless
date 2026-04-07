"""dku app-designer — manage app manifest: tiles, homepage, definition."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    read_text_input,
    resolve_project,
)
from dku_cli.output import render, render_raw, resolve_output_format, success


def _handle_app_error(e: Exception, project_key: str) -> None:
    """Wrap handle_api_error with app-designer-specific guidance."""
    msg = str(e)
    if "neither an app template nor an app instance" in msg:
        exit_with_error(
            f"Project {project_key} is not an app template",
            details=[
                f'Enable it first: dku app-designer enable -P {project_key} --label "My App"',
                "Then retry the command.",
            ],
        )
    handle_api_error(e)


app = typer.Typer(help="Manage App Designer manifest and tiles.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tile_target(tile: dict) -> str:
    """Extract a human-readable target reference from a tile."""
    # Dataset/folder/dashboard binding (applies to many tile types)
    ds = tile.get("datasetName", "")
    fid = tile.get("folderId", "")
    did = tile.get("dashboardId", "")

    t = tile.get("type", "")
    if t == "SCENARIO_RUN":
        return tile.get("scenarioId", "")
    if t == "PROJECT_VARIABLES_EDIT":
        n = len(tile.get("params", []))
        return f"{n} param(s)"
    if t == "INLINE_PYTHON_RUN":
        return "(code)"
    if ds:
        return ds
    if did:
        return did
    if fid:
        return fid
    return ""


def _build_tile(
    tile_type: str,
    scenario: str | None,
    prompt: str | None,
    params_json: str | None,
    behavior: str | None,
    code: str | None,
    button_text: str | None,
    dataset: str | None,
    dashboard: str | None,
    folder: str | None,
    help_text: str | None,
) -> dict:
    """Construct a tile dict from CLI shortcut flags."""
    tile: dict = {"type": tile_type}

    if prompt:
        tile["prompt"] = prompt
    if help_text:
        tile["help"] = help_text

    if tile_type == "SCENARIO_RUN":
        if not scenario:
            exit_with_error(
                "SCENARIO_RUN requires --scenario",
                details=["Provide the scenario ID: --scenario BUILD_ALL"],
            )
        tile["scenarioId"] = scenario
        if button_text:
            tile["buttonText"] = button_text

    elif tile_type == "PROJECT_VARIABLES_EDIT":
        if params_json:
            try:
                tile["params"] = json.loads(params_json)
            except json.JSONDecodeError as exc:
                exit_with_error(f"Invalid JSON for --params: {exc}")
        if behavior:
            tile["behavior"] = behavior

    elif tile_type == "INLINE_PYTHON_RUN":
        if code:
            tile["code"] = read_text_input(code)
        if button_text:
            tile["buttonText"] = button_text

    # Dataset/dashboard/folder binding (applies to many tile types)
    if dataset:
        tile["datasetName"] = dataset
    if dashboard:
        tile["dashboardId"] = dashboard
    if folder:
        tile["folderId"] = folder

    # Apply behavior for types that didn't already set it
    if behavior and "behavior" not in tile:
        tile["behavior"] = behavior

    return tile


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def get(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the full app manifest."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        render_raw(manifest.get_raw(), output_format=output)
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="JSON definition (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Set/replace the full app manifest from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        new_def = read_json_input(definition)
        manifest = proj.get_app_manifest()
        manifest.raw_data = new_def
        manifest.save()
        success(f"Updated app manifest for project {project_key}")
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command("list-tiles")
def list_tiles(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all tiles across all sections."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        raw = manifest.get_raw()

        rows = []
        for si, section in enumerate(raw.get("homepageSections", [])):
            title = section.get("sectionTitle", "")
            for ti, tile in enumerate(section.get("tiles", [])):
                rows.append(
                    {
                        "section": str(si),
                        "section_title": title,
                        "index": str(ti),
                        "type": tile.get("type", ""),
                        "prompt": tile.get("prompt", tile.get("buttonText", "")),
                        "target": _tile_target(tile),
                    }
                )
            # Show empty sections (header-only sections with title but no tiles)
            if not section.get("tiles") and title:
                rows.append(
                    {
                        "section": str(si),
                        "section_title": title,
                        "index": "",
                        "type": "(header)",
                        "prompt": "",
                        "target": "",
                    }
                )

        render(
            rows,
            ["section", "section_title", "index", "type", "prompt", "target"],
            output_format=output,
            title=f"App Tiles ({project_key})",
        )
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command("add-tile")
def add_tile(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    tile_type: str | None = typer.Option(
        None, "--type", "-t", help="Tile type (e.g. SCENARIO_RUN, DASHBOARD_LINK)"
    ),
    scenario: str | None = typer.Option(
        None, "--scenario", help="Scenario ID (for SCENARIO_RUN)"
    ),
    prompt: str | None = typer.Option(None, "--prompt", help="Tile prompt/label"),
    params: str | None = typer.Option(
        None,
        "--params",
        help="JSON array of variable params (for PROJECT_VARIABLES_EDIT)",
    ),
    behavior: str | None = typer.Option(
        None, "--behavior", help="Tile behavior (e.g. MODAL, INLINE_AUTO_SAVE)"
    ),
    code: str | None = typer.Option(
        None,
        "--code",
        help="Python code (for INLINE_PYTHON_RUN, supports @file.py or -)",
    ),
    button_text: str | None = typer.Option(
        None, "--button-text", help="Button text (for SCENARIO_RUN, INLINE_PYTHON_RUN)"
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Bind to dataset (for INLINE_DATASET_EDIT, UPLOAD_DATASET_SET_FILE, DOWNLOAD_DATASET)",
    ),
    dashboard: str | None = typer.Option(
        None, "--dashboard", help="Bind to dashboard ID (for DASHBOARD_LINK)"
    ),
    folder: str | None = typer.Option(
        None,
        "--folder",
        help="Bind to folder ID (for MANAGED_FOLDER_BROWSE, MANAGED_FOLDER_ADD_FILE)",
    ),
    help_text: str | None = typer.Option(
        None, "--help-text", help="Help text shown on the tile"
    ),
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="Full tile JSON (overrides shortcuts)"
    ),
    section: int = typer.Option(
        0, "--section", "-s", help="Target section index (default: 0)"
    ),
) -> None:
    """Add a tile to the app homepage.

    Use type-specific flags for common tiles, or --definition for full control.
    """
    project_key = resolve_project(project)
    try:
        if definition:
            tile = read_json_input(definition)
        else:
            if not tile_type:
                exit_with_error(
                    "Must provide --type or --definition",
                    details=[
                        "Example: dku app-designer add-tile --type SCENARIO_RUN --scenario BUILD -P PROJ",
                        "Example: dku app-designer add-tile --definition @tile.json -P PROJ",
                    ],
                )
            tile = _build_tile(
                tile_type,
                scenario,
                prompt,
                params,
                behavior,
                code,
                button_text,
                dataset,
                dashboard,
                folder,
                help_text,
            )

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        raw = manifest.get_raw()
        sections = raw.setdefault("homepageSections", [])

        # Ensure target section exists
        while len(sections) <= section:
            sections.append({"tiles": []})

        sections[section].setdefault("tiles", []).append(tile)
        manifest.save()
        tile_idx = len(sections[section]["tiles"]) - 1
        success(
            f"Added {tile.get('type', 'unknown')} tile at section {section}, index {tile_idx}"
        )
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command("remove-tile")
def remove_tile(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    section: int = typer.Option(0, "--section", "-s", help="Section index"),
    index: int = typer.Option(
        ..., "--index", "-i", help="Tile index within section (from list-tiles)"
    ),
) -> None:
    """Remove a tile by section and tile index."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        raw = manifest.get_raw()
        sections = raw.get("homepageSections", [])

        if section < 0 or section >= len(sections):
            exit_with_error(
                f"Section {section} out of range (0-{len(sections) - 1})",
                details=[f"Use: dku app-designer list-tiles -P {project_key}"],
            )

        tiles = sections[section].get("tiles", [])
        if index < 0 or index >= len(tiles):
            exit_with_error(
                f"Tile index {index} out of range (0-{len(tiles) - 1})",
                details=[f"Use: dku app-designer list-tiles -P {project_key}"],
            )

        removed = tiles.pop(index)
        manifest.save()
        success(
            f"Removed {removed.get('type', 'unknown')} tile at section {section}, index {index}"
        )
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command()
def enable(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    label: str | None = typer.Option(None, "--label", "-l", help="App label"),
    description: str | None = typer.Option(
        None, "--description", help="App short description"
    ),
) -> None:
    """Enable the app homepage (set useAppHomepage=true)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        raw = manifest.get_raw()
        raw["useAppHomepage"] = True
        if label:
            raw["label"] = label
        if description:
            raw["shortDesc"] = description
        manifest.save()
        success(f"App homepage enabled for project {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def disable(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Disable the app homepage (set useAppHomepage=false)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        raw = manifest.get_raw()
        raw["useAppHomepage"] = False
        manifest.save()
        success(f"App homepage disabled for project {project_key}")
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command("set-section")
def set_section(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    section: int = typer.Option(
        ..., "--section", "-s", help="Section index (created if it does not exist)"
    ),
    title: str | None = typer.Option(None, "--title", help="Section title"),
    text: str | None = typer.Option(
        None, "--text", help="Section description (supports HTML)"
    ),
) -> None:
    """Set section title and/or description text."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        manifest = proj.get_app_manifest()
        raw = manifest.get_raw()
        sections = raw.setdefault("homepageSections", [])

        # Ensure target section exists
        while len(sections) <= section:
            sections.append({"tiles": []})

        if title is not None:
            sections[section]["sectionTitle"] = title
        if text is not None:
            sections[section]["sectionText"] = text
        manifest.save()
        success(f"Updated section {section} in project {project_key}")
    except Exception as e:
        _handle_app_error(e, project_key)
