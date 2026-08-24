"""Shared parsing/coercion helpers for tool modules."""

from __future__ import annotations

import json
from typing import Any

from .validation import require_non_empty_strings


def parse_json_object(raw_json: str, field_name: str) -> dict:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for '{field_name}': {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"'{field_name}' must be a JSON object")
    return parsed


def coerce_json_object(value: Any, field_name: str) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return parse_json_object(value, field_name)
    raise ValueError(f"'{field_name}' must be a JSON object or JSON string object")


def parse_json_array(raw_json: str, field_name: str) -> list:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for '{field_name}': {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"'{field_name}' must be a JSON array")
    return parsed


def coerce_json_array(value: Any, field_name: str) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return parse_json_array(value, field_name)
    raise ValueError(f"'{field_name}' must be a JSON array or JSON string array")


def get_bool_value(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if value is not True and value is not False:
        raise ValueError(f"'{field_name}' must be a boolean")
    return value


def parse_non_empty_string_list(raw_json: str, field_name: str) -> list[str]:
    parsed = parse_json_array(raw_json, field_name)
    if len(parsed) < 1:
        raise ValueError(f"'{field_name}' must be a non-empty JSON array")

    return require_non_empty_strings(parsed, field_name)


def deep_merge_dict(base: dict, patch: dict) -> dict:
    """Apply a JSON Merge Patch to a dict, with null values removing keys."""
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            current = merged.get(key)
            merged[key] = deep_merge_dict(
                current if isinstance(current, dict) else {}, value
            )
        else:
            merged[key] = value
    return merged
