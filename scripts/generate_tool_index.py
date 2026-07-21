"""Generate the skill tool index from the live FastMCP registry.

The committed index is a derived view of the registered surface: tool name,
display group, and the first sentence of the function docstring. This chain is
stdio-only with one fixed catalog, so a single in-process import of the server
is the whole source of truth — no transport union, no subprocess. Importing the
package registers every tool module; no DSS request is made.

Run: ``uv run python scripts/generate_tool_index.py``.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT / "dataiku-skills" / "dataiku-headless" / "references" / "tool-index.md"
)

# Every registered tool module maps to exactly one display group. An unmapped
# module fails generation so a new domain cannot disappear into a miscellaneous
# bucket.
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
    ("dashboards", "Dashboards"),
    ("insights", "Insights"),
    ("webapps", "WebApps"),
    ("wikis", "Wikis"),
    ("agents", "Agents"),
    ("agent_reviews", "Agent reviews"),
    ("evaluation_stores", "Evaluation stores"),
    ("llms_and_knowledge_banks", "LLMs and knowledge banks"),
    ("machine_learning", "Machine learning"),
    ("semantic_models", "Semantic models"),
    ("object_settings", "Generic object settings"),
    ("instances", "Instances"),
    ("cobuild", "Cobuild"),
    ("project_audit", "Project audit"),
]

_SENTENCE_END = re.compile(r"\.(?:\s|$)")


@dataclass(frozen=True)
class ToolRecord:
    """One registered tool: its name, defining module, and docstring."""

    name: str
    module: str
    doc: str | None


@lru_cache(maxsize=1)
def registry_tools() -> tuple[ToolRecord, ...]:
    """Return every registered tool from one in-process server import."""
    import asyncio

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import dataiku_mcp

    tools = asyncio.run(dataiku_mcp.mcp.list_tools())
    records: list[ToolRecord] = []
    seen: set[str] = set()
    for tool in sorted(tools, key=lambda item: item.name):
        if tool.name in seen:
            raise SystemExit(f"registry registered duplicate tool name `{tool.name}`")
        seen.add(tool.name)
        records.append(ToolRecord(tool.name, tool.fn.__module__, tool.fn.__doc__))
    if not records:
        raise SystemExit("registry returned an empty tool set")
    return tuple(records)


def _domain(module: str) -> str:
    """Collapse a tool module onto its first package below ``tools``."""
    parts = module.split(".")
    try:
        return parts[parts.index("tools") + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"tool function has unexpected module `{module}`") from exc


def _first_sentence(name: str, doc: str | None) -> str:
    """Return the first sentence of the first docstring paragraph."""
    if not doc or not doc.strip():
        raise SystemExit(
            f"tool `{name}` has no docstring; add one before regenerating the index"
        )
    paragraph = " ".join(doc.strip().split("\n\n", 1)[0].split())
    match = _SENTENCE_END.search(paragraph)
    return paragraph[: match.start() + 1] if match else paragraph


def _grouped_tools() -> dict[str, list[ToolRecord]]:
    known = {key for key, _ in GROUPS}
    grouped: dict[str, list[ToolRecord]] = {key: [] for key in known}
    for tool in registry_tools():
        domain = _domain(tool.module)
        if domain not in known:
            raise SystemExit(
                f"tool `{tool.name}` is in unmapped domain `{domain}` "
                f"({tool.module}); add the domain to GROUPS"
            )
        grouped[domain].append(tool)
    empty = [key for key, _ in GROUPS if not grouped[key]]
    if empty:
        raise SystemExit(f"tool-index groups have no registered tools: {empty}")
    return grouped


def render_index() -> str:
    """Render deterministic Markdown from the current registry."""
    grouped = _grouped_tools()
    tools = registry_tools()
    cobuild = sum(_domain(tool.module) == "cobuild" for tool in tools)
    total = len(tools)
    non_cobuild = total - cobuild

    lines = [
        "# Reference: Tool index",
        "",
        "> Generated from the live FastMCP registry by",
        "> `scripts/generate_tool_index.py`. Do not edit by hand. Change the tool",
        "> docstring or the registered surface, then run",
        "> `uv run python scripts/generate_tool_index.py`.",
        "",
        f"The server registers {total} tools: {non_cobuild} non-Cobuild and "
        f"{cobuild} Cobuild.",
        "",
        "Use this index to find a capability. Get parameters, defaults, enums, and "
        "the current input schema from the live tool schema, not this summary.",
        "",
    ]
    for key, title in GROUPS:
        lines.extend((f"## {title}", ""))
        for tool in sorted(grouped[key], key=lambda item: item.name):
            lines.append(f"- `{tool.name}` — {_first_sentence(tool.name, tool.doc)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """Write the generated index to its canonical path."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_index(), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
