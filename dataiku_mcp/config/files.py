"""Shared JSON file operations for transport configuration."""

import json
import os
import tempfile
from pathlib import Path


def read_json_object(path: Path, *, description: str = "Settings file") -> dict:
    """Read a UTF-8 JSON object from path."""
    with open(path, encoding="utf-8") as file:
        document = json.load(file)
    if not isinstance(document, dict):
        raise ValueError(f"{description} must be a JSON object.")
    return document


def write_json_atomic(path: Path, document: dict) -> None:
    """Atomically write a UTF-8 JSON object with user-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix="config.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(document, temp_file, indent=2)
            temp_file.write("\n")
        temp_path.chmod(0o600)
        os.replace(temp_path, path)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
