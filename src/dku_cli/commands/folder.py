"""dku folder — managed folder file operations.

Commands: create, delete, get, list, ls, upload, upload-dir, download,
delete-file, delete-files, create-dataset, set-metadata, rename, copy,
decompress.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, resolve_folder, resolve_project
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS managed folders.")


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the new managed folder"),
    connection: str = typer.Option(
        "filesystem_folders",
        "--connection",
        "-c",
        help="Connection name (default: filesystem_folders). Use 'dku connection list' to see options.",
    ),
    folder_type: str | None = typer.Option(
        None, "--type", "-t", help="Folder type (e.g., Filesystem, S3)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False,
        "--if-not-exists",
        help="Skip if a folder with this name already exists",
    ),
) -> None:
    """Create a new managed folder.

    Returns the folder ID (8-char string) needed by other folder commands.
    Default connection is 'filesystem_folders'. Use --connection for S3/GCS/etc.

    Workflow: create folder → upload files → create-dataset → recipe create-embed-docs
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # --if-not-exists: pre-scan by name
        if if_not_exists:
            existing = proj.list_managed_folders()
            for f in existing:
                if f.get("name", "") == name:
                    if output == "json":
                        render_raw(
                            {"id": f["id"], "name": name, "status": "already_exists"},
                            output_format="json",
                        )
                    else:
                        warn(
                            f"Managed folder '{name}' already exists (id={f['id']}), skipping."
                        )
                    return

        folder = proj.create_managed_folder(
            name, folder_type=folder_type, connection_name=connection
        )
        folder_id = folder.id

        if output == "json":
            render_raw(
                {"id": folder_id, "name": name, "status": "created"},
                output_format="json",
            )
        else:
            success(
                f"Created managed folder '{name}' (id={folder_id}) in {project_key}"
            )
            info(
                f"Use this ID for folder commands: dku folder ls {folder_id} -P {project_key}"
            )
    except typer.Exit:
        raise
    except Exception as e:
        if is_already_exists_error(e):
            exit_with_error(
                f"Managed folder '{name}' already exists in {project_key}.",
                details=[
                    f'Use --if-not-exists to skip: dku folder create "{name}" --if-not-exists -P {project_key}',
                    f"List folders: dku folder list -P {project_key}",
                ],
            )
        # Catch both common DSS refusal shapes for managed-folder creation:
        #   - "You may not create a managed folder on connection X" (permission)
        #   - "Invalid connection type for managed folders : PostgreSQL" (wrong type)
        # Either way the recovery is the same: find a connection that accepts folders.
        msg = str(e)
        folder_refused = (
            "may not create a managed folder" in msg
            or "You are not allowed to create a managed folder" in msg
            or "Invalid connection type for managed folders" in msg
        )
        if folder_refused:
            exit_with_error(
                f"Connection '{connection}' cannot host managed folders in {project_key}.",
                details=[
                    "Find a connection that accepts managed folders:",
                    f"  dku --format json folder list -P {project_key} | jq -r '.[0].params.connection'  (reuse what an existing folder uses)",
                    '  dku --format json connection list | jq -r \'.[] | select(.type | IN("Filesystem","S3","GCS","Azure","HDFS")) | .name\'',
                    f"Then retry with: dku folder create {name} -c <ALLOWED_CONN> -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a managed folder from the flow.

    NOTE: This removes the folder from the flow and any recipes using it,
    but does NOT delete the folder's file contents from the underlying storage.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)

        folder_name = folder.get_settings().get_raw().get("name", folder_ref)
        folder_id = folder.id if hasattr(folder, "id") else folder_ref

        from dku_cli.safety import Tier, guard

        guard(
            ctx,
            tier=Tier.DELETE,
            action="folder.delete",
            subject=f"managed folder '{folder_name}' ({folder_id}) in {project_key}",
            yes=yes,
            prompt=f"Delete managed folder '{folder_name}' ({folder_id}) from {project_key}? (File contents on underlying storage are preserved.)",
        )

        folder.delete()
        success(
            f"Deleted managed folder '{folder_name}' ({folder_id}) from {project_key}"
        )
        info("Note: File contents were NOT deleted from underlying storage.")
    except typer.Exit:
        raise
    except typer.Abort:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delete-file")
def delete_file(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    path: str = typer.Argument(help="Path of file to delete within the folder"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a file from a managed folder.

    No error is raised if the file doesn't exist (idempotent).
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="folder.delete_file",
        subject=f"file '{path}' in folder '{folder_ref}' ({project_key})",
        yes=yes,
        prompt=f"Delete file '{path}' from folder '{folder_ref}' in {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        folder.delete_file(path)
        success(f"Deleted {path} from folder {folder_ref}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get managed folder settings (name, type, connection, path)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        raw = folder.get_settings().get_raw()

        if output == "json":
            render_raw(raw, output_format="json")
        else:
            params = raw.get("params", {})
            data = [
                {"field": "id", "value": raw.get("id", "")},
                {"field": "name", "value": raw.get("name", "")},
                {"field": "type", "value": raw.get("type", "")},
                {"field": "connection", "value": params.get("connection", "")},
                {"field": "path", "value": params.get("path", "")},
            ]
            render(
                data,
                ["field", "value"],
                title=f"Folder: {raw.get('name', folder_ref)}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the full managed-folder definition as JSON.

    Returns the raw settings dict (id, name, type, params, metrics, checks).
    Parallel to `dku dataset get-definition` and `dku recipe get-definition`.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        raw = folder.get_settings().get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin)",
    ),
) -> None:
    """Replace the managed-folder definition from JSON.

    Always GET → edit → SET. Pass the full settings dict; the underlying
    DSS endpoint refuses changes to `id` and `projectKey`.
    """
    from dku_cli.helpers import read_json_input

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        new_def = read_json_input(definition)
        folder.set_definition(new_def)
        success(f"Updated definition for folder '{folder_ref}'")
    except Exception as e:
        handle_api_error(e)


@app.command("create-dataset")
def create_dataset(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    dataset_name: str = typer.Argument(help="Name for the new FilesInFolder dataset"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    format: str | None = typer.Option(
        None,
        "--format",
        help="Format type (csv, excel, parquet, json, avro, ...). Default: autodetect from files.",
    ),
    no_autodetect: bool = typer.Option(
        False,
        "--no-autodetect",
        help="Skip format autodetection (creates dataset with no format set; CSV will be assumed at read time)",
    ),
    sheet: str | None = typer.Option(
        None,
        "--sheet",
        help=(
            "Excel only: sheet name to read. Implies --format excel. Repeatable "
            "syntax not supported (one sheet per dataset; use one dataset per "
            "sheet for multi-sheet Excel files)."
        ),
    ),
    sheet_index: int | None = typer.Option(
        None,
        "--sheet-index",
        help=(
            "Excel only: 0-based sheet index alternative to --sheet. Implies "
            "--format excel."
        ),
    ),
    skip_rows_before: int | None = typer.Option(
        None,
        "--skip-rows-before",
        help=(
            "Excel/CSV: number of rows to skip BEFORE the header row (when the "
            "header is not on row 0 — common with banner/title rows in Excel)."
        ),
    ),
    no_header: bool = typer.Option(
        False,
        "--no-header",
        help="CSV/Excel: file has no header row; auto-name columns col_0, col_1, …",
    ),
) -> None:
    """Create a FilesInFolder dataset from a managed folder.

    This creates a dataset that reads files from the managed folder, useful for
    feeding document files (PDFs, images) into embed-docs or extract recipes,
    OR ingesting structured Excel/CSV/Parquet/JSON files.

    By default the dataset's format is autodetected from the folder contents
    (`autodetect_settings`). Pass --format to override (e.g. when the folder
    holds .xlsx files but autodetect picks up an unrelated .csv first), or
    --no-autodetect to skip detection entirely.

    For Excel files, prefer the typed Excel flags over a raw set-definition:
      dku folder create-dataset INV xls_inv --format excel --sheet "FY24" \\
        --skip-rows-before 3 -P PROJ

    Workflow: folder create → folder upload → folder create-dataset → recipe create-embed-docs
    """
    project_key = resolve_project(project)
    if (sheet or sheet_index is not None) and format and format.lower() != "excel":
        exit_with_error(
            f"--sheet/--sheet-index is only valid with --format excel (got '{format}').",
        )
    if sheet and sheet_index is not None:
        exit_with_error(
            "Pass either --sheet NAME or --sheet-index N, not both.",
        )
    excel_implied = bool(sheet or sheet_index is not None)
    if excel_implied and not format:
        format = "excel"
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        ds = folder.create_dataset_from_files(dataset_name)
        format_msg = ""
        if format:
            # Always run autodetect first so the dataset has the full set of
            # format defaults (separator, quoteChar, parseHeaderRow, ...).
            # Without this, an explicit --format csv produces a dataset DSS
            # can't read ("Missing parameters for CSV"). Detection failures
            # are tolerated — we'll fall back to a hand-rolled minimum below.
            try:
                ds.autodetect_settings().save()
            except Exception:
                pass
            settings = ds.get_settings()
            raw = settings.get_raw()
            detected_format = (raw.get("formatType") or "").lower()
            target = format.lower()
            raw["formatType"] = format
            # If the detected format differs from the requested one, the
            # detected formatParams keys are wrong for the new format. Reset
            # so we don't carry CSV defaults into an Excel dataset.
            if detected_format != target:
                raw["formatParams"] = {}
            params = raw.setdefault("formatParams", {})
            if target == "csv":
                # Sane CSV defaults for the case where detection failed or
                # picked a different format. autodetect-on-CSV usually fills
                # these — these defaults are the safety net.
                params.setdefault("separator", ",")
                params.setdefault("style", "excel")
                params.setdefault("charset", "utf8")
                params.setdefault("quoteChar", '"')
                params.setdefault("parseHeaderRow", True)
            elif target == "excel":
                params.setdefault("parseHeaderRow", True)
                params.setdefault("xlsxRowOverflowStrategy", "FAIL")
                if sheet:
                    params["sheets"] = sheet
                    params["sheetSelectionMode"] = "NAMES"
                elif sheet_index is not None:
                    params["sheets"] = str(sheet_index)
                    params["sheetSelectionMode"] = "INDICES"
            if skip_rows_before is not None:
                params["skipRowsBeforeHeader"] = skip_rows_before
            if no_header:
                params["parseHeaderRow"] = False
            settings.save()
            extras = []
            if sheet:
                extras.append(f"sheet={sheet}")
            elif sheet_index is not None:
                extras.append(f"sheet-index={sheet_index}")
            if skip_rows_before is not None:
                extras.append(f"skip-rows-before={skip_rows_before}")
            extra_str = (", " + ", ".join(extras)) if extras else ""
            format_msg = f" (format={format}, explicit{extra_str})"
        elif not no_autodetect:
            try:
                detected = ds.autodetect_settings()
                detected.save()
                format_msg = f" (format={detected.get_raw().get('formatType', '?')}, autodetected)"
            except Exception as detect_err:  # noqa: BLE001
                warn(
                    f"Autodetect failed ({detect_err}); dataset created with default format. "
                    f"Re-run with --format <type> if reads break."
                )
        success(
            f"Created FilesInFolder dataset '{dataset_name}' from folder {folder_ref} in {project_key}{format_msg}"
        )
        info(
            f"Tip: dku recipe create-embed-docs RECIPE --input {dataset_name} "
            f"--output-kb KB --embedding-llm LLM -P {project_key}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        if is_already_exists_error(e):
            exit_with_error(
                f"Dataset '{dataset_name}' already exists in {project_key}.",
                details=[
                    f"Choose a different name or delete it first: dku dataset delete {dataset_name} -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command("list")
def list_folders(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List managed folders in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    prefix: str = typer.Option("/", "--prefix", help="Path prefix to list"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List contents of a managed folder."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
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
            title=f"Folder: {folder_ref}",
            headers={"path": "PATH", "size": "SIZE", "last_modified": "MODIFIED"},
        )
    except Exception as e:
        handle_api_error(e)


def _put_file_with_retry(
    folder, remote_path: str, local_path: Path, retries: int
) -> int:
    """Upload one file to a managed folder with bounded retry.

    Returns the number of retries actually used (0 if first attempt succeeded).
    Raises the last exception if all attempts fail. ``retries`` is the number
    of EXTRA attempts after the first — so retries=2 means up to 3 total tries.
    """
    import time

    attempts = max(1, retries + 1)
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with local_path.open("rb") as f:
                folder.put_file(remote_path, f)
            return attempt
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                # Brief linear backoff. Server-side hiccups (DSS proxy timeout,
                # rate limits, transient socket) usually clear within a few s.
                time.sleep(1.0 + attempt)
    assert last_exc is not None
    raise last_exc


@app.command()
def upload(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    local_path: Path = typer.Argument(help="Local file to upload"),
    remote_path: str = typer.Option(
        None, "--path", help="Remote path (defaults to filename)"
    ),
    retry: int = typer.Option(
        2,
        "--retry",
        help=(
            "Number of retries after the first attempt (default 2 ⇒ up to 3 "
            "tries). DSS proxies occasionally return transient errors mid-stream."
        ),
        min=0,
        max=10,
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
        folder = resolve_folder(proj, folder_ref)

        retries_used = _put_file_with_retry(folder, target, local_path, retry)

        if retries_used:
            success(
                f"Uploaded {local_path.name} → {target} (recovered after {retries_used} retry/retries)"
            )
        else:
            success(f"Uploaded {local_path.name} → {target}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def download(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    remote_path: str = typer.Argument(help="Remote file path"),
    dest: Path = typer.Option(".", "--dest", "-d", help="Local destination directory"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Download a file from a managed folder."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)

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


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Folder description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update managed folder description and/or tags.

    Accepts folder ID or name. No JSON needed.
    """
    if description is None and tags is None:
        error("Provide --description and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        defn = folder.get_definition()

        if description is not None:
            defn["description"] = description
        if tags is not None:
            defn["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        folder.set_definition(defn)
        success(f"Updated metadata for folder '{folder_ref}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def rename(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    new_name: str = typer.Argument(help="New name for the folder"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Rename a managed folder."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        folder.rename(new_name)
        success(f"Renamed folder '{folder_ref}' → '{new_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def copy(
    ctx: typer.Context,
    source_ref: str = typer.Argument(help="Source managed folder ID or name"),
    target_ref: str = typer.Argument(help="Target managed folder ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    write_mode: str = typer.Option(
        "OVERWRITE",
        "--write-mode",
        "-w",
        help="Write mode: OVERWRITE or APPEND",
    ),
    target_project: str = typer.Option(
        None,
        "--target-project",
        help="Target project key (defaults to same project)",
    ),
) -> None:
    """Copy contents of one managed folder to another.

    Both folders must exist. Returns when the async copy completes.
    """
    project_key = resolve_project(project)
    target_project_key = target_project or project_key
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        source = resolve_folder(proj, source_ref)
        target_proj = client.get_project(target_project_key)
        target = resolve_folder(target_proj, target_ref)
        future = source.copy_to(target, write_mode=write_mode)
        future.wait_for_result()
        success(f"Copied folder '{source_ref}' → '{target_ref}' (mode={write_mode})")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("upload-dir")
def upload_dir(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    local_dir: Path = typer.Argument(help="Local directory to upload"),
    remote_prefix: str = typer.Option(
        "/", "--prefix", help="Remote path prefix (default: /)"
    ),
    retry: int = typer.Option(
        2,
        "--retry",
        help=(
            "Number of retries per file after the first attempt (default 2 ⇒ "
            "up to 3 tries). Batch uploads in particular hit transient DSS "
            "proxy errors mid-stream; the CLI tallies recoveries and continues."
        ),
        min=0,
        max=10,
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help=(
            "Stop on the first file that fails after retries. Default is to "
            "keep uploading the rest and report a summary at the end."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Upload an entire local directory to a managed folder.

    All files are uploaded preserving the directory structure. Each file is
    retried independently on transient errors. With --fail-fast the upload
    stops on the first hard failure; otherwise failed files are tallied and
    surfaced in the summary so you can retry only the misses.
    """
    project_key = resolve_project(project)
    if not local_dir.is_dir():
        error(f"Not a directory: {local_dir}")
        raise typer.Exit(1)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)

        uploaded = 0
        retries_total = 0
        failed: list[tuple[Path, str]] = []  # (path, last_error_msg)
        for root, _dirs, files in os.walk(local_dir):
            for filename in files:
                local_path = Path(root) / filename
                relative = local_path.relative_to(local_dir)
                remote_path = f"{remote_prefix.rstrip('/')}/{relative}"
                try:
                    retries_total += _put_file_with_retry(
                        folder, remote_path, local_path, retry
                    )
                    uploaded += 1
                except Exception as exc:
                    failed.append((local_path, str(exc)))
                    if fail_fast:
                        raise

        # Build a single-line summary the agent can grep on.
        summary = f"Uploaded {uploaded}/{uploaded + len(failed)} from {local_dir} → {remote_prefix}"
        if retries_total:
            summary += f" (retries used: {retries_total})"
        if failed:
            summary += f"; failed: {len(failed)}"
            warn(summary)
            # Per-file diagnostics so retries are scriptable.
            for path, msg in failed:
                error(f"  failed: {path} — {msg}")
            raise typer.Exit(1)
        success(summary)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delete-files")
def delete_files(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    paths: list[str] = typer.Argument(help="Paths of files to delete"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete multiple files from a managed folder.

    Pass one or more file paths as arguments.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="folder.delete_files",
        subject=f"{len(paths)} file(s) in folder '{folder_ref}' ({project_key})",
        yes=yes,
        prompt=f"Delete {len(paths)} file(s) from folder '{folder_ref}' in {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)
        for path in paths:
            folder.delete_file(path)
        success(f"Deleted {len(paths)} file(s) from folder {folder_ref}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def decompress(
    ctx: typer.Context,
    folder_ref: str = typer.Argument(help="Managed folder ID or name"),
    archive_path: str = typer.Argument(
        help="Path to zip/tar.gz archive within the folder"
    ),
    dest: str = typer.Option(
        None,
        "--dest",
        "-d",
        help="Destination path within folder (default: same directory as archive)",
    ),
    delete_archive: bool = typer.Option(
        False,
        "--delete-archive",
        help="Delete the archive after extraction",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Extract a zip archive inside a managed folder.

    Downloads the archive, extracts it locally, uploads all extracted files
    back to the folder. Supports .zip files.

    The DSS UI has "UNCOMPRESS TO CURRENT FOLDER" but that endpoint is
    session-only (no API key auth). This command does equivalent work
    client-side.

    Example: dku folder decompress FOLDER_ID /Places.zip -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        folder = resolve_folder(proj, folder_ref)

        # Determine destination prefix
        if dest is not None:
            dest_prefix = dest.rstrip("/")
        else:
            # Same directory as the archive
            parent = "/".join(archive_path.split("/")[:-1])
            dest_prefix = parent if parent else ""

        # Download the archive
        info(f"Downloading {archive_path}...")
        stream = folder.get_file(archive_path)
        archive_data = io.BytesIO(stream.content)

        if not zipfile.is_zipfile(archive_data):
            exit_with_error(
                f"'{archive_path}' is not a valid zip file.",
                details=[
                    "Only .zip archives are supported.",
                    f"Check file: dku folder ls {folder_ref} -P {project_key}",
                ],
            )

        archive_data.seek(0)
        extracted_files = []

        with zipfile.ZipFile(archive_data, "r") as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            info(f"Extracting {len(members)} file(s)...")

            with tempfile.TemporaryDirectory() as tmpdir:
                zf.extractall(tmpdir)
                for member in members:
                    local_path = Path(tmpdir) / member.filename
                    remote_path = f"{dest_prefix}/{member.filename}"
                    with local_path.open("rb") as f:
                        folder.put_file(remote_path, f)
                    extracted_files.append(remote_path)

        if delete_archive:
            folder.delete_file(archive_path)
            info(f"Deleted archive {archive_path}")

        if output == "json":
            render_raw(
                {
                    "archive": archive_path,
                    "destination": dest_prefix or "/",
                    "files_extracted": len(extracted_files),
                    "files": extracted_files,
                    "archive_deleted": delete_archive,
                },
                output_format="json",
            )
        else:
            success(
                f"Extracted {len(extracted_files)} file(s) from {archive_path} → {dest_prefix or '/'}"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
