"""Docs/help hygiene: every backticked `dku ...` snippet must resolve to a
real command in the registered click tree, so stale renames don't rot in
source strings or skill docs.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer.main

from dku_cli.main import app
from dku_cli.spec import full_index

ROOT = Path(__file__).resolve().parents[1]

SNIPPET_RE = re.compile(r"[`']dku((?: [a-z][a-z0-9-]*)+)")

# (file-path-substring, "dku <group> <command>") pairs for deliberate
# wrong-form examples in docs — not stale refs, don't flag them.
ALLOWLIST = {
    ("playbooks/tabular-flow.md", "dku dataset dq"),
    ("commands/flow.py", "dku flow zone"),
}


def _build_command_tree():
    root = typer.main.get_command(app)
    index = full_index(root)
    groups = {name for name in index if name != "root"}
    root_commands = set(index.get("root", {}).get("commands", {}))
    pairs = {
        (group, command)
        for group, node in index.items()
        if group != "root"
        for command in node["commands"]
    }
    return groups, root_commands, pairs


def _iter_snippets(paths):
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in SNIPPET_RE.finditer(text):
            yield path, match.group(1).split()


def _is_allowlisted(path: Path, words: list[str]) -> bool:
    snippet = "dku " + " ".join(words[:2])
    return any(
        file_substring in str(path) and snippet == allowed_snippet
        for file_substring, allowed_snippet in ALLOWLIST
    )


def test_dku_command_refs_resolve():
    groups, root_commands, pairs = _build_command_tree()
    assert len(pairs) > 500

    py_files = sorted((ROOT / "src" / "dku_cli").rglob("*.py"))
    md_files = sorted((ROOT / "dataiku-mcp" / "skills").rglob("*.md"))

    total = 0
    failures: list[tuple[Path, list[str]]] = []
    for path, words in _iter_snippets(py_files + md_files):
        total += 1
        first = words[0]
        if first in root_commands:
            continue
        if first not in groups:
            if not _is_allowlisted(path, words):
                failures.append((path, words))
            continue
        if len(words) == 1:
            continue
        second = words[1]
        if (first, second) not in pairs and not _is_allowlisted(path, words):
            failures.append((path, words))

    assert not failures, "\n".join(f"{p}: dku {' '.join(w)}" for p, w in failures)
    assert total > 0
