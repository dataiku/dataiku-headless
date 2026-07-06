"""Tile helpers for `dku app-designer` — summarize tile targets.

Splits the per-type target extraction (scenario / params / code / dataset /
dashboard / folder bindings) out of the command surface in app_designer.py.
"""

from __future__ import annotations


def _tile_target(tile: dict) -> str:
    """Extract a human-readable target reference from a tile."""
    # Dataset/folder/dashboard binding (applies to many tile types)
    ds = tile.get("datasetName", "")
    fid = tile.get("folderId", "")
    did = tile.get("dashboardId", "")

    t = tile.get("type", "")
    if t == "SCENARIO_RUN":
        return tile.get("scenarioId", "")
    if t == "PROJECT_VARIABLES_EDIT":
        n = len(tile.get("params", []))
        return f"{n} param(s)"
    if t == "INLINE_PYTHON_RUN":
        return "(code)"
    if ds:
        return ds
    if did:
        return did
    if fid:
        return fid
    return ""
