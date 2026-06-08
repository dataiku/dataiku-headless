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
        self._lock = threading.Lock()

    def record(self, event: dict) -> None:
        line = json.dumps(event, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
