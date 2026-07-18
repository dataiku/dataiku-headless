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


def test_fenced_code_tool_tokens_are_extracted():
    """A tool name written inside a ``` fence is extracted like a backticked one."""
    text = "before\n```python\nrun_scenario(project_key)\nget_ghost_tool()\n```\nafter"
    tokens = check_skill_tool_names.tool_shaped_tokens(text)
    assert "run_scenario" in tokens  # real tool
    assert "get_ghost_tool" in tokens  # a ghost inside a fence is still caught
    # A single-word / camelCase token inside the fence is not tool-shaped.
    assert "before" not in tokens


def test_prose_ghost_sweep_flags_unbackticked_ghost_but_not_real_tools():
    registry = check_skill_tool_names.registry_tool_names()
    valid = registry | check_skill_tool_names.ALLOWLIST
    prefixes = check_skill_tool_names._registry_prefixes(registry)

    # A real tool named unbackticked in prose is NOT flagged.
    assert (
        check_skill_tool_names.prose_ghost_tokens("use list_datasets to see them", valid, prefixes)
        == set()
    )
    # A verb-prefixed ghost that is no real tool IS flagged.
    ghosts = check_skill_tool_names.prose_ghost_tokens("then call get_webapp_state next", valid, prefixes)
    assert "get_webapp_state" in ghosts
    # A backticked ghost is handled by the code sweep, not the prose sweep.
    assert (
        check_skill_tool_names.prose_ghost_tokens("call `get_webapp_state` now", valid, prefixes)
        == set()
    )


def test_within_skill_root_rejects_escapes():
    root = check_skill_links.SKILL_ROOT.resolve()
    inside = next(root.rglob("SKILL.md")).resolve()
    assert check_skill_links._within_skill_root(inside)
    outside = (root / ".." / ".." / "README.md").resolve()
    assert not check_skill_links._within_skill_root(outside)


def test_resolve_rejects_reference_escaping_skills_root():
    """A ``../../../README.md`` traversal must not resolve outside the skills root."""
    skill_dir = next(check_skill_links.SKILL_ROOT.glob("*"))
    while not (skill_dir / "SKILL.md").is_file():
        skill_dir = next(check_skill_links.SKILL_ROOT.rglob("SKILL.md")).parent
    from_file = skill_dir / "SKILL.md"
    resolved = check_skill_links._resolve("../../../README.md", from_file, skill_dir, {})
    assert resolved is None
