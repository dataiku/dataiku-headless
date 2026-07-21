"""Tests for the shared serialization helpers.

Focused on ``bounded_compact_json`` — the plain size-check-and-clip byte ceiling
reused by the settings inspector and other bounded read tools. It is deliberately
NOT a binary-search envelope fit: it bounds the payload's own serialized bytes and
keeps truthful counts, without guaranteeing a byte-exact final frame.
"""

import json

from dataiku_mcp.tools.utils.serialization import bounded_compact_json, compact_json


def test_small_payload_is_returned_unchanged():
    obj = {"a": 1, "b": ["x", "y"]}
    out = bounded_compact_json(obj, 1_000_000)
    assert out == compact_json(obj)
    assert json.loads(out) == obj


def test_payload_exactly_at_ceiling_is_not_truncated():
    encoded = compact_json({"k": "v"})
    out = bounded_compact_json({"k": "v"}, len(encoded.encode("utf-8")))
    assert json.loads(out) == {"k": "v"}


def test_oversized_payload_is_clipped_with_truthful_counts():
    max_bytes = 2_000
    obj = {"blob": "x" * (max_bytes + 5_000)}
    out = json.loads(bounded_compact_json(obj, max_bytes))
    assert out["truncated"] is True
    assert out["truncation_reason"] == "max_response_bytes"
    assert out["returned_bytes"] <= max_bytes
    assert out["total_bytes"] > max_bytes
    assert isinstance(out["payload_json_truncated"], str)


def test_custom_payload_key_is_used():
    max_bytes = 500
    obj = {"blob": "y" * (max_bytes + 2_000)}
    out = json.loads(bounded_compact_json(obj, max_bytes, payload_key="settings_json_truncated"))
    assert "settings_json_truncated" in out
    assert "payload_json_truncated" not in out


def test_clip_lands_on_a_utf8_boundary():
    # A multi-byte character straddling the clip boundary must not corrupt the
    # returned prefix — the clip decodes with errors="ignore".
    max_bytes = 100
    obj = {"blob": "é" * 500}  # 2 bytes each in UTF-8
    out = json.loads(bounded_compact_json(obj, max_bytes))
    # Round-trips as valid text (no partial code unit) and stays within ceiling.
    assert out["payload_json_truncated"].encode("utf-8")
    assert out["returned_bytes"] <= max_bytes
