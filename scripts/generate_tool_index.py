"""Regenerate `references/tool-index.md` from the live FastMCP tool registry.

One fact, one home: a tool's purpose is stated once, in its docstring. This
index is a *derived* view — every line is a tool name plus the first sentence of
that docstring, grouped by domain — so it can never contradict the running
server, only fall behind it when a docstring changes and nobody regenerates.
That staleness is caught mechanically by `tests/test_tool_index.py`, which
re-renders in memory and diffs against the committed file.

The index reflects the **stdio** transport (the default). Under
`streamable-http` the registry swaps `create_upload_dataset` for
`create_upload_dataset_from_rows` and drops the instance-switching tools; this
file always shows the stdio surface.

Usage: uv run python scripts/generate_tool_index.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Force the stdio surface *before* importing the server. Transport gating runs
# at import time in dataiku_mcp/__init__.py, and its load_dotenv() will not
# override an already-set variable — so a developer's local streamable-http
# default can never leak into the committed index. Dummy credentials keep the
# import self-contained; no tool is ever invoked here, only introspected.
os.environ["DKU_MCP_TRANSPORT"] = "stdio"
os.environ.setdefault("DKU_DSS_URL", "http://tool-index-generation.invalid")
os.environ.setdefault("DKU_API_KEY", "generation-only-unused")

import asyncio  # noqa: E402

import dataiku_mcp  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT / "dataiku-skills" / "dataiku-headless" / "references" / "tool-index.md"
)

# Every tool module maps to exactly one group here, in display order. The
# generator raises instead of dropping an unmapped module into an
# "Uncategorized" bucket (total categorization) — adding a new tool domain
# forces a deliberate edit to this list, which is the whole point.
GROUPS: list[tuple[str, str]] = [
    ("projects", "Projects"),
    ("datasets", "Datasets"),
    ("recipes", "Recipes"),
    ("flow", "Flow"),
    ("connections", "Connections"),
    ("scenarios", "Scenarios"),
    ("jobs", "Jobs"),
    ("managed_folders", "Managed folders"),
    ("code_environments", "Code environments"),
    ("data_collections", "Data collections"),
    ("cross_project_sharing", "Cross-project sharing"),
    ("project_libraries", "Project libraries"),
    ("data_quality", "Data quality"),
    ("agents", "Agents"),
    ("llms_and_knowledge_banks", "LLMs and knowledge banks"),
    ("machine_learning", "Machine learning"),
    ("instances", "Instances"),
    ("cobuild", "Cobuild"),
    ("project_audit", "Project audit"),
]

_SENTENCE_END = re.compile(r"\.(?:\s|$)")


def _domain(module: str) -> str:
    """Map a tool's module to its group key.

    `dataiku_mcp.tools.projects` -> `projects`;
    `dataiku_mcp.tools.machine_learning.analyses` -> `machine_learning`
    (submodules collapse onto their package so a domain stays one group).
    """
    parts = module.split(".")
    return parts[parts.index("tools") + 1]


def _first_sentence(name: str, doc: str | None) -> str:
    """First sentence of the first paragraph of a tool's docstring.

    Raises if the tool has no docstring — the index needs one line per tool, and
    a missing docstring is a real defect, not something to paper over.
    """
    if not doc or not doc.strip():
        raise SystemExit(
            f"Tool `{name}` has no docstring — the tool-index needs one sentence "
            "per tool. Add a docstring to the tool and regenerate."
        )
    paragraph = " ".join(doc.strip().split("\n\n", 1)[0].split())
    match = _SENTENCE_END.search(paragraph)
    return paragraph[: match.start() + 1] if match else paragraph


def _grouped_tools() -> dict[str, list[tuple[str, str]]]:
    """Registry tools bucketed by domain: {group_key: [(name, sentence), ...]}."""
    tools = asyncio.run(dataiku_mcp.mcp.list_tools())
    known = {key for key, _ in GROUPS}
    grouped: dict[str, list[tuple[str, str]]] = {key: [] for key in known}
    for tool in tools:
        fn = tool.fn
        domain = _domain(fn.__module__)
        if domain not in known:
            raise SystemExit(
                f"Tool `{tool.name}` is in unmapped domain `{domain}` "
                f"(module {fn.__module__}). Add `{domain}` to GROUPS in "
                "scripts/generate_tool_index.py."
            )
        grouped[domain].append((tool.name, _first_sentence(tool.name, fn.__doc__)))
    return grouped


def render_index() -> str:
    """Render the full tool-index markdown from the live registry."""
    grouped = _grouped_tools()
    empty = [key for key, _ in GROUPS if not grouped[key]]
    if empty:
        raise SystemExit(
            f"Group(s) with no tools under stdio: {empty}. Remove them from "
            "GROUPS in scripts/generate_tool_index.py, or investigate the "
            "surface — a domain that lost all its tools is probably a mistake."
        )
    total = sum(len(entries) for entries in grouped.values())

    lines = [
        "# Reference: Tool Index",
        "",
        "> Generated from the live FastMCP registry by "
        "`scripts/generate_tool_index.py`. Do not edit by hand — change the tool "
        "docstring and regenerate: "
        "`uv run python scripts/generate_tool_index.py`.",
        "",
        f"Every tool the headless supervisor exposes ({total} under the default "
        "**stdio** transport), grouped by domain, each with the first sentence of "
        "its docstring. Skim this when the capability you need isn't obvious from "
        "a playbook; then get exact parameters, defaults, and enums from the tool "
        "schema — never from this list.",
        "",
        "Under the `streamable-http` transport the surface differs: the registry "
        "swaps `create_upload_dataset` for `create_upload_dataset_from_rows` and "
        "drops the instance-switching tools (`switch_instance`, `list_instances`). "
        "This file reflects the stdio surface.",
        "",
    ]
    for key, title in GROUPS:
        lines.append(f"## {title}")
        lines.append("")
        for name, sentence in sorted(grouped[key]):
            lines.append(f"- `{name}` — {sentence}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUTPUT.write_text(render_index(), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
