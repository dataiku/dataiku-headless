"""Agent version helpers shared by `dku agent` and `dku agent-review`.

Version copy/activation for agent saved models, plus structured-agent
loop-block wiring (a block-based agent's prompt and LLM live in the loop
block, not in top-level ``structuredAgentSettings``).
"""

from __future__ import annotations

import contextlib
import copy
import time

import typer

from dku_cli.output import error


def _next_version_id(versions: list) -> str:
    """Pick the next `vN` version id by inspecting existing ids."""
    nums: list[int] = []
    for v in versions:
        vid = v.get("versionId", "")
        if vid.startswith("v"):
            with contextlib.suppress(ValueError):
                nums.append(int(vid[1:]))
    return f"v{max(nums) + 1 if nums else 1}"


def _deep_copy_version(settings, source_vid: str | None = None) -> tuple[dict, str]:
    """Deep-copy a version into a new version dict appended to raw['versions'].

    Source defaults to the agent's active version. Returns (new_version_dict, new_vid).
    The new dict is a live reference inside raw['versions'] — mutate it then call
    settings.save() to persist. Caller activates via saved_model.set_active_version()
    (setting raw['activeVersion'] alone is not persisted).
    """
    raw = settings.get_raw()
    versions = raw.get("versions", [])
    if not versions:
        error("Agent has no versions to copy from.")
        raise typer.Exit(1)

    src_vid = source_vid or raw.get("activeVersion") or versions[0]["versionId"]
    source = next((v for v in versions if v.get("versionId") == src_vid), None)
    if source is None:
        error(
            f"Version '{src_vid}' not found. "
            "Use `dku agent list-versions` to list available versions."
        )
        raise typer.Exit(1)

    new_vid = _next_version_id(versions)
    new_version = copy.deepcopy(source)
    new_version["versionId"] = new_vid
    now_ms = int(time.time() * 1000)
    tag = {
        "versionNumber": 0,
        "lastModifiedBy": {"login": "api"},
        "lastModifiedOn": now_ms,
    }
    new_version["versionTag"] = tag
    new_version["creationTag"] = dict(tag)
    versions.append(new_version)
    return new_version, new_vid


def _resolve_target_version_raw(
    settings, *, new_version: bool, source_vid: str | None = None
) -> tuple[dict, str | None]:
    """Return (version_raw_dict, new_vid_or_None).

    When new_version is True: deep-copies the source (or active) version, appends it,
    returns the new dict + new id. When False: returns the active version's raw dict
    + None, matching legacy in-place behavior.
    """
    if new_version:
        return _deep_copy_version(settings, source_vid=source_vid)

    active_ver_id = settings.active_version
    if active_ver_id is None:
        version_ids = settings.get_version_ids()
        if not version_ids:
            error("Agent has no versions.")
            raise typer.Exit(1)
        active_ver_id = version_ids[0]
    return settings.get_version_settings(active_ver_id).get_raw(), None


def _activate_version(proj, agent_id: str, new_vid: str) -> None:
    """Flip the active version.

    Uses saved_model API — setting activeVersion in raw is not persisted.
    """
    proj.get_saved_model(agent_id).set_active_version(new_vid)


_LOOP_BLOCK_TYPES = frozenset({"CORE_LOOP", "STANDARD_REACT"})


def _find_loop_block(cfg: dict) -> dict | None:
    """Return the tool-calling loop block, or None if the graph has none.

    Prefers the starting block when it is a loop; otherwise the first loop block.
    """
    blocks = cfg.get("blocks") or []
    start_id = cfg.get("startingBlockId")
    for b in blocks:
        if b.get("id") == start_id and b.get("type") in _LOOP_BLOCK_TYPES:
            return b
    for b in blocks:
        if b.get("type") in _LOOP_BLOCK_TYPES:
            return b
    return None


def _set_structured_agent_llm(ver_raw: dict, llm_id: str) -> bool:
    """Write llm_id into a structured agent's loop block.

    A block-based structured agent (e.g. create-react) holds its model in the
    loop block's llmId, not in a top-level structuredAgentSettings.llmId — DSS
    ignores the latter for these agents, so writing it persists nothing the
    runtime reads. Mirrors how set-prompt targets the loop block. Returns True
    when a loop block was found and written.
    """
    cfg = ver_raw.setdefault("structuredAgentSettings", {})
    loop_block = _find_loop_block(cfg)
    if loop_block is not None:
        loop_block["llmId"] = llm_id
        return True
    cfg["llmId"] = llm_id
    return False
