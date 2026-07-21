"""Verify backticked tool names in the skill resolve to registered tools.

The skill routes agents to real MCP tools by naming them in backticks and code
fences. A pruned or renamed reader that survives in skill prose is a dead route
the tool-index generator cannot catch. This checker extracts backticked and
fenced identifiers that sit in the server's tool-verb namespace (``get_*``,
``list_*``, ``run_*``, …) and requires each to be a registered tool or one of a
small allowlist of genuine non-tool names.

Restricting to the tool-verb namespace keeps the allowlist minimal: field,
value, recipe-family, and example identifiers that never share a tool verb are
simply out of scope instead of needing an entry each.

Run: ``uv run python scripts/check_skill_tool_names.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import generate_tool_index


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "dataiku-skills"
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_CALL = re.compile(r"^([a-z][a-z0-9_]+)\s*\(")
_IDENT = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MIN_REGISTRY = 50

# Genuine non-tool names that sit in the tool-verb namespace (a field or value
# that legitimately collides with a tool verb). Keep this as small as the skill
# honestly requires — `run_id` is a scenario/job field, not a `run_*` tool.
ALLOWLIST: frozenset[str] = frozenset({"run_id"})


def registry_tool_names() -> set[str]:
    """Return the live registered tool names, refusing a broken import."""
    names = {tool.name for tool in generate_tool_index.registry_tools()}
    if len(names) < _MIN_REGISTRY:
        raise SystemExit(
            f"live registry returned only {len(names)} tools; refusing to "
            "validate against a likely broken import"
        )
    return names


def verb_namespace(registry: set[str]) -> frozenset[str]:
    """Return the first-segment verbs used by registered tools."""
    return frozenset(name.split("_", 1)[0] for name in registry)


def tool_shaped_tokens(text: str, namespace: frozenset[str]) -> set[str]:
    """Backticked/fenced identifiers that sit in the tool-verb namespace."""
    found: set[str] = set()
    outside_fences = _FENCE.sub("\n", text)
    for span in _INLINE_CODE.findall(outside_fences):
        token = span.strip()
        call = _CALL.match(token)
        if call:
            token = call.group(1)
        if _IDENT.fullmatch(token):
            found.add(token)
    for block in _FENCE.findall(text):
        found.update(word for word in _WORD.findall(block) if _IDENT.fullmatch(word))
    return {token for token in found if token.split("_", 1)[0] in namespace}


def check() -> tuple[list[str], int, int]:
    """Return diagnostics, token count, and registry size."""
    registry = registry_tool_names()
    valid = registry | ALLOWLIST
    namespace = verb_namespace(registry)
    errors: list[str] = []
    checked = 0

    for path in sorted(SKILL_ROOT.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        tokens = tool_shaped_tokens(text, namespace)
        checked += len(tokens)
        rel = path.relative_to(SKILL_ROOT)
        for token in sorted(tokens - valid):
            errors.append(
                f"{rel}: `{token}` is in the tool-verb namespace but is not a "
                "registered tool. Backtick a real tool, add a genuine non-tool "
                "name to ALLOWLIST, or remove the dead route."
            )
    return errors, checked, len(registry)


def main() -> int:
    """Print diagnostics and return a shell-friendly status code."""
    if not SKILL_ROOT.is_dir():
        print(f"no skill tree under {SKILL_ROOT}", file=sys.stderr)
        return 1

    errors, checked, registry_size = check()
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        f"skill tool names OK: {checked} tool-shaped token(s) checked against "
        f"{registry_size} registered tools"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
