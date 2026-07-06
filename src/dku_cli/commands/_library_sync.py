"""Support helpers for `dku library` sync and recursive delete.

Extracted from ``library.py`` (which stays the sole home of the Typer
commands) to keep that module within the size ratchet. Nothing here is a
command — only the local-walk / remote-walk / delete-loop internals.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from dku_cli.errors import exit_with_error
from dku_cli.output import warn

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
    """Recursively list all file paths under a library folder.

    Returns paths normalised WITHOUT a leading slash (matches the form
    `dku library write` / `delete` accept). Real DSS returns `item.path`
    with a leading slash (e.g. ``/python/lib/foo.py``); we strip it.
    """
    remote: set[str] = set()

    def _normalize(p: str) -> str:
        return p.lstrip("/")

    def _walk(container) -> None:
        for item in container.list():
            item_path = _normalize(item.path)
            # DSSLibraryItem: check if it has a .list() method (folder)
            try:
                item.list()  # probe: raises if item is a file, not a folder
                _walk(item)
            except Exception:  # quality-ratchet: allow-broad-exception
                remote.add(item_path)

    try:
        if folder_path == "/" or folder_path == "":
            _walk(lib)
        else:
            folder = lib.get_folder(folder_path)
            _walk(folder)
    except Exception:  # quality-ratchet: allow-broad-exception
        pass  # Folder doesn't exist yet — no remote files
    return remote


def _is_library_folder(lib, path: str) -> bool:
    """Return True if `path` resolves to a folder (not a file) in the library.

    Best-effort: a folder responds to `.list()`, a file does not. Returns
    False on any error so the caller can fall back to file-delete semantics.
    """
    try:
        folder = lib.get_folder(path)
        if folder is None:
            return False
        folder.list()
        return True
    except Exception:  # quality-ratchet: allow-broad-exception
        return False


def _delete_folder_recursive(lib, folder_path: str) -> tuple[int, int, list[str]]:
    """Delete every file under `folder_path`, then the folder itself.

    Returns (file_count, folder_count, failures) so callers can summarise and
    surface per-path delete failures instead of silently reporting zero.
    """
    files = _list_remote_files(lib, folder_path)
    file_count = 0
    failures: list[str] = []
    for fpath in sorted(files):
        try:
            f = lib.get_file(fpath)
            if f is not None:
                f.delete()
                file_count += 1
        except Exception as del_err:  # quality-ratchet: allow-broad-exception
            failures.append(f"{fpath}: {del_err}")

    folder_count = 0
    try:
        folder = lib.get_folder(folder_path)
        if folder is not None and hasattr(folder, "delete"):
            folder.delete()
            folder_count = 1
    except Exception as del_err:  # quality-ratchet: allow-broad-exception
        failures.append(f"{folder_path}: {del_err}")
    return file_count, folder_count, failures


def _report_delete_failures(
    failures: list[str],
    files_deleted: int,
    folders_deleted: int,
    path: str,
    project_key: str,
) -> None:
    """Surface per-path delete failures and exit non-zero (no-op if none)."""
    if not failures:
        return
    for f in failures:
        warn(f"Failed to delete {f}")
    retry = f"dku library delete <path> -P {project_key}"
    exit_with_error(
        f"Deleted {files_deleted} file(s) and {folders_deleted} "
        f"folder(s) under '{path}', but {len(failures)} delete(s) failed.",
        details=[
            f"Re-run the recursive delete, or remove the remaining items "
            f"individually: {retry}",
        ],
    )
