"""CI-facing wrapper: the skill tree passes its integrity checkers with zero errors.

The real logic lives in two scripts run as part of the normal `pytest` gate, not
only the standalone CI step:

* ``scripts/check_skill_links.py`` — frontmatter integrity, routing completeness,
  dead *file*-reference detection.
* ``scripts/check_skill_tool_names.py`` — every backticked, tool-shaped token in
  the skill markdown resolves to a real registered tool (or the explicit non-tool
  allowlist), so a reference to a pruned/ghost tool fails the build.

Diagnostics print to stderr and surface on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_skill_links  # noqa: E402
import check_skill_tool_names  # noqa: E402


def test_skill_tree_has_no_broken_links():
    assert check_skill_links.main() == 0


def test_skill_tree_names_only_real_tools():
    assert check_skill_tool_names.main() == 0


def test_every_registered_tool_name_validates():
    """All real tool names are tool-shaped and accepted — no false negatives."""
    registry = check_skill_tool_names.registry_tool_names()
    valid = registry | check_skill_tool_names.ALLOWLIST
    assert len(registry) >= 58, registry
    for name in registry:
        assert check_skill_tool_names.tool_shaped_tokens(f"`{name}`") == {name}
        assert name in valid


def test_a_reintroduced_ghost_tool_fails():
    """A pruned tool name, if it reappears in prose, is extracted and rejected."""
    registry = check_skill_tool_names.registry_tool_names()
    valid = registry | check_skill_tool_names.ALLOWLIST
    for ghost in ("get_ml_model_details", "search_project_library", "get_webapp_state"):
        tokens = check_skill_tool_names.tool_shaped_tokens(
            f"Read the model with `{ghost}(project_key, id)` first."
        )
        assert ghost in tokens
        assert ghost not in valid
