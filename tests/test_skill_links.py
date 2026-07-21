"""CI-facing tests for the skill file and tool-name integrity scripts."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_skill_links  # noqa: E402
import check_skill_tool_names  # noqa: E402


def test_skill_tree_has_no_broken_or_unrouted_files():
    assert check_skill_links.main() == 0


def test_skill_tree_names_only_registered_tools():
    assert check_skill_tool_names.main() == 0


def test_every_registered_name_has_the_checked_tool_shape():
    registry = check_skill_tool_names.registry_tool_names()
    namespace = check_skill_tool_names.verb_namespace(registry)

    assert len(registry) >= 50
    for name in registry:
        assert check_skill_tool_names.tool_shaped_tokens(f"`{name}`", namespace) == {
            name
        }


def test_pruned_tool_reference_is_flagged():
    registry = check_skill_tool_names.registry_tool_names()
    namespace = check_skill_tool_names.verb_namespace(registry)
    valid = registry | check_skill_tool_names.ALLOWLIST

    # A pruned reader named in backticks (call form or bare) is caught even
    # though the index generator renders only what is registered.
    for ghost in ("get_wiki_article(project_key, object_id)", "get_dashboard_settings"):
        tokens = check_skill_tool_names.tool_shaped_tokens(
            f"Inspect it with `{ghost}`.", namespace
        )
        name = ghost.split("(", 1)[0]
        assert name in tokens
        assert name not in valid


def test_non_tool_field_names_are_out_of_scope():
    registry = check_skill_tool_names.registry_tool_names()
    namespace = check_skill_tool_names.verb_namespace(registry)

    # Field, value, and recipe-family names never share a tool verb, so they
    # are ignored without an allowlist entry each.
    assert check_skill_tool_names.tool_shaped_tokens(
        "`system_prompt` `sql_query` `knowledge_bank`", namespace
    ) == set()


def test_fenced_ghost_call_is_flagged():
    registry = check_skill_tool_names.registry_tool_names()
    namespace = check_skill_tool_names.verb_namespace(registry)

    text = "before\n```python\nget_ghost_tool()\nrun_scenario(project_key)\n```\nafter"
    tokens = check_skill_tool_names.tool_shaped_tokens(text, namespace)

    assert {"get_ghost_tool", "run_scenario"} <= tokens
