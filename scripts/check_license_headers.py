#!/usr/bin/env python3

# Copyright 2026 Dataiku
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

"""Verify that every tracked source file carries the Apache 2.0 preamble.

Checks Python, shell, JavaScript, CSS, and HTML files. Comment syntax differs per
language, so the header is matched against a comment-stripped, whitespace-
collapsed view of the top of each file. Exits non-zero if any file is missing
the preamble.

Usage:
    python3 scripts/check_license_headers.py            # every tracked file
    python3 scripts/check_license_headers.py a.py b.js  # only the given files
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CHECKED_SUFFIXES = frozenset({".py", ".sh", ".js", ".css", ".html"})

# Number of leading lines searched for the preamble. Generous enough to allow a
# shebang, a PEP 723 metadata block, or an HTML doctype ahead of the header.
HEADER_SCAN_LINES = 60

LICENSE_BODY = (
    'Licensed under the Apache License, Version 2.0 (the "License"); '
    "you may not use this file except in compliance with the License. "
    "You may obtain a copy of the License at "
    "http://www.apache.org/licenses/LICENSE-2.0 "
    "Unless required by applicable law or agreed to in writing, software "
    'distributed under the License is distributed on an "AS IS" BASIS, '
    "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. "
    "See the License for the specific language governing permissions and "
    "limitations under the License."
)

# Any single year or year range is accepted so the header does not need a
# yearly sweep across the tree.
PREAMBLE_PATTERN = re.compile(
    r"Copyright \d{4}(?:[-,] ?\d{4})* Dataiku " + re.escape(LICENSE_BODY)
)

# Leading comment markers, stripped line by line before matching.
COMMENT_PREFIX_PATTERN = re.compile(r"^\s*(?:#+|//+|/\*+|\*+/?|<!--+|--+>)\s?")
COMMENT_SUFFIX_PATTERN = re.compile(r"\s*(?:\*+/|--+>)\s*$")


def normalize(text: str) -> str:
    """Strip comment markers from each line and collapse whitespace."""
    stripped = []
    for line in text.splitlines():
        line = COMMENT_PREFIX_PATTERN.sub("", line)
        line = COMMENT_SUFFIX_PATTERN.sub("", line)
        stripped.append(line)
    return re.sub(r"\s+", " ", " ".join(stripped)).strip()


def has_preamble(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    head = "\n".join(text.splitlines()[:HEADER_SCAN_LINES])
    return PREAMBLE_PATTERN.search(normalize(head)) is not None


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [Path(name) for name in output.split("\0") if name]


def main(argv: list[str]) -> int:
    candidates = [Path(arg) for arg in argv] if argv else tracked_files()
    targets = sorted(
        path
        for path in candidates
        if path.suffix in CHECKED_SUFFIXES and path.is_file()
    )

    missing = [path for path in targets if not has_preamble(path)]

    if missing:
        print(
            f"Missing the Apache 2.0 preamble in {len(missing)} of "
            f"{len(targets)} checked file(s):",
            file=sys.stderr,
        )
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nAdd the preamble as a comment at the top of each file, using "
            "that file's comment syntax.",
            file=sys.stderr,
        )
        return 1

    print(f"Apache 2.0 preamble present in all {len(targets)} checked file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
