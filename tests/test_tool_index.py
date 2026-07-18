"""Drift guard for the generated tool index.

`references/tool-index.md` is a rendered view of the live tool registry (see
scripts/generate_tool_index.py). This test re-renders it in memory and diffs
against the committed file: a tool added/removed, or a docstring's first
sentence changed, without regenerating the index fails here — with the regen
command in the message. It never contacts a live DSS instance.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Pin the stdio surface before the generator imports the server (see the same
# guard in scripts/generate_tool_index.py) and make scripts/ importable.
os.environ["DKU_MCP_TRANSPORT"] = "stdio"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_tool_index as gen  # noqa: E402


def test_tool_index_matches_registry():
    committed = gen.OUTPUT.read_text(encoding="utf-8")
    rendered = gen.render_index()
    assert committed == rendered, (
        "references/tool-index.md is stale — a tool or its docstring changed but "
        "the index was not regenerated. Run:\n"
        "    uv run python scripts/generate_tool_index.py"
    )
