"""dku app-designer — manage app manifest: tiles, homepage, definition."""

from __future__ import annotations

import io
import json
import zipfile

import typer

from dku_cli.commands._app_designer_tiles import _tile_target
from dku_cli.enums import AppEnableMode
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    object_write_lock,
    read_json_input,
    read_text_input,
    resolve_project,
)
from dku_cli.output import render, render_raw, resolve_output_format, success, warn

_REGULAR_MANIFEST_ERROR = "neither an app template nor an app instance"


def _is_regular_manifest_error(exc: Exception) -> bool:
    """True when DSS rejects a manifest read because the project is REGULAR.

    Server raises `IllegalArgumentException: Project ... is neither an app
    template nor an app instance` for `proj.get_app_manifest()` and
    `_perform_json("GET", "/projects/X/app-manifest")` on REGULAR projects,
    even when manifest data exists server-side (PUT works regardless).
    """
    return _REGULAR_MANIFEST_ERROR in str(exc)


def _read_manifest_via_export(client, project_key: str) -> dict:
    """Read the app manifest of a REGULAR project via /export ZIP.

    Falls back to this path when `proj.get_app_manifest()` raises because
    the project is REGULAR. Loads the project archive into memory, opens
    `project_config/app-manifest.json`, returns the parsed dict (empty
    dict if the file is missing — meaning the project never had setup
    data).
    """
    response = client._perform_raw("POST", f"/projects/{project_key}/export", body={})
    raw_bytes = b"".join(
        chunk for chunk in response.iter_content(chunk_size=32768) if chunk
    )
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        try:
            with zf.open("project_config/app-manifest.json") as fh:
                return json.loads(fh.read().decode("utf-8"))
        except KeyError:
            return {}


def _read_manifest(client, project_key: str) -> dict:
    """Read the project's app manifest, with REGULAR-project fallback.

    Returns the raw manifest dict. Tries `proj.get_app_manifest()` first
    (the canonical SDK path). On REGULAR-project rejection, falls back
    to the project export ZIP.
    """
    proj = client.get_project(project_key)
    try:
        manifest = proj.get_app_manifest()
        return manifest.get_raw()
    except Exception as exc:
        if _is_regular_manifest_error(exc):
            return _read_manifest_via_export(client, project_key)
        raise


def _write_manifest(client, project_key: str, raw: dict) -> None:
    """Write the project's app manifest, with REGULAR-project fallback.

    Tries `manifest.save()` first (works for APP_TEMPLATE / APP_INSTANCE).
    If that fails because the project is REGULAR, transparently routes
    through APP_TEMPLATE: temporarily promotes the project, writes via
    the SDK, then restores the original `projectAppType`. The round-trip
    preserves the caller's surface so setup-mode (REGULAR) callers keep
    their project type unchanged.
    """
    proj = client.get_project(project_key)
    try:
        manifest = proj.get_app_manifest()
        manifest.raw_data = raw
        manifest.save()
        return
    except Exception as exc:
        if not _is_regular_manifest_error(exc):
            raise

    # REGULAR-project path: round-trip through APP_TEMPLATE
    settings = proj.get_settings()
    original_settings_raw = settings.get_raw()
    original_type = original_settings_raw.get("projectAppType", "REGULAR")

    original_settings_raw["projectAppType"] = "APP_TEMPLATE"
    settings.save()

    try:
        manifest = proj.get_app_manifest()
        manifest.raw_data = raw
        manifest.save()
    finally:
        # Always restore the original projectAppType, even on failure,
        # so a partial error does not leave the project converted.
        settings = proj.get_settings()
        rollback_raw = settings.get_raw()
        if rollback_raw.get("projectAppType") != original_type:
            rollback_raw["projectAppType"] = original_type
            settings.save()


def _handle_app_error(e: Exception, project_key: str) -> None:
    """Wrap handle_api_error with app-designer-specific guidance."""
    if _is_regular_manifest_error(e):
        exit_with_error(
            f"Project {project_key} is REGULAR — cannot read its app manifest "
            "via the SDK helper.",
            details=[
                "REGULAR projects can hold a Project Setup manifest (useAppHomepage=True).",
                "Use `dku app-designer get -P "
                f"{project_key}` to read via the export-ZIP fallback,",
                "or convert to an App Template first: "
                f"`dku app-designer enable -P {project_key} --mode template`.",
            ],
        )
    handle_api_error(e)


app = typer.Typer(help="Manage App Designer manifest and tiles.")


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


@app.command()
def get(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the full app manifest.

    Works for both APP_TEMPLATE / APP_INSTANCE projects (canonical SDK path)
    and REGULAR projects with `useAppHomepage=True` Project Setup data
    (export-ZIP fallback). Empty dict means the project has no manifest.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        raw = _read_manifest(client, project_key)
        render_raw(raw, output_format=output)
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    confirm_name: str | None = typer.Option(
        None,
        "--confirm-name",
        help="Must match the project key when wiping all homepage sections.",
    ),
) -> None:
    """Set/replace the full app manifest from JSON.

    Safety: if the current manifest has homepage sections and the new
    payload would result in zero (or omits the key), the write is gated
    behind tier-3 CASCADE — pass `--yes --confirm-name <PROJECT_KEY>` to
    proceed. Prevents the `PUT {}` foot-gun that silently wipes a
    Project Setup's section list.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    new_def = read_json_input(definition)
    if not isinstance(new_def, dict):
        exit_with_error("--definition must be a JSON object (the manifest dict).")
    try:
        client = get_client_from_ctx(ctx)
        with object_write_lock(client, project_key, "project", project_key):
            try:
                current = _read_manifest(client, project_key)
            except Exception:
                # Couldn't read current state — be conservative, fall through
                # to write anyway. The agent should know what it's doing.
                current = {}

            current_sections = current.get("homepageSections") or []
            new_sections = new_def.get("homepageSections")
            if current_sections and (new_sections is None or len(new_sections) == 0):
                guard(
                    ctx,
                    tier=Tier.CASCADE,
                    action="app_designer.wipe_sections",
                    subject=(
                        f"app manifest for project '{project_key}' "
                        f"(replaces {len(current_sections)} homepageSection(s) with 0)"
                    ),
                    yes=yes,
                    target_id=project_key,
                    confirm_name=confirm_name,
                    prompt=(
                        f"Replace project '{project_key}' app manifest? "
                        f"This wipes all {len(current_sections)} homepage section(s)."
                    ),
                )

            _write_manifest(client, project_key, new_def)
        success(f"Updated app manifest for project {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        _handle_app_error(e, project_key)


@app.command("list-tiles")
def list_tiles(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List all tiles across all sections."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        raw = _read_manifest(client, project_key)

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
        with object_write_lock(client, project_key, "project", project_key):
            raw = _read_manifest(client, project_key)
            sections = raw.setdefault("homepageSections", [])

            # Ensure target section exists
            while len(sections) <= section:
                sections.append({"tiles": []})

            sections[section].setdefault("tiles", []).append(tile)
            _write_manifest(client, project_key, raw)
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a tile by section and tile index."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="app_designer.remove_tile",
        subject=f"tile at section {section}, index {index} in {project_key}",
        yes=yes,
        prompt=f"Remove tile at section {section}, index {index}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        with object_write_lock(client, project_key, "project", project_key):
            raw = _read_manifest(client, project_key)
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
            _write_manifest(client, project_key, raw)
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
    mode: AppEnableMode = typer.Option(
        AppEnableMode.template,
        "--mode",
        "-m",
        case_sensitive=False,
        help=(
            "What to enable: 'template' (default — converts the project "
            "to APP_TEMPLATE so it can be instantiated as a Dataiku App). "
            "'setup' is rejected — Project Setup mode requires an internal "
            "endpoint not exposed in the public API; see the error message "
            "for the manual UI step."
        ),
    ),
) -> None:
    """Enable the app homepage on a project (APP_TEMPLATE mode).

    Sets `projectAppType=APP_TEMPLATE` AND `useAppHomepage=True`.
    Reversible by opening the App Designer UI and clicking
    `Actions → Convert back to regular project` (POSTs
    `/dip/api/projects/switch-app-type` with `appType=REGULAR`).

    \b
    Project Setup mode (the lighter alternative for one-off templates
    configured before use) is NOT settable via this CLI. The discriminator
    `hasSetupSection` is written by `POST /dip/api/projects/set-setup-section`,
    which lives in the internal `/dip/api/` namespace; that namespace
    rejects API-key auth (HTTP 401) and `dataikuapi` only targets
    `/dip/publicapi/`. Setting `useAppHomepage=true` in the manifest alone
    is necessary-but-not-sufficient — the UI keys on `hasSetupSection`.
    Open the App Designer in a browser and click
    `Show advanced options → Add a setup section to this project` instead.
    """
    project_key = resolve_project(project)
    mode_normalised = mode.value

    if mode_normalised == "setup":
        # Drop the lie — manifest PUT alone leaves the UI in landing-page state.
        # Tell the agent exactly what to do instead.
        try:
            client = get_client_from_ctx(ctx)
            host = client.host.rstrip("/")
        except Exception:
            host = "<DSS-URL>"
        exit_with_error(
            "--mode setup is not implementable via the public API.",
            details=[
                "Project Setup mode is gated by a project-level boolean",
                "`hasSetupSection` (visible in `params.json`) that ONLY the",
                "internal endpoint `/dip/api/projects/set-setup-section`",
                "writes. That endpoint rejects API-key auth (401) and is",
                "not mirrored in `/dip/publicapi/` — so `dku` cannot reach",
                "it. Setting `useAppHomepage=True` alone leaves the App",
                "Designer UI on the 'Convert this project…' landing page.",
                "",
                "Two paths forward:",
                f"  1. Manual UI step — open {host}/projects/{project_key}/app-designer/",
                "     then click `Show advanced options → Add a setup section",
                "     to this project`.",
                "  2. Use APP_TEMPLATE mode instead:",
                f"     dku app-designer enable -P {project_key} --mode template",
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        with object_write_lock(client, project_key, "project", project_key):
            settings = proj.get_settings()
            raw_settings = settings.get_raw()
            if raw_settings.get("projectAppType") != "APP_TEMPLATE":
                raw_settings["projectAppType"] = "APP_TEMPLATE"
                settings.save()
                warn(
                    f"Project {project_key} converted to APP_TEMPLATE — "
                    "no longer a REGULAR project."
                )

            raw = _read_manifest(client, project_key)
            raw["useAppHomepage"] = True
            if label:
                raw["label"] = label
            if description:
                raw["shortDesc"] = description
            _write_manifest(client, project_key, raw)

        success(f"App template enabled for {project_key} (projectAppType=APP_TEMPLATE)")
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
        with object_write_lock(client, project_key, "project", project_key):
            raw = _read_manifest(client, project_key)
            raw["useAppHomepage"] = False
            _write_manifest(client, project_key, raw)
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
        with object_write_lock(client, project_key, "project", project_key):
            raw = _read_manifest(client, project_key)
            sections = raw.setdefault("homepageSections", [])

            # Ensure target section exists
            while len(sections) <= section:
                sections.append({"tiles": []})

            if title is not None:
                sections[section]["sectionTitle"] = title
            if text is not None:
                sections[section]["sectionText"] = text
            _write_manifest(client, project_key, raw)
        success(f"Updated section {section} in project {project_key}")
    except Exception as e:
        _handle_app_error(e, project_key)
