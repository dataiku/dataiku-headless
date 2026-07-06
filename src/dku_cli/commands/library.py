"""dku library — list, read, write, delete, mkdir, sync."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path, PurePosixPath

import typer

from dku_cli.commands._library_sync import (
    _DEFAULT_EXCLUDES,
    _collect_local_files,
    _delete_folder_recursive,
    _is_library_folder,
    _list_remote_files,
    _report_delete_failures,
)
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, resolve_output_format, success, warn

app = typer.Typer(help="Manage DSS project library files.")


def _get_or_create_folder(lib, folder_path: str):
    """Navigate to a folder, creating intermediate dirs as needed."""
    parts = PurePosixPath(folder_path).parts
    current = lib
    for part in parts:
        child = None
        with contextlib.suppress(Exception):
            child = current.get_folder(part)
        current = current.add_folder(part) if child is None else child
    return current


@app.command("list")
def list_files(
    ctx: typer.Context,
    path: str = typer.Option("/", "--path", help="Directory path to list"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List files in the project library."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
            data.append(
                {
                    "path": item.path,
                }
            )

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
    content: str = typer.Option(
        ...,
        "--content",
        "-c",
        help="Content: literal string, @file.py to read from file, or - for stdin",
    ),
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

        # get_file() returns None for missing files (does NOT raise)
        f = lib.get_file(path)
        if f is None:
            # File doesn't exist — create it in the appropriate folder
            if parent and parent != ".":
                folder = _get_or_create_folder(lib, parent)
                f = folder.add_file(filename)
            else:
                f = lib.add_file(filename)
            # add_file() may return None in some dataikuapi versions — re-fetch
            if f is None:
                if parent and parent != ".":
                    f = folder.get_file(filename)
                else:
                    f = lib.get_file(path)

        if f is None:
            exit_with_error(
                f"Could not open file '{path}' for writing in project library.",
                details=[
                    f"Try creating the parent directory first: dku library mkdir {parent} -P {project_key}"
                ],
            )
        f.write(content_bytes)
        success(f"Wrote {len(content_bytes)} bytes to {path}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    path: str = typer.Argument(help="File or folder path in the library"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Recursively delete a folder and every file under it. "
        "Tier-3 CASCADE safety — requires --confirm-name to match the folder path.",
    ),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must match the folder path to proceed (tier-3 cascade, --recursive only).",
    ),
) -> None:
    """Delete a file (or, with --recursive, a folder tree) from the library.

    Without --recursive, the target must be a file — pointing at a folder
    emits a prescriptive error showing the recursive recovery one-liner.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)

    if recursive:
        guard(
            ctx,
            tier=Tier.CASCADE,
            action="library.delete-recursive",
            subject=f"library folder '{path}' in {project_key} (and ALL descendant files)",
            yes=yes,
            target_id=path,
            confirm_name=confirm_name,
            prompt=(
                f"Recursively delete library folder '{path}' from {project_key}? "
                "This wipes every file beneath it."
            ),
        )
        try:
            client = get_client_from_ctx(ctx)
            proj = client.get_project(project_key)
            lib = proj.get_library()
            if not _is_library_folder(lib, path):
                exit_with_error(
                    f"'{path}' is not a folder in the project library — "
                    "--recursive only applies to folders.",
                    details=[
                        "For a single file, drop --recursive:",
                        f"  dku library delete '{path}' -P {project_key} --yes",
                    ],
                    status=2,
                )
            files_deleted, folders_deleted, failures = _delete_folder_recursive(
                lib, path
            )
            _report_delete_failures(
                failures, files_deleted, folders_deleted, path, project_key
            )
            success(
                f"Deleted {files_deleted} file(s) "
                f"and {folders_deleted} folder(s) under '{path}'"
            )
            return
        except typer.Exit:
            raise
        except Exception as e:
            handle_api_error(e)
            return

    guard(
        ctx,
        tier=Tier.DELETE,
        action="library.delete",
        subject=f"library file '{path}' in {project_key}",
        yes=yes,
        prompt=f"Delete library file '{path}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        try:
            f = lib.get_file(path)
            f.delete()
        except Exception as inner:
            # Bare DSS error is "The item /X is a folder, not a file" —
            # surface the recursive escape hatch instead of a dead-end.
            # NOTE: dataikuapi raises from get_file() itself, not from
            # delete() — the path is rejected before the file handle is
            # returned. So this except wraps both calls.
            msg = str(inner)
            if "is a folder, not a file" in msg or "is a folder" in msg:
                exit_with_error(
                    f"'{path}' is a folder, not a file. Use --recursive to "
                    "delete the folder and everything beneath it.",
                    details=[
                        "Tier-3 cascade — wipes every descendant file:",
                        "",
                        f"  dku library delete '{path}' -P {project_key} \\\\",
                        f"    --recursive --yes --confirm-name '{path}'",
                        "",
                        "Or enumerate-and-delete one file at a time:",
                        "",
                        f"  dku --format json library list --path '{path}' -P {project_key} \\\\",
                        "    | jq -r '.[].path' \\\\",
                        f"    | xargs -I{{}} dku library delete '{{}}' -P {project_key} --yes",
                    ],
                    status=2,
                )
            raise

        success(f"Deleted {path}")
    except typer.Exit:
        raise
    except Exception as e:
        # get_file() raises "is a folder, not a file" when path points to a folder.
        if "not a file" in str(e):
            exit_with_error(
                f"'{path}' is a folder, not a file.",
                details=[
                    f"Delete it recursively with: dku library delete-folder {path} "
                    f"-P {project_key} --yes --confirm-name {path}"
                ],
            )
        handle_api_error(e)


@app.command("delete-folder")
def delete_folder(
    ctx: typer.Context,
    path: str = typer.Argument(help="Folder path in the library"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must match the folder PATH to proceed (tier-3 cascade).",
    ),
) -> None:
    """Recursively delete a folder and all its contents from the project library."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)

    # Refuse root deletion up front (dataikuapi raises "Cannot delete root folder").
    if path.strip() in ("", "/"):
        exit_with_error(
            "Refusing to delete the library root.",
            details=[
                "Pass a specific folder path, e.g. dku library delete-folder python/mylib"
            ],
        )

    guard(
        ctx,
        tier=Tier.CASCADE,
        action="library.delete-folder",
        subject=f"library folder '{path}' in {project_key} (deletes all files inside)",
        yes=yes,
        target_id=path,
        confirm_name=confirm_name,
        prompt=f"Recursively delete library folder '{path}' and everything in it from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()
        folder = lib.get_folder(path)  # None if missing; raises if path is a file
        if folder is None:
            exit_with_error(
                f"Library folder '{path}' not found in {project_key}.",
                details=[f"List contents with: dku library list -P {project_key}"],
            )
        folder.delete()
        success(f"Deleted folder {path} and its contents")
    except typer.Exit:
        raise
    except Exception as e:
        # get_folder() raises "is a file, not a folder" when path points to a file.
        if "not a folder" in str(e):
            exit_with_error(
                f"'{path}' is a file, not a folder.",
                details=[
                    f"Delete a single file with: dku library delete {path} -P {project_key} --yes"
                ],
            )
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


@app.command()
def sync(
    ctx: typer.Context,
    local_dir: str = typer.Argument(help="Local directory to sync from"),
    remote_dir: str = typer.Argument(
        "/", help="Remote library path to sync to (default: root)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    delete: bool = typer.Option(
        False, "--delete", help="Delete remote files not present locally"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would be synced without doing it"
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-e", help="Additional glob patterns to exclude"
    ),
) -> None:
    """Sync a local directory to the project library.

    Uploads all files from LOCAL_DIR to REMOTE_DIR in the DSS project library,
    creating directories as needed. Skips .git, __pycache__, .DS_Store, *.pyc
    by default.
    """
    project_key = resolve_project(project)
    local_path = Path(local_dir)

    if not local_path.is_dir():
        exit_with_error(
            f"Local directory not found: {local_dir}",
            details=["Provide a path to an existing directory."],
        )

    excludes = _DEFAULT_EXCLUDES | set(exclude)
    local_files = _collect_local_files(local_path, excludes)

    if not local_files:
        info("No files to sync (all excluded or directory empty).")
        return

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        lib = proj.get_library()

        # Normalise remote_dir
        remote_base = remote_dir.strip("/")

        # Upload files
        uploaded = 0
        for abs_path, rel_posix in local_files:
            remote_path = f"{remote_base}/{rel_posix}" if remote_base else rel_posix

            if dry_run:
                info(f"(dry-run) Would upload: {rel_posix} → {remote_path}")
            else:
                p = PurePosixPath(remote_path)
                parent = str(p.parent)
                filename = p.name

                # Ensure parent directory exists
                if parent and parent != ".":
                    folder = _get_or_create_folder(lib, parent)
                    f = lib.get_file(remote_path)
                    if f is None:
                        f = folder.add_file(filename)
                        if f is None:
                            f = folder.get_file(filename)
                else:
                    f = lib.get_file(remote_path)
                    if f is None:
                        f = lib.add_file(filename)
                        if f is None:
                            f = lib.get_file(remote_path)

                if f is None:
                    exit_with_error(
                        f"Could not write '{remote_path}' to project library.",
                        details=[
                            f"Try creating the parent directory first: dku library mkdir {parent} -P {project_key}"
                        ],
                    )

                content = abs_path.read_bytes()
                f.write(content)
                info(f"Uploaded: {rel_posix} → {remote_path}")
            uploaded += 1

        # Delete remote files not in local
        deleted = 0
        if delete:
            local_remotes = set()
            for _, rel_posix in local_files:
                if remote_base:
                    local_remotes.add(f"{remote_base}/{rel_posix}")
                else:
                    local_remotes.add(rel_posix)

            remote_files = _list_remote_files(lib, remote_base or "/")
            to_delete = remote_files - local_remotes

            delete_failures = 0
            for rpath in sorted(to_delete):
                if dry_run:
                    info(f"(dry-run) Would delete: {rpath}")
                    deleted += 1
                    continue
                try:
                    rf = lib.get_file(rpath)
                    if rf is not None:
                        rf.delete()
                        info(f"Deleted: {rpath}")
                    deleted += 1
                except Exception as del_err:
                    delete_failures += 1
                    warn(f"Failed to delete {rpath}: {del_err}")
            if delete_failures:
                exit_with_error(
                    f"{delete_failures} remote file(s) could not be deleted "
                    f"during sync (deleted {deleted}).",
                    details=[
                        "Re-run the sync, or delete the files individually: "
                        f"dku library delete <path> -P {project_key}",
                    ],
                )

        if dry_run:
            summary = f"(dry-run) Would sync {uploaded} file(s)"
            if delete and deleted:
                summary += f", delete {deleted} file(s)"
            info(summary)
        else:
            summary = f"Synced {uploaded} file(s) to {remote_dir}"
            if delete and deleted:
                summary += f", deleted {deleted} file(s)"
            success(summary)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
