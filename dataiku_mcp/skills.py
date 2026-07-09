"""Locate and export the bundled Dataiku agent skills.

The skill files are prompt-based Markdown documents read off disk by an agent
harness (Claude Code, Codex, or a custom agent). When installed from a wheel
they live under ``dataiku_mcp/skills``; when running from a source checkout they
live at the repo-root ``dataiku-skills`` directory. ``skills_dir`` resolves
whichever is present so callers do not have to care which layout they are in.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# Installed-wheel location of the skills (force-included by hatchling), with a
# source-checkout fallback to repo-root ``dataiku-skills``.
_PACKAGED_SKILLS = _HERE / "skills"
_REPO_SKILLS = _HERE.parent / "dataiku-skills"


def skills_dir() -> Path:
    """Return the directory containing the bundled skill files."""
    if _PACKAGED_SKILLS.is_dir():
        return _PACKAGED_SKILLS
    if _REPO_SKILLS.is_dir():
        return _REPO_SKILLS
    raise FileNotFoundError(
        f"Bundled skills not found. Looked in {_PACKAGED_SKILLS} and {_REPO_SKILLS}."
    )


def _doc(name: str) -> Path:
    """Return the path to a bundled top-level doc (e.g. ``AGENTS.md``).

    Installed wheels carry it under ``dataiku_mcp/<name>``; source checkouts
    keep it at the repo root.
    """
    packaged = _HERE / name
    repo = _HERE.parent / name
    if packaged.is_file():
        return packaged
    if repo.is_file():
        return repo
    raise FileNotFoundError(f"Bundled {name} not found. Looked in {packaged} and {repo}.")


def agents_md() -> Path:
    """Return the path to the bundled ``AGENTS.md`` operating doc."""
    return _doc("AGENTS.md")


def claude_md() -> Path:
    """Return the path to the bundled ``CLAUDE.md`` operating doc."""
    return _doc("CLAUDE.md")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: print the skills location or export it to disk."""
    parser = argparse.ArgumentParser(
        prog="dataiku-headless-skills",
        description="Locate or export the bundled Dataiku agent skills.",
    )
    parser.add_argument(
        "--export",
        metavar="DEST",
        help="Copy the bundled skills into DEST/dataiku-skills and AGENTS.md into DEST/AGENTS.md.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing DEST/dataiku-skills and DEST/AGENTS.md.",
    )
    args = parser.parse_args(argv)

    src = skills_dir()

    if args.export:
        dest_root = Path(args.export).expanduser().resolve()
        dest = dest_root / "dataiku-skills"
        if dest.exists():
            if not args.force:
                print(
                    f"Refusing to overwrite existing {dest} (use --force).",
                    file=sys.stderr,
                )
                return 1
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"Exported skills to {dest}")

        # Drop the operating docs beside the exported skills, mirroring the repo layout.
        for name, src_doc in (("AGENTS.md", agents_md()), ("CLAUDE.md", claude_md())):
            doc_dest = dest_root / name
            if doc_dest.exists() and not args.force:
                print(
                    f"Skipping {name}: {doc_dest} exists (use --force).",
                    file=sys.stderr,
                )
                continue
            shutil.copy2(src_doc, doc_dest)
            print(f"Exported {name} to {doc_dest}")
        return 0

    # No --export: print the location of the bundled skills.
    print(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
