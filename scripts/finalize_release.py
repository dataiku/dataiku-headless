#!/usr/bin/env python3

# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Update versions and release notes on the final feature/fix branch, without publishing."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_release import release_notes, tomllib, validate, validate_target_branch


def finalize(root: Path, release_branch: str) -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    def run(*args: str) -> None:
        subprocess.run(args, cwd=root, check=True)

    # Validate input before using it in refs, and preserve unrelated local work.
    if not re.fullmatch(r"release/[0-9]+\.[0-9]+\.[0-9]+", release_branch):
        raise ValueError("Expected release/X.Y.Z")
    branch = git("branch", "--show-current")
    if not branch or branch == "main" or branch.startswith("release/"):
        raise ValueError(
            "Run on the final feature/fix branch, not main or a release branch"
        )
    if git("status", "--porcelain"):
        raise ValueError(
            "Commit your changes first; finalization requires a clean worktree"
        )
    run("git", "fetch", "origin", "--tags")
    baseline = tomllib.loads(git("show", "origin/main:pyproject.toml"))["project"][
        "version"
    ]
    target = validate_target_branch(release_branch, baseline)
    current = validate(root)
    if current not in {baseline, target}:
        raise ValueError("Working version must match main or the target release")
    for ref in ("origin/main", f"origin/{release_branch}", f"refs/tags/v{baseline}"):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", ref, "HEAD"], cwd=root
        ).returncode:
            raise ValueError(f"Bring {ref} into this branch before finalizing")
    for tag in (f"v{target}", f"dataiku-headless--v{target}"):
        if (
            subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{tag}"], cwd=root
            ).returncode
            == 0
        ):
            raise ValueError(f"Target already has a published tag: {tag}")
    run("uv", "lock", "--check")
    run("uv", "lock", "--script", "runtime/run_mcp.py", "--check")
    original_changelog = (root / "CHANGELOG.md").read_text()
    # Generate only the unpublished section; retain all existing released notes.
    with TemporaryDirectory(prefix="headless-release-") as temporary:
        notes_root = Path(temporary)
        run(
            sys.executable,
            "-m",
            "commitizen",
            "changelog",
            "--start-rev",
            f"v{baseline}",
            "--unreleased-version",
            f"v{target}",
            "--file-name",
            str(notes_root / "CHANGELOG.md"),
        )
        notes = release_notes(notes_root, target)
    if current != target:
        run(sys.executable, "-m", "commitizen", "bump", target, "--version-files-only")
    changelog = root / "CHANGELOG.md"
    sections = re.split(r"(?m)(?=^## )", original_changelog)
    preamble = sections.pop(0) if not sections[0].startswith("## ") else ""
    sections = [
        section
        for section in sections
        if not re.match(rf"^## v{re.escape(target)} \(", section)
    ]
    changelog.write_text(preamble + notes + "\n" + "".join(sections))
    run("uv", "lock")
    run("uv", "lock", "--check")
    if validate(root) != target:
        raise ValueError("Version update did not match the release branch")
    release_notes(root, target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_branch", help="Target release/X.Y.Z branch")
    args = parser.parse_args()
    try:
        version = finalize(Path.cwd(), args.release_branch)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Finalization failed: {error}\n")
    print(
        f"Finalized {version}. Review git diff, commit and push these changes to your final feature/fix PR."
    )
