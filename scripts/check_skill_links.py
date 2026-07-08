"""Integrity check for the dku-cli skill tree.

Fails when the skill's routing contract breaks: SKILL.md frontmatter missing,
a playbook/reference file not listed in SKILL.md's tables, or a .md
cross-reference that resolves to nothing. Run standalone or from CI:

    uv run python scripts/check_skill_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "dataiku-mcp" / "skills" / "dku-cli"

MD_REF = re.compile(r"(?:\.\./)*(?:[\w-]+/)*[\w-]+\.md")


def _frontmatter_errors(skill_md: str) -> list[str]:
    errors = []
    match = re.match(r"\A---\n(.*?)\n---\n", skill_md, re.DOTALL)
    if not match:
        return ["SKILL.md: missing YAML frontmatter block"]
    body = match.group(1)
    for field in ("name", "description"):
        if not re.search(rf"^{field}:\s*\S", body, re.MULTILINE):
            errors.append(f"SKILL.md: frontmatter missing `{field}`")
    name = re.search(r"^name:\s*(\S+)", body, re.MULTILINE)
    if name and name.group(1) != SKILL_DIR.name:
        errors.append(
            "SKILL.md: frontmatter name "
            f"`{name.group(1)}` != directory `{SKILL_DIR.name}`"
        )
    return errors


def _routing_errors(skill_md: str) -> list[str]:
    errors = []
    for sub in ("playbooks", "references"):
        for path in sorted((SKILL_DIR / sub).glob("*.md")):
            if f"{sub}/{path.name}" not in skill_md:
                errors.append(f"SKILL.md: does not route to {sub}/{path.name}")
    return errors


def _reference_errors() -> list[str]:
    errors = []
    basenames = {p.name for p in SKILL_DIR.rglob("*.md")}
    for path in sorted(SKILL_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for ref in set(MD_REF.findall(text)):
            candidates = [path.parent / ref, SKILL_DIR / ref.removeprefix("../")]
            if any(c.exists() for c in candidates) or Path(ref).name in basenames:
                continue
            errors.append(f"{path.relative_to(SKILL_DIR)}: dead reference `{ref}`")
    return errors


def main() -> int:
    skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    errors = (
        _frontmatter_errors(skill_md) + _routing_errors(skill_md) + _reference_errors()
    )
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print(f"skill tree OK: {len(list(SKILL_DIR.rglob('*.md')))} files")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
