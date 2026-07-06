"""File-transfer helpers for `dku folder` — retried uploads and zip safety.

Kept out of folder.py so the command surface stays a thin map: bounded-retry
upload used by `upload`/`upload-dir`, and the Zip-Slip member-path check used
by `decompress`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from dku_cli.errors import exit_with_error


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
        except Exception as exc:  # quality-ratchet: allow-broad-exception
            last_exc = exc
            if attempt + 1 < attempts:
                # Brief linear backoff. Server-side hiccups (DSS proxy timeout,
                # rate limits, transient socket) usually clear within a few s.
                time.sleep(1.0 + attempt)
    assert last_exc is not None
    raise last_exc


def _ensure_safe_zip_paths(zf: zipfile.ZipFile, archive_path: str) -> None:
    """Refuse archives with absolute or parent-traversal member paths (Zip-Slip)."""
    for m in zf.infolist():
        name = m.filename
        # Normalize once so a backslash-rooted entry (\Windows\win.ini)
        # is caught by the same absolute-path check as /etc/passwd.
        norm = name.replace("\\", "/")
        parts = norm.split("/")
        if norm.startswith("/") or (len(name) > 1 and name[1] == ":") or ".." in parts:
            exit_with_error(
                f"Refusing to extract unsafe path '{name}' from "
                f"'{archive_path}' (absolute or parent-traversal path).",
                details=[
                    "The archive contains a Zip-Slip path that would write "
                    "outside the destination folder.",
                    "Repackage the archive with relative member paths only.",
                ],
            )
