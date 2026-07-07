"""Shared definition-merge helpers."""

from __future__ import annotations


def deep_merge_dicts(base: dict, patch: dict) -> dict:
    """Recursively merge *patch* into *base*; non-dict patch values replace."""
    merged = dict(base)
    for key, value in patch.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_params_preserving_siblings(
    raw: dict, patch: dict, deep: bool = False
) -> None:
    if not isinstance(patch, dict):
        raw.update(patch)
        return
    if deep:
        merged = deep_merge_dicts(raw, patch)
        raw.clear()
        raw.update(merged)
        return
    params = patch.get("params")
    if isinstance(params, dict) and isinstance(raw.get("params"), dict):
        top_level = dict(patch)
        top_level.pop("params")
        raw.update(top_level)
        raw["params"].update(params)
        return
    raw.update(patch)
