"""Append-only JSONL audit log for the ``dku_exec`` tool.

One line per executor call, written to ``<state_root>/audit/exec.jsonl``.
Thread-safe so concurrent agent sessions don't interleave partial lines.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class AuditLog:
    """Thread-safe JSONL appender."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _chmod(self.path.parent, 0o700)
        self._lock = threading.Lock()

    def record(self, event: dict) -> None:
        line = json.dumps(event, default=str)
        with self._lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            _chmod(self.path, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass
