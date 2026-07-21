"""Compact JSON serialization for MCP tool results."""

import json
from typing import Any


def compact_json(obj: Any) -> str:
    """Serialize ``obj`` as compact JSON for a tool result.

    Replaces the previous pretty-printed (2-space-indented) tool-result returns:
    identical content, compact separators, no indentation whitespace — ~20–50% smaller
    per result depending on nesting, compounding through the re-read multiplier (every
    committed result is re-sent on every later turn). See token-benchmarks/ASSESSMENT.md §5.
    """
    return json.dumps(obj, separators=(",", ":"), default=str)


def bounded_compact_json(
    obj: Any,
    max_bytes: int,
    payload_key: str = "payload_json_truncated",
) -> str:
    """Serialize ``obj`` as compact JSON under a hard UTF-8 byte ceiling.

    Plain size-check-and-clip — deliberately *not* a binary search. A payload that
    fits keeps its ordinary schema. An oversized payload is clipped to the largest
    UTF-8-safe prefix of its own serialization and returned as a small envelope
    that reports the elided byte counts. The clipped prefix is diagnostic evidence,
    not a claim that partial JSON parses.

    Note the ceiling bounds the *payload's* serialized bytes, not the final
    envelope: re-escaping the clipped prefix into the outer JSON can inflate it
    (worst case ~2x for quote-heavy content). That is the accepted trade for
    dropping the binary-search envelope fit — the goal is a bounded read, not a
    byte-exact response frame. Shared by the settings inspector and other bounded
    read tools.
    """
    encoded = compact_json(obj)
    raw = encoded.encode("utf-8")
    if len(raw) <= max_bytes:
        return encoded
    clipped = raw[:max_bytes].decode("utf-8", errors="ignore")
    return compact_json(
        {
            "truncated": True,
            "truncation_reason": "max_response_bytes",
            "total_bytes": len(raw),
            "returned_bytes": len(clipped.encode("utf-8")),
            payload_key: clipped,
        }
    )


def columnar(rows: list, columns: list) -> dict:
    """Render a list of uniform dicts as a keys-once ``{"columns", "rows"}`` table.

    ``rows[i]`` becomes ``[row.get(c) for c in columns]`` (missing keys -> None), so
    the column names are written once instead of repeated on every row. Lossless and
    self-describing; ~15-20% smaller on row returns on top of compact_json, compounding
    through the re-read multiplier. See token-benchmarks/ASSESSMENT.md §5.
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
    ``False``/``0``. See token-benchmarks/ASSESSMENT.md §5.
    """
    return {k: v for k, v in d.items() if not is_empty(v)}
