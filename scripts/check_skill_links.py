"""Check frontmatter, local links, and reachability in the skill tree.

Every Markdown playbook and reference must be reachable from ``SKILL.md``.
Path-qualified Markdown references must resolve to a real file, and duplicate
basenames are rejected because bare-filename routing would otherwise be
ambiguous. First-party skill Markdown is trusted, so there is no path-traversal
guard.

Run: ``uv run python scripts/check_skill_links.py``.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "dataiku-skills"
_MD_TOKEN = re.compile(r"(?:\.\./|[\w.-]+/)*[\w.-]+\.md")


def _frontmatter_errors(skill_dir: Path, text: str) -> list[str]:
    """Require a frontmatter name/description and a directory-matching name."""
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return [f"{skill_dir.name}/SKILL.md: missing YAML frontmatter block"]

    body = match.group(1)
    errors: list[str] = []
    for field in ("name", "description"):
        if not re.search(rf"^{field}:\s*\S", body, re.MULTILINE):
            errors.append(f"{skill_dir.name}/SKILL.md: frontmatter missing `{field}`")
    name = re.search(r"^name:\s*(\S+)", body, re.MULTILINE)
    if name and name.group(1) != skill_dir.name:
        errors.append(
            f"{skill_dir.name}/SKILL.md: frontmatter name "
            f"`{name.group(1)}` != directory `{skill_dir.name}`"
        )
    return errors


def _by_name(md_files: list[Path]) -> tuple[dict[str, Path], list[str]]:
    """Build the unique-basename map used by bare Markdown references."""
    seen: dict[str, list[Path]] = {}
    for path in md_files:
        seen.setdefault(path.name, []).append(path)

    by_name: dict[str, Path] = {}
    errors: list[str] = []
    for name, paths in seen.items():
        by_name[name] = paths[0].resolve()
        if len(paths) > 1:
            joined = ", ".join(str(path) for path in sorted(paths))
            errors.append(f"duplicate basename `{name}` in skill tree: {joined}")
    return by_name, errors


def _resolve(
    ref: str, from_file: Path, skill_dir: Path, by_name: dict[str, Path]
) -> Path | None:
    """Resolve one Markdown token without letting qualified typos fall back."""
    if "/" in ref:
        stripped = ref
        while stripped.startswith("../"):
            stripped = stripped[3:]
        for candidate in (from_file.parent / ref, skill_dir / stripped):
            if candidate.is_file():
                return candidate.resolve()
        return None

    sibling = from_file.parent / ref
    if sibling.is_file():
        return sibling.resolve()
    return by_name.get(ref)


def _md_refs(path: Path) -> set[str]:
    """Extract local Markdown filename tokens from one skill document."""
    text = re.sub(r"https?://[^\s)]+", "", path.read_text(encoding="utf-8"))
    return set(_MD_TOKEN.findall(text))


def _check_skill(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir}: missing SKILL.md"]

    errors = _frontmatter_errors(skill_dir, skill_md.read_text(encoding="utf-8"))
    md_files = sorted(skill_dir.rglob("*.md"))
    by_name, duplicate_errors = _by_name(md_files)
    errors.extend(f"{skill_dir.name}: {error}" for error in duplicate_errors)

    for path in md_files:
        for ref in sorted(_md_refs(path)):
            if "/" in ref and _resolve(ref, path, skill_dir, by_name) is None:
                errors.append(
                    f"{skill_dir.name}/{path.relative_to(skill_dir)}: "
                    f"dead reference `{ref}`"
                )

    reachable = {skill_md.resolve()}
    queue: deque[Path] = deque([skill_md])
    while queue:
        current = queue.popleft()
        for ref in _md_refs(current):
            target = _resolve(ref, current, skill_dir, by_name)
            if target and target.suffix == ".md" and target not in reachable:
                reachable.add(target)
                queue.append(target)

    for path in md_files:
        if path.resolve() not in reachable:
            errors.append(
                f"{skill_dir.name}/{path.relative_to(skill_dir)}: not reachable "
                "from SKILL.md"
            )
    return errors


def _skill_dirs() -> list[Path]:
    """Return each directory that declares a skill router."""
    return sorted(path.parent for path in SKILL_ROOT.rglob("SKILL.md"))


def main() -> int:
    """Print diagnostics and return a shell-friendly status code."""
    skill_dirs = _skill_dirs()
    if not skill_dirs:
        print(f"no SKILL.md found under {SKILL_ROOT}", file=sys.stderr)
        return 1

    errors: list[str] = []
    total_md = 0
    for skill_dir in skill_dirs:
        errors.extend(_check_skill(skill_dir))
        total_md += len(list(skill_dir.rglob("*.md")))

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        f"skill tree OK: {len(skill_dirs)} skill(s), {total_md} markdown files, "
        "all files reachable and all qualified links resolve"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
