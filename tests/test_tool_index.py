"""The committed tool index is an exact rendering of the live registry."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_tool_index as generator  # noqa: E402


def test_tool_index_matches_registry():
    committed = generator.OUTPUT.read_text(encoding="utf-8")

    assert committed == generator.render_index(), (
        "references/tool-index.md is stale; run "
        "`uv run python scripts/generate_tool_index.py`"
    )


def test_every_tool_has_one_known_group_and_a_summary():
    known = {key for key, _ in generator.GROUPS}

    for tool in generator.registry_tools():
        assert generator._domain(tool.module) in known
        assert generator._first_sentence(tool.name, tool.doc)
