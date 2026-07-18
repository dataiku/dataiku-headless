"""CI-facing wrapper: the skill tree passes its integrity checker with zero errors.

The real logic lives in scripts/check_skill_links.py (frontmatter integrity,
routing completeness, dead-reference detection). This asserts it returns 0 so
the check runs as part of the normal `pytest` gate, not only the standalone CI
step. Diagnostics print to stderr and surface on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_skill_links  # noqa: E402


def test_skill_tree_has_no_broken_links():
    assert check_skill_links.main() == 0
