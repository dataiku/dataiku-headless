"""Shared definition-merge helpers."""

from __future__ import annotations


def merge_params_preserving_siblings(raw: dict, patch: dict) -> None:
    if not isinstance(patch, dict):
        raw.update(patch)
        return
    params = patch.get("params")
    if isinstance(params, dict) and isinstance(raw.get("params"), dict):
        top_level = dict(patch)
        top_level.pop("params")
        raw.update(top_level)
        raw["params"].update(params)
        return
    raw.update(patch)
