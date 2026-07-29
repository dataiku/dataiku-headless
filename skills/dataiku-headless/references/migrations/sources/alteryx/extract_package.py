"""Unzip an Alteryx .yxzp package (path-traversal guarded) and inventory members · in: <package.yxzp> --out PATH → out: JSON {package,target_dir,member_count,members[],workflows[],workflow_paths[]} + files on disk · deps: stdlib (zipfile, pathlib, json, sys, argparse)."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

WORKFLOW_SUFFIXES = (".yxmd", ".yxmc", ".yxwz")


def extract(package: Path, target: Path) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        for member in names:
            destination = (target / member).resolve()
            if not destination.is_relative_to(target_root):
                raise ValueError(f"unsafe archive member path: {member}")
        archive.extractall(target)
        return names


def inventory(package: Path, target: Path) -> dict:
    members = extract(package, target)
    workflows = [m for m in members if m.lower().endswith(WORKFLOW_SUFFIXES)]
    target_root = target.resolve()
    return {
        "package": str(package),
        "target_dir": str(target_root),
        "member_count": len(members),
        "members": members,
        "workflows": workflows,
        "workflow_paths": [str(target_root / workflow) for workflow in workflows],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract and inventory an Alteryx .yxzp package."
    )
    parser.add_argument("package", help="path to the .yxzp package (a zip archive)")
    parser.add_argument(
        "target_dir",
        nargs="?",
        help="directory to extract into (default: <package-stem>_extracted under cwd)",
    )
    parser.add_argument(
        "--out",
        help="JSON output path (default: extract/<package-stem>.json under cwd)",
    )
    args = parser.parse_args()

    package = Path(args.package)
    stem = package.stem or "package"
    target = (
        Path(args.target_dir) if args.target_dir else Path.cwd() / f"{stem}_extracted"
    )
    out_path = Path(args.out) if args.out else Path.cwd() / "extract" / f"{stem}.json"

    try:
        result = inventory(package, target)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")

    wf = result["workflows"]
    wf_digest = ", ".join(wf) if wf else "none"
    print(f"extracted {result['member_count']} members to {result['target_dir']}")
    print(f"{len(wf)} workflow file(s): {wf_digest}")
    print(f"-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
