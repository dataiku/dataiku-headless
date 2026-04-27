"""dku library — list, read, write, delete, mkdir, sync."""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path, PurePosixPath

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, resolve_output_format, success

app = typer.Typer(help="Manage DSS project library files.")


def _get_or_create_folder(lib, folder_path: str):
    """Navigate to a folder, creating intermediate dirs as needed."""
    parts = PurePosixPath(folder_path).parts
    current = lib
    for part in parts:
        child = None
        try:
            child = current.get_folder(part)
        except Exception:
            pass
        if child is None:
            current = current.add_folder(part)
        else:
            current = child
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
    path: str = typer.Argument(help="File path in the library"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a file from the project library."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
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
        f = lib.get_file(path)
        f.delete()

        success(f"Deleted {path}")
    except typer.Exit:
        raise
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


# Default patterns to exclude from sync
_DEFAULT_EXCLUDES = {
    ".git",
    "__pycache__",
    ".DS_Store",
    "*.pyc",
    ".venv",
    "node_modules",
    ".ruff_cache",
}


def _collect_local_files(local_dir: Path, excludes: set[str]) -> list[tuple[Path, str]]:
    """Walk *local_dir* and return (abs_path, relative_posix_path) pairs."""
    files: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(local_dir):
        # Prune excluded directories in-place
        dirnames[:] = [
            d for d in dirnames if not any(fnmatch.fnmatch(d, pat) for pat in excludes)
        ]
        for fname in filenames:
            if any(fnmatch.fnmatch(fname, pat) for pat in excludes):
                continue
            abs_path = Path(dirpath) / fname
            rel = abs_path.relative_to(local_dir).as_posix()
            files.append((abs_path, rel))
    return files


def _list_remote_files(lib, folder_path: str) -> set[str]:
    """Recursively list all file paths under a library folder."""
    remote: set[str] = set()

    def _walk(container, prefix: str) -> None:
        for item in container.list():
            item_path = item.path
            # item.path may be absolute from library root — make relative
            if prefix and not item_path.startswith(prefix):
                item_path = f"{prefix}/{item_path}"
            # DSSLibraryItem: check if it has a .list() method (folder) or not (file)
            try:
                item.list()  # probe: raises if item is a file, not a folder
                _walk(item, item_path)
            except Exception:
                remote.add(item_path)

    try:
        if folder_path == "/":
            _walk(lib, "")
        else:
            folder = lib.get_folder(folder_path)
            _walk(folder, folder_path)
    except Exception:
        pass  # Folder doesn't exist yet — no remote files
    return remote


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
            if remote_base:
                remote_path = f"{remote_base}/{rel_posix}"
            else:
                remote_path = rel_posix

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

            for rpath in sorted(to_delete):
                if dry_run:
                    info(f"(dry-run) Would delete: {rpath}")
                else:
                    try:
                        rf = lib.get_file(rpath)
                        if rf is not None:
                            rf.delete()
                            info(f"Deleted: {rpath}")
                    except Exception:
                        pass  # File may already be gone
                deleted += 1

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
