"""Integrity check for the dataiku-skills tree.

One skill, one router. Every playbook and reference earns its place by being
reachable from its skill's SKILL.md, and every path-qualified cross-reference
must resolve to a real file. That is the routing contract the supervisor relies
on: an orphaned playbook is a fact with no home (the model never finds it), and
a dead link is a home with no fact (the model follows it into nothing). This
checker fails on either. Run standalone or in CI:

    uv run python scripts/check_skill_links.py

Layout assumed under SKILL_ROOT: one directory per skill, each with a SKILL.md
router at its root and `playbooks/` + `references/` subtrees. Non-markdown assets
are not routed and are ignored.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "dataiku-skills"

# Subtrees whose every .md file must be transitively reachable from SKILL.md.
ROUTED_SUBDIRS = ("playbooks", "references")

# A .md path token: optional ../ hops and directory segments, then filename.md.
# Matches both markdown-link targets `](path.md)` and inline backtick paths.
_MD_TOKEN = re.compile(r"(?:\.\./|[\w.-]+/)*[\w.-]+\.md")


def _within_skill_root(resolved: Path) -> bool:
    """True if a resolved path lives inside the skills root (no ``../`` escape)."""
    try:
        resolved.relative_to(SKILL_ROOT.resolve())
        return True
    except ValueError:
        return False


def _frontmatter_errors(skill_dir: Path, text: str) -> list[str]:
    """SKILL.md must carry `name` + `description`, and name must equal the dir."""
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


def _resolve(
    ref: str, from_file: Path, skill_dir: Path, by_name: dict[str, Path]
) -> Path | None:
    """Resolve a .md reference to a real file, or None if it dangles.

    A **path-qualified** reference (one containing `/`, e.g. `../references/x.md`)
    is a hard link and must resolve *exactly* — either relative to the referring
    file's directory, or relative to the skill root with leading `../` stripped.
    The basename fallback is deliberately NOT tried for these: it would rescue a
    path-qualified typo (`references/objct-model.md`) by matching a same-named file
    elsewhere in the tree, hiding a real dead link.

    A **bare** reference (no `/`, the sibling-filename convention where one file
    names another without spelling out the path) resolves against the referring
    file's directory first, then the unique-basename map.
    """
    if "/" in ref:
        stripped = ref
        while stripped.startswith("../"):
            stripped = stripped[3:]
        for candidate in ((from_file.parent / ref), (skill_dir / stripped)):
            if candidate.is_file():
                resolved = candidate.resolve()
                # A ``../``-laden ref must not climb out of the skill tree. A
                # target outside SKILL_ROOT (e.g. `../../../README.md`) is treated
                # as unresolvable so it fails the dead-reference check rather than
                # silently pointing the supervisor at a file off the routed tree.
                if _within_skill_root(resolved):
                    return resolved
        return None

    candidate = from_file.parent / ref
    if candidate.is_file():
        resolved = candidate.resolve()
        if _within_skill_root(resolved):
            return resolved
    return by_name.get(ref)


def _by_name(md_files: list[Path]) -> tuple[dict[str, Path], list[str]]:
    """Map each unique basename to its file; report any basename claimed twice.

    The bare-filename convention (`_resolve`) relies on a basename identifying
    exactly one file. Two files sharing a basename make every bare reference to
    that name ambiguous, so it is a hard error rather than a last-writer-wins
    overwrite of the lookup map.
    """
    by_name: dict[str, Path] = {}
    seen: dict[str, list[Path]] = {}
    for path in md_files:
        seen.setdefault(path.name, []).append(path)
    errors: list[str] = []
    for name, paths in seen.items():
        by_name[name] = paths[0].resolve()
        if len(paths) > 1:
            joined = ", ".join(str(p) for p in sorted(paths))
            errors.append(f"duplicate basename `{name}` in the skill tree: {joined}")
    return by_name, errors


def _md_refs(path: Path) -> set[str]:
    return set(_MD_TOKEN.findall(path.read_text(encoding="utf-8")))


def _check_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    errors += _frontmatter_errors(skill_dir, skill_md.read_text(encoding="utf-8"))

    md_files = sorted(skill_dir.rglob("*.md"))
    by_name, dup_errors = _by_name(md_files)
    errors += [f"{skill_dir.name}: {msg}" for msg in dup_errors]

    # (c) Dead-reference detection. A *path-qualified* .md reference (one with a
    # directory or ../ component) is a hard link and must resolve. Bare filename
    # tokens are treated as soft references: they overlap with prose (e.g. an
    # artifact the agent writes at runtime, like `runtime_plan.md`), so they
    # are not flagged here — they only feed reachability below.
    for path in md_files:
        for ref in sorted(_md_refs(path)):
            if "/" not in ref:
                continue
            if _resolve(ref, path, skill_dir, by_name) is None:
                errors.append(
                    f"{skill_dir.name}/{path.relative_to(skill_dir)}: "
                    f"dead reference `{ref}`"
                )

    # (b) Routing completeness. BFS from SKILL.md over every resolvable reference
    # (path-qualified and bare alike), then require every routed-subtree .md to
    # be reachable — a playbook/reference nobody links to is orphaned.
    reachable: set[Path] = {skill_md.resolve()}
    queue: deque[Path] = deque([skill_md])
    while queue:
        current = queue.popleft()
        for ref in _md_refs(current):
            target = _resolve(ref, current, skill_dir, by_name)
            if target is not None and target.suffix == ".md" and target not in reachable:
                reachable.add(target)
                queue.append(target)

    for path in md_files:
        rel = path.relative_to(skill_dir)
        if rel.parts and rel.parts[0] in ROUTED_SUBDIRS and path.resolve() not in reachable:
            errors.append(
                f"{skill_dir.name}/{rel}: not reachable from SKILL.md "
                "(orphaned — link it from the router or an already-routed file)"
            )
    return errors


def _skill_dirs() -> list[Path]:
    """Every directory under SKILL_ROOT that holds a SKILL.md router."""
    return sorted(path.parent for path in SKILL_ROOT.rglob("SKILL.md"))


def main() -> int:
    skill_dirs = _skill_dirs()
    if not skill_dirs:
        print(f"no SKILL.md found under {SKILL_ROOT}", file=sys.stderr)
        return 1

    errors: list[str] = []
    total_md = 0
    for skill_dir in skill_dirs:
        errors += _check_skill(skill_dir)
        total_md += len(list(skill_dir.rglob("*.md")))

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        f"skill tree OK: {len(skill_dirs)} skill(s), {total_md} markdown files, "
        "all routed files reachable and all path references resolve"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
