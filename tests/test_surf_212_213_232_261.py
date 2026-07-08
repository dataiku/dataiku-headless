"""Surface-batch tests for #212 (set-definition --deep-merge), #213 (code-recipe
set-settings round-trip), #232 (stack --columns projection), #261 (multi-role /
multi-output plugin recipe create)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dku_cli.commands.recipe.core import _parse_role_entries
from dku_cli.definition_merge import deep_merge_dicts, merge_params_preserving_siblings
from tests.commands.recipe.helpers import app, runner


# --------------------------------------------------------------------------- #
# #212 — shared definition merge
# --------------------------------------------------------------------------- #
def test_deep_merge_dicts_recurses_and_replaces_scalars():
    base = {"a": {"x": 1, "y": {"deep": True}}, "b": 2}
    patch = {"a": {"y": {"deep": False, "new": 3}}, "c": 4}
    merged = deep_merge_dicts(base, patch)
    assert merged == {
        "a": {"x": 1, "y": {"deep": False, "new": 3}},
        "b": 2,
        "c": 4,
    }
    # base is not mutated
    assert base["a"]["y"] == {"deep": True}


def test_merge_params_preserving_siblings_shallow_keeps_params_siblings():
    raw = {"params": {"envSelection": {"envMode": "USE_BUILTIN_MODE"}, "keep": 1}}
    merge_params_preserving_siblings(
        raw, {"params": {"containerSelection": {"containerMode": "NONE"}}}
    )
    assert raw["params"]["envSelection"] == {"envMode": "USE_BUILTIN_MODE"}
    assert raw["params"]["keep"] == 1
    assert raw["params"]["containerSelection"] == {"containerMode": "NONE"}


def test_merge_params_preserving_siblings_deep_recurses_nested():
    raw = {
        "params": {
            "containerSelection": {"containerMode": "NONE", "containerConf": "c1"},
            "envSelection": {"envMode": "EXPLICIT_ENV", "envName": "e"},
        },
        "tags": ["t"],
    }
    merge_params_preserving_siblings(
        raw,
        {"params": {"containerSelection": {"containerMode": "INHERIT"}}},
        deep=True,
    )
    # Sibling key inside the patched sub-dict survives (shallow would drop it).
    assert raw["params"]["containerSelection"] == {
        "containerMode": "INHERIT",
        "containerConf": "c1",
    }
    assert raw["params"]["envSelection"] == {"envMode": "EXPLICIT_ENV", "envName": "e"}
    assert raw["tags"] == ["t"]


def test_set_definition_accepts_deep_merge_with_definition(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    raw = {
        "type": "python",
        "params": {
            "envSelection": {"envMode": "USE_BUILTIN_MODE"},
            "containerSelection": {"containerMode": "NONE", "containerConf": "c1"},
        },
    }
    settings.get_recipe_raw_definition.return_value = raw

    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "r1",
            "-d",
            '{"params":{"containerSelection":{"containerMode":"INHERIT"}}}',
            "--deep-merge",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "deep-merged" in result.output
    assert raw["params"]["envSelection"] == {"envMode": "USE_BUILTIN_MODE"}
    assert raw["params"]["containerSelection"] == {
        "containerMode": "INHERIT",
        "containerConf": "c1",
    }
    settings.save.assert_called_once()


# --------------------------------------------------------------------------- #
# #213 — code-recipe set-settings round-trip
# --------------------------------------------------------------------------- #
def _code_recipe_settings(patch_client, rtype="python"):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {"type": rtype, "name": "r1"}
    return settings


def test_set_settings_accepts_string_payload_for_code_recipe(patch_client):
    settings = _code_recipe_settings(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "r1",
            "-s",
            '{"payload": "print(\\"v2\\")", "tags": ["x"]}',
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.set_payload.assert_called_once_with('print("v2")')
    # Non-payload keys land on the raw definition.
    assert settings.get_recipe_raw_definition.return_value["tags"] == ["x"]
    settings.save.assert_called_once()


def test_set_settings_rejects_object_payload_for_code_recipe(patch_client):
    settings = _code_recipe_settings(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "r1",
            "-s",
            '{"payload": {"engineType": "DSS"}}',
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "source" in result.output and "set-code" in result.output
    settings.set_payload.assert_not_called()
    settings.save.assert_not_called()


def test_set_settings_still_rejects_string_payload_for_visual_recipe(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {"type": "grouping"}
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "r1",
            "-s",
            '{"payload": "{\\"keys\\": []}"}',
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "must be a JSON object" in result.output


# --------------------------------------------------------------------------- #
# #232 — stack --columns projection
# --------------------------------------------------------------------------- #
def test_create_stack_columns_rejected_with_intersect(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--columns",
            "id",
            "--mode",
            "INTERSECT",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--columns cannot be combined with --mode INTERSECT" in result.output


def test_create_stack_columns_switches_to_custom_mode(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {"virtualInputs": [{"index": 0}, {"index": 1}]}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--columns",
            "id,name",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["mode"] == "CUSTOM"
    assert settings.obj_payload["selectedColumns"] == ["id", "name"]


# --------------------------------------------------------------------------- #
# #261 — role-pair parsing + multi-output plugin recipe create
# --------------------------------------------------------------------------- #
def test_parse_role_entries_bare_and_pairs():
    default, pairs = _parse_role_entries(
        ["main", "decisions=ds_a", "diagnostics=ds_b"], "output"
    )
    assert default == "main"
    assert pairs == [("decisions", "ds_a"), ("diagnostics", "ds_b")]


def test_parse_role_entries_empty():
    assert _parse_role_entries([], "input") == (None, [])


def test_parse_role_entries_rejects_two_bare_roles():
    with pytest.raises(SystemExit):
        _parse_role_entries(["main", "other"], "input")


def test_parse_role_entries_rejects_malformed_pair():
    with pytest.raises(SystemExit):
        _parse_role_entries(["decisions="], "output")
    with pytest.raises(SystemExit):
        _parse_role_entries(["=ds_a"], "output")


def test_create_plugin_recipe_multi_output_roles(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_recipe.return_value = MagicMock()
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "multi",
            "--type",
            "CustomCode_my-recipe",
            "--input-role",
            "main=input_ds",
            "--output-role",
            "decisions=ds_a",
            "--output-role",
            "diagnostics=ds_b",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    recipe_proto = proj.create_recipe.call_args[0][0]
    assert recipe_proto["inputs"]["main"]["items"][0]["ref"] == "input_ds"
    assert recipe_proto["outputs"]["decisions"]["items"][0]["ref"] == "ds_a"
    assert recipe_proto["outputs"]["diagnostics"]["items"][0]["ref"] == "ds_b"


def test_create_plugin_recipe_repeatable_output_ds_with_default_role(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_recipe.return_value = MagicMock()
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "multi",
            "--type",
            "CustomCode_my-recipe",
            "-i",
            "input_ds",
            "--output-ds",
            "ds_a",
            "--output-ds",
            "ds_b",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    recipe_proto = proj.create_recipe.call_args[0][0]
    refs = [it["ref"] for it in recipe_proto["outputs"]["main"]["items"]]
    assert refs == ["ds_a", "ds_b"]


def test_create_non_plugin_rejects_role_pairs_and_multi_output(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "r1",
            "--type",
            "python",
            "-i",
            "a",
            "--output-ds",
            "o1",
            "--output-ds",
            "o2",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "only supported" in result.output and "CustomCode" in result.output
