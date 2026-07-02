"""Regenerate `references/command-index.md` from the CLI's own command tree.

Every group/command with its one-line `--help` description, grouped under a
handful of capability categories for skimming. Source of truth is the same
introspection `--help` uses (`dku_cli.spec.full_index`), so this can't drift
from real CLI behavior — only from being forgotten after a command is added,
which `tests/test_generate_command_index.py` catches by re-rendering and
diffing against the committed file.

Usage: uv run python scripts/generate_command_index.py
"""

from __future__ import annotations

from pathlib import Path

import typer.main

from dku_cli.main import app
from dku_cli.spec import full_index

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dataiku-mcp" / "skills" / "dku-cli" / "references" / "command-index.md"

# Every group must appear here exactly once — the generator errors instead of
# silently dropping a new group into an "Uncategorized" bucket.
CATEGORIES: list[tuple[str, list[str]]] = [
    ("Root Commands", ["root"]),
    (
        "Tabular Flow & Data",
        [
            "dataset",
            "recipe",
            "flow",
            "dq",
            "sql",
            "connection",
            "folder",
            "streaming",
            "meaning",
            "library",
            "job",
            "continuous",
            "analysis",
            "macro",
            "bundle",
        ],
    ),
    (
        "GenAI & Agents",
        [
            "agent",
            "agent-block",
            "agent-hub",
            "agent-review",
            "agent-tool",
            "llm",
            "rag",
            "knowledge",
            "eal",
        ],
    ),
    (
        "Project Ops",
        [
            "project",
            "project-folder",
            "project-deployer",
            "scenario",
            "git",
            "code-env",
            "code-studio",
            "cluster",
            "notebook",
            "api-deployer",
            "api-service",
            "wiki",
            "discussion",
        ],
    ),
    (
        "Analytics & Apps",
        [
            "dashboard",
            "insight",
            "app",
            "app-designer",
            "ml",
            "model",
            "model-comparison",
            "evaluation-store",
        ],
    ),
    ("Semantic Layer", ["semantic-model"]),
    (
        "Extensions & Admin",
        [
            "plugin",
            "webapp",
            "admin",
            "api-key",
            "auth",
            "user",
            "group",
            "config",
            "workspace",
        ],
    ),
    ("Govern", ["govern"]),
]


def _render(index: dict[str, dict]) -> str:
    categorized = {name for _, names in CATEGORIES for name in names}
    missing = set(index) - categorized
    if missing:
        raise SystemExit(
            f"Uncategorized group(s) in CATEGORIES: {sorted(missing)}. "
            "Add each to a category in scripts/generate_command_index.py."
        )
    unknown = categorized - set(index)
    if unknown:
        raise SystemExit(
            f"CATEGORIES references group(s) that no longer exist: {sorted(unknown)}. "
            "Remove them from scripts/generate_command_index.py."
        )

    lines = [
        "# Reference: Command Index",
        "",
        "> Generated from `dku`'s command tree by "
        "`scripts/generate_command_index.py`. Do not edit by hand — change "
        "help text in the CLI source and regenerate.",
        "",
        "Every group and command with its one-line description — read this once per "
        "session when the capability table in `SKILL.md` doesn't have a row, or the "
        "task spans domains you haven't touched yet. Grep it locally instead of "
        "drilling `--help` into each group. Once you have the exact command, jump "
        "straight to `dku <group> <command> --help` for flags.",
        "",
    ]
    for category, group_names in CATEGORIES:
        lines.append(f"## {category}")
        lines.append("")
        for name in group_names:
            node = index[name]
            lines.append(f"### `{name}` — {node['help']}")
            lines.append("")
            for cmd_name, one_liner in node["commands"].items():
                lines.append(f"- `{cmd_name}` — {one_liner}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    root = typer.main.get_command(app)
    index = full_index(root)
    OUTPUT.write_text(_render(index), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
