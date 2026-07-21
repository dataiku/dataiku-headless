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
    """Serialize ``obj`` with a hard UTF-8 byte ceiling.

    Normal payloads keep their ordinary schema. An oversized payload becomes a
    small, valid JSON envelope containing the largest UTF-8-safe prefix that
    fits. The prefix is evidence for diagnosis, not a claim that partial JSON is
    complete or parseable.
    """
    encoded = compact_json(obj)
    raw = encoded.encode("utf-8")
    if len(raw) <= max_bytes:
        return encoded

    def envelope_for(clip_bytes: int) -> dict[str, Any]:
        clipped = raw[:clip_bytes].decode("utf-8", errors="ignore")
        return {
            "truncated": True,
            "truncation_reason": "max_response_bytes",
            "total_bytes": len(raw),
            "returned_bytes": len(clipped.encode("utf-8")),
            payload_key: clipped,
        }

    best = envelope_for(0)
    if len(compact_json(best).encode("utf-8")) > max_bytes:
        raise ValueError("max_bytes is too small for the truncation envelope")

    low, high = 0, len(raw)
    while low <= high:
        middle = (low + high) // 2
        candidate = envelope_for(middle)
        if len(compact_json(candidate).encode("utf-8")) <= max_bytes:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return compact_json(best)


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
