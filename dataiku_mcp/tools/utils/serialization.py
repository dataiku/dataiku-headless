"""Compact JSON serialization for MCP tool results."""

import json
from typing import Any


def compact_json(obj: Any) -> str:
    """Serialize ``obj`` as compact JSON for a tool result.

    Replaces the previous pretty-printed (2-space-indented) tool-result returns:
    identical content, compact separators, no indentation whitespace — ~20–50% smaller
    per result depending on nesting, compounding through the re-read multiplier (every
    committed result is re-sent on every later turn).
    """
    return json.dumps(obj, separators=(",", ":"), default=str)


def columnar(rows: list, columns: list) -> dict:
    """Render a list of uniform dicts as a keys-once ``{"columns", "rows"}`` table.

    ``rows[i]`` becomes ``[row.get(c) for c in columns]`` (missing keys -> None), so
    the column names are written once instead of repeated on every row. Lossless and
    self-describing; ~15-20% smaller on row returns on top of compact_json, compounding
    through the re-read multiplier.
    """
    return {"columns": list(columns), "rows": [[row.get(c) for c in columns] for row in rows]}


def is_empty(value: Any) -> bool:
    """True for no-information values: ``None``, ``""``, ``[]``, ``{}``.

    ``False``, ``0`` and ``0.0`` are NOT empty (they are not equal to any of the
    above), so information-bearing falsy values are preserved.
    """
    return value in (None, "", [], {})


def omit_empty(d: dict) -> dict:
    """Drop keys whose value ``is_empty`` from a result dict (shallow, non-recursive).

    Absent reads as empty by JSON convention, so omitting these is lossless; keeps
    ``False``/``0``.
    """
    return {k: v for k, v in d.items() if not is_empty(v)}
