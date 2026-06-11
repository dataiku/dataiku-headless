"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock
from tests.commands.recipe.helpers import app, runner
from tests.commands.recipe.helpers import setup_prepare_mock as _setup_prepare_mock


# ── Plugin recipe tests ────────────────────────────────────────────


def test_recipe_create_plugin_recipe(patch_client):
    """Plugin recipes (CustomCode_*) use DSSRecipeCreator in raw mode."""
    proj = patch_client.get_project("PROJ1")
    # project.create_recipe is the low-level method called by DSSRecipeCreator.build()
    recipe_handle = MagicMock()
    proj.create_recipe.return_value = recipe_handle

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_plugin_step",
            "--type",
            "CustomCode_my-recipe",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output

    # DSSRecipeCreator.build() calls project.create_recipe(recipe_proto, creation_settings)
    proj.create_recipe.assert_called_once()
    call_args = proj.create_recipe.call_args
    recipe_proto = call_args[0][0]
    creation_settings = call_args[0][1]

    assert recipe_proto["type"] == "CustomCode_my-recipe"
    assert recipe_proto["name"] == "my_plugin_step"
    assert "main" in recipe_proto["inputs"]
    assert recipe_proto["inputs"]["main"]["items"][0]["ref"] == "input_ds"
    assert "main" in recipe_proto["outputs"]
    assert recipe_proto["outputs"]["main"]["items"][0]["ref"] == "output_ds"
    assert creation_settings["rawCreation"] is True


def test_recipe_create_plugin_recipe_with_params(patch_client, tmp_path):
    """Plugin recipes accept --params for initial configuration."""
    proj = patch_client.get_project("PROJ1")
    recipe_handle = MagicMock()
    proj.create_recipe.return_value = recipe_handle

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_plugin_step",
            "--type",
            "CustomCode_my-recipe",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--params",
            '{"mode": "advanced", "threshold": 0.5}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    call_args = proj.create_recipe.call_args
    recipe_proto = call_args[0][0]
    creation_settings = call_args[0][1]
    assert creation_settings["rawCreation"] is True
    # Config lands in params.customConfig (where the plugin reads it), not the
    # payload, with the required containerSelection — otherwise the recipe NPEs
    # at run time.
    assert recipe_proto["params"]["customConfig"] == {
        "mode": "advanced",
        "threshold": 0.5,
    }
    assert recipe_proto["params"]["containerSelection"] == {"containerMode": "INHERIT"}
    # Config must NOT be written to the payload.
    assert "rawPayload" not in creation_settings


def test_recipe_create_plugin_recipe_params_from_file(patch_client, tmp_path):
    """Plugin recipe --params accepts @file.json."""
    proj = patch_client.get_project("PROJ1")
    proj.create_recipe.return_value = MagicMock()

    config_file = tmp_path / "config.json"
    config_file.write_text('{"key": "value"}')

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "CustomCode_plug_rec",
            "--input",
            "in_ds",
            "--output-ds",
            "out_ds",
            "--params",
            f"@{config_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe_proto = proj.create_recipe.call_args[0][0]
    assert recipe_proto["params"]["customConfig"] == {"key": "value"}
    assert recipe_proto["params"]["containerSelection"] == {"containerMode": "INHERIT"}


def test_recipe_create_plugin_recipe_invalid_params(patch_client):
    """Plugin recipe --params with invalid JSON shows helpful error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "CustomCode_plug_rec",
            "--input",
            "in_ds",
            "--output-ds",
            "out_ds",
            "--params",
            "not json",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output


def test_recipe_create_plugin_recipe_custom_roles(patch_client):
    """Plugin recipes support --input-role and --output-role."""
    proj = patch_client.get_project("PROJ1")
    proj.create_recipe.return_value = MagicMock()

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "CustomCode_plug_rec",
            "--input",
            "in_ds",
            "--output-ds",
            "out_ds",
            "--input-role",
            "documents",
            "--output-role",
            "results",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe_proto = proj.create_recipe.call_args[0][0]
    assert "documents" in recipe_proto["inputs"]
    assert "results" in recipe_proto["outputs"]


def test_recipe_create_plugin_recipe_output_folder(patch_client):
    """--output-folder wires an existing managed folder (by name) as the output.

    The folder name resolves to its ID and that ID is the recipe output ref.
    """
    proj = patch_client.get_project("PROJ1")
    proj.create_recipe.return_value = MagicMock()

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "CustomCode_plug_rec",
            "--input",
            "in_ds",
            "--output-folder",
            "Data Folder",
            "--output-role",
            "output_folder",
            "--params",
            '{"mode": "x"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    recipe_proto = proj.create_recipe.call_args[0][0]
    # Folder name "Data Folder" resolves to id "folder1" (conftest).
    refs = [
        item["ref"]
        for role in recipe_proto["outputs"].values()
        for item in role["items"]
    ]
    assert refs == ["folder1"]
    assert recipe_proto["params"]["customConfig"] == {"mode": "x"}


def test_recipe_create_output_ds_and_folder_mutually_exclusive(patch_client):
    """Passing both --output-ds and --output-folder is rejected."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "CustomCode_plug_rec",
            "--input",
            "in_ds",
            "--output-ds",
            "out_ds",
            "--output-folder",
            "Data Folder",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "only one of --output-ds and --output-folder" in result.output.lower()


def test_recipe_create_requires_an_output(patch_client):
    """Omitting both --output-ds and --output-folder is rejected with guidance."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "python",
            "--input",
            "in_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "No output specified" in result.output


def test_recipe_run_folder_output_builds_as_managed_folder(patch_client):
    """A recipe whose output is a managed folder builds with object_type
    MANAGED_FOLDER, not the default DATASET (which would error)."""
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe("recipe1")
    recipe.get_settings().get_flat_output_refs.return_value = ["folder1"]

    result = runner.invoke(
        app,
        ["recipe", "run", "recipe1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    builder = proj.new_job.return_value
    builder.with_output.assert_called_once_with("folder1", object_type="MANAGED_FOLDER")


def test_recipe_create_unknown_type_error(patch_client):
    """Unknown non-plugin recipe type gives helpful error."""
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.return_value = None

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_step",
            "--type",
            "nonexistent",
            "--input",
            "in_ds",
            "--output-ds",
            "out_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown recipe type" in result.output
    assert "CustomCode_" in result.output


# ── get-settings / set-settings ──────────────────────────────────────


def test_recipe_get_settings_json(patch_client):
    """get-settings returns full settings including payload."""
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "recipe",
            "get-settings",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "type" in parsed  # From raw definition
    assert "name" in parsed


def test_recipe_get_settings_python_recipe_with_code(patch_client):
    """get-settings on a Python recipe must NOT crash on obj_payload JSON
    parsing — it must read the string payload directly, same as get-definition."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    # Simulate a Python recipe with code set
    settings.get_recipe_raw_definition.return_value = {
        "type": "python",
        "name": "my_py",
    }
    settings._str_payload = "import dataiku\nprint('hello')"
    # obj_payload would blow up on this — our code must not call it
    type(settings).obj_payload = property(
        lambda self: (_ for _ in ()).throw(ValueError("JSON decode"))
    )

    result = runner.invoke(
        app,
        ["--format", "json", "recipe", "get-settings", "my_py", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["type"] == "python"
    assert parsed["payload"] == "import dataiku\nprint('hello')"

    # Restore the mock for subsequent tests
    del type(settings).obj_payload


def test_recipe_get_settings_sql_query_recipe_with_code(patch_client):
    """Same fix must apply to sql_query / r / shell / spark_sql_query / etc."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "sql_query",
        "name": "extract",
    }
    settings._str_payload = "SELECT id, name FROM t WHERE active = 1"
    type(settings).obj_payload = property(
        lambda self: (_ for _ in ()).throw(ValueError("JSON decode"))
    )

    result = runner.invoke(
        app,
        ["--format", "json", "recipe", "get-settings", "extract", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["type"] == "sql_query"
    assert parsed["payload"] == "SELECT id, name FROM t WHERE active = 1"

    del type(settings).obj_payload


def test_recipe_get_settings_visual_payload_always_dict(patch_client):
    """For visual recipes, payload must always be a parsed dict — never a
    JSON-encoded string. Regression for AYX028 where some visual recipes
    returned payload as a string and others as a dict."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "join",
        "name": "j1",
    }
    # Simulate the failure mode: obj_payload returns a JSON string (some
    # dataikuapi paths do this for stack/group/etc. depending on engine).
    type(settings).obj_payload = property(
        lambda self: '{"virtualInputs":[{"index":0}]}'
    )

    result = runner.invoke(
        app, ["--format", "json", "recipe", "get-settings", "j1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed["payload"], dict), (
        f"payload must be dict, got {type(parsed['payload']).__name__}"
    )
    assert parsed["payload"]["virtualInputs"] == [{"index": 0}]

    del type(settings).obj_payload


def test_recipe_get_settings_visual_payload_dict_passthrough(patch_client):
    """When obj_payload is already a dict, it passes through unchanged."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "grouping",
        "name": "g1",
    }
    type(settings).obj_payload = property(
        lambda self: {"keys": [{"column": "country"}], "values": []}
    )

    result = runner.invoke(
        app, ["--format", "json", "recipe", "get-settings", "g1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed["payload"], dict)
    assert parsed["payload"]["keys"] == [{"column": "country"}]

    del type(settings).obj_payload


def test_recipe_get_settings_visual_payload_falls_back_to_raw_params(patch_client):
    """When obj_payload raises, the raw_params['payload'] fallback parses
    a JSON string into a dict."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "vstack",
        "name": "s1",
    }
    type(settings).obj_payload = property(
        lambda self: (_ for _ in ()).throw(AttributeError("no obj_payload"))
    )
    settings.raw_params = {"payload": '{"mode":"UNION","virtualInputs":[]}'}

    result = runner.invoke(
        app, ["--format", "json", "recipe", "get-settings", "s1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed["payload"], dict)
    assert parsed["payload"]["mode"] == "UNION"

    del type(settings).obj_payload


def test_recipe_get_settings_visual_empty_payload_returns_empty_dict(patch_client):
    """When no payload is available at all, return an empty dict (not None,
    not missing) so consumers can rely on the type."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "shaker",
        "name": "p1",
    }
    type(settings).obj_payload = property(lambda self: None)
    settings.raw_params = {}

    result = runner.invoke(
        app, ["--format", "json", "recipe", "get-settings", "p1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["payload"] == {}

    del type(settings).obj_payload


def test_recipe_set_settings_updates_definition(patch_client):
    """set-settings updates raw definition keys."""
    settings_json = json.dumps({"engineType": "DSS"})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "recipe1",
            "--settings",
            settings_json,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated settings" in result.output


def test_recipe_set_settings_updates_payload(patch_client):
    """set-settings with payload key updates visual recipe config."""
    settings_json = json.dumps(
        {"payload": {"orders": [{"column": "price", "desc": True}]}}
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "recipe1",
            "--settings",
            settings_json,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


def test_recipe_set_settings_blocks_nlp_agent_eval_output_column(patch_client):
    """nlp_agent_evaluation hard-pins outputColumnName — surface that before save."""
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe("agent_eval_recipe")
    recipe.get_settings.return_value.get_recipe_raw_definition.return_value = {
        "type": "nlp_agent_evaluation",
        "name": "agent_eval_recipe",
    }
    settings_json = json.dumps({"payload": {"outputColumnName": "my_col"}})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "agent_eval_recipe",
            "--settings",
            settings_json,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Cannot change `outputColumnName`" in result.output
    assert "JSON envelope" in result.output
    # The settings save must NOT have happened — otherwise the user thinks it
    # worked and is confused later when DSS reverted it.
    recipe.get_settings.return_value.save.assert_not_called()


def test_recipe_set_settings_rejects_stringified_payload(patch_client):
    """set-settings emits prescriptive error when a visual payload was re-stringified."""
    # User error: ran `get-settings -o json | jq '.payload |= tostring'`
    # then `set-settings` — payload becomes a JSON string, not a dict. This
    # guidance is for VISUAL recipes (code recipes get a different message).
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe("recipe1").get_settings()
    settings.get_recipe_raw_definition.return_value = {"type": "sampling"}
    settings_json = json.dumps(
        {"payload": json.dumps({"orders": [{"column": "price", "desc": True}]})}
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "recipe1",
            "--settings",
            settings_json,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    # The error message must point at the actual problem so the agent
    # doesn't re-paste the same broken payload.
    assert "JSON object" in result.output or "must be a JSON" in result.output
    assert "json.dumps" in result.output or "re-stringify" in result.output


def test_recipe_create_filter_with_formula(patch_client):
    """create-filter builds a Prepare recipe with a FilterOnCustomFormula step."""
    proj, _recipe_mock, settings = _setup_prepare_mock(patch_client, steps=[])

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-filter",
            "my_filter",
            "-i",
            "data",
            "--output-ds",
            "filtered",
            "--filter-formula",
            "age > 30",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created filter recipe" in result.output
    # Expect a prepare/shaker recipe with a single FilterOnCustomFormula step
    proj.new_recipe.assert_called_with("shaker", "my_filter")
    steps = settings.obj_payload["steps"]
    assert len(steps) == 1
    step = steps[0]
    assert step["type"] == "FilterOnCustomFormula"
    assert step["params"]["expression"] == "age > 30"
    assert step["params"]["action"] == "KEEP_ROW"
    settings.save.assert_called()


def test_recipe_create_filter_remove_row(patch_client):
    """--action REMOVE_ROW drops matching rows instead of keeping them."""
    proj, _recipe_mock, settings = _setup_prepare_mock(patch_client, steps=[])

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-filter",
            "drop_bad",
            "-i",
            "data",
            "--output-ds",
            "cleaned",
            "-f",
            "status == 'ERROR'",
            "--action",
            "REMOVE_ROW",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    steps = settings.obj_payload["steps"]
    assert steps[0]["params"]["action"] == "REMOVE_ROW"


def test_recipe_create_window_with_partition_col(patch_client):
    """--partition-col alias configures window partitioning."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "my_window",
            "-i",
            "data",
            "--output-ds",
            "windowed",
            "--partition-col",
            "customer_id",
            "--order-col",
            "date",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created window recipe" in result.output
    assert settings.obj_payload["partitioningColumns"] == [{"column": "customer_id"}]
    assert settings.obj_payload["orders"] == [{"column": "date", "desc": False}]
    settings.save.assert_called()


# ---------------------------------------------------------------------------


# ── NET-NEW (PR surface): set-env, set-code --file alias, set-definition
# payload guards (code-recipe refusal + visual ok + wrapper unwrap),
# set-description, set-settings code-recipe redirect, plugin customConfig ──


def test_recipe_set_env_explicit(patch_client):
    """set-env writes envSelection + containerSelection into recipe params."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    raw_def: dict = {
        "type": "python",
        "params": {"envSelection": {"envMode": "INHERIT"}},
    }
    settings = recipe.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = raw_def
    patch_client.list_code_envs.return_value = [
        {"envName": "migloop_py", "envLang": "PYTHON"},
    ]
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-env",
            "recipe1",
            "--env-mode",
            "EXPLICIT_ENV",
            "--env-name",
            "migloop_py",
            "--container-mode",
            "NONE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated env/container" in result.output
    assert raw_def["params"]["envSelection"] == {
        "envMode": "EXPLICIT_ENV",
        "envName": "migloop_py",
    }
    assert raw_def["params"]["containerSelection"] == {"containerMode": "NONE"}
    settings.save.assert_called()


def test_recipe_set_env_null_params_persists(patch_client):
    """set-env on a recipe with NO params key writes into the ATTACHED definition.

    `get_recipe_params()` returns None right after a bare code-recipe create;
    the old `or {}` idiom wrote into a detached dict, persisted nothing, and
    still printed success (live-confirmed silent no-op).
    """
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    raw_def: dict = {"type": "python"}
    settings = recipe.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = raw_def
    settings.get_recipe_params.return_value = None
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-env",
            "recipe1",
            "--container-mode",
            "NONE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw_def["params"]["containerSelection"] == {"containerMode": "NONE"}
    settings.save.assert_called()


def test_recipe_set_env_rejects_invalid_env_mode(patch_client):
    """An invalid --env-mode (e.g. USE_BUILTIN_ENV) is refused with the real values.

    DSS deserializes an unknown envMode to null and only fails at build time.
    """
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-env",
            "recipe1",
            "--env-mode",
            "USE_BUILTIN_ENV",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "USE_BUILTIN_MODE" in result.output
    recipe.get_settings.return_value.save.assert_not_called()


def test_recipe_set_env_rejects_unknown_env(patch_client):
    """--env-name that does not exist on the instance is refused up-front.

    DSS accepts any string for envName without validating it, so the bad env
    only surfaces as a confusing failure at recipe build time. set-env must
    catch it before writing anything.
    """
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    patch_client.list_code_envs.return_value = [
        {"envName": "py39", "envLang": "PYTHON"},
    ]
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-env",
            "recipe1",
            "--env-mode",
            "EXPLICIT_ENV",
            "--env-name",
            "nonexistent_env",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output
    assert "dku code-env list" in result.output
    recipe.get_settings.return_value.save.assert_not_called()


def test_recipe_set_env_requires_env_name(patch_client):
    """EXPLICIT_ENV without --env-name is a prescriptive error, no save."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-env",
            "recipe1",
            "--env-mode",
            "EXPLICIT_ENV",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "requires --env-name" in result.output
    recipe.get_settings.return_value.save.assert_not_called()


def test_recipe_set_env_nothing_to_set(patch_client):
    """Passing neither --env-mode nor --container-mode is an explicit error."""
    result = runner.invoke(app, ["recipe", "set-env", "recipe1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "Nothing to set" in result.output


def test_recipe_set_code_from_file_alias(patch_client, tmp_path):
    """--file is an alias for --code @file, matching curl/kubectl convention."""
    code_file = tmp_path / "script.py"
    code_file.write_text("print('via --file alias')")
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--file",
            str(code_file),
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    payload_arg = recipe.get_settings().set_payload.call_args[0][0]
    assert "via --file alias" in payload_arg


def test_recipe_set_code_rejects_both_code_and_file(patch_client, tmp_path):
    """Passing both --code and --file is an explicit error."""
    code_file = tmp_path / "script.py"
    code_file.write_text("x")
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            "y",
            "--file",
            str(code_file),
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "exactly one of --code / --file" in result.output


def test_recipe_set_definition_payload_refuses_code_recipe(patch_client):
    """--payload on a code recipe must refuse: its payload IS the source code,
    so seeding a JSON payload would silently wipe it. Regression: the Docker
    container-mode hint used to suggest exactly this, clobbering the code."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.get_recipe_raw_definition.return_value = {
        "type": "python",
        "name": "recipe1",
    }
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            '{"containerSelection": {"containerMode": "NONE"}}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "code recipe" in result.output
    assert "set-env" in result.output
    assert "set-code" in result.output
    settings.save.assert_not_called()


def test_recipe_set_definition_payload_visual_ok(patch_client):
    """--payload still works on a visual recipe (its payload is JSON config)."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.get_recipe_raw_definition.return_value = {
        "type": "grouping",
        "name": "recipe1",
    }
    settings.obj_payload = {"existing": "kept"}
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            '{"postFilter": {"enabled": true}}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Updated payload" in result.output
    assert settings.obj_payload["existing"] == "kept"
    assert settings.obj_payload["postFilter"] == {"enabled": True}
    settings.save.assert_called()


def test_recipe_set_definition_unwraps_get_definition_wrapper(patch_client):
    """Passing the full {definition, payload} output of get-definition is
    auto-unwrapped — only the inner definition lands in raw_definition.
    Previously this silently wrote 'definition' and 'payload' top-level keys
    into raw_definition with a 'success' message."""
    raw = {"type": "python", "name": "recipe1"}
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.get_settings().get_recipe_raw_definition.return_value = raw

    wrapper = json.dumps(
        {
            "definition": {"type": "python", "customFields": {"k": "v"}},
            "payload": {"some_payload": "ignored"},
        }
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            wrapper,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Unwrapping --definition" in result.output
    # Inner definition merged; wrapper keys NOT injected into raw_definition.
    assert raw["customFields"] == {"k": "v"}
    assert "payload" not in raw
    assert "$status" not in raw


def test_recipe_set_definition_unwraps_dollar_status_wrapper(patch_client):
    """The raw DSS response shape {definition, $status} is also unwrapped."""
    raw = {"type": "python", "name": "recipe1"}
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.get_settings().get_recipe_raw_definition.return_value = raw

    wrapper = json.dumps(
        {
            "definition": {"type": "python", "description": "set via dku"},
            "$status": {"recipeStatus": {}},
        }
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            wrapper,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["description"] == "set via dku"
    assert "$status" not in raw


# ── Prepare step: add-fold ─────────────────────────────────────────────


def test_recipe_set_description_inline(patch_client):
    raw = {"type": "python", "name": "recipe1"}
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.get_settings().get_recipe_raw_definition.return_value = raw

    result = runner.invoke(
        app,
        [
            "recipe",
            "set-description",
            "recipe1",
            "--description",
            "Computes daily KPIs from raw events.",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Updated description for recipe 'recipe1'" in result.output
    assert raw["description"] == "Computes daily KPIs from raw events."
    # Sibling top-level keys preserved (shallow merge semantics).
    assert raw["type"] == "python"
    assert raw["name"] == "recipe1"
    recipe.get_settings().save.assert_called()


def test_recipe_set_description_from_file(tmp_path, patch_client):
    desc_path = tmp_path / "desc.md"
    desc_path.write_text("# Daily KPIs\n\nLong-form description.")
    raw = {"type": "python", "name": "recipe1"}
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.get_settings().get_recipe_raw_definition.return_value = raw

    result = runner.invoke(
        app,
        [
            "recipe",
            "set-description",
            "recipe1",
            "--description",
            f"@{desc_path}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["description"] == "# Daily KPIs\n\nLong-form description."
    recipe.get_settings().save.assert_called()


def test_recipe_set_settings_code_recipe_points_to_set_env(patch_client):
    """set-settings on a code recipe (string payload) redirects to set-env/set-code."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe("recipe1").get_settings()
    settings.get_recipe_raw_definition.return_value = {"type": "python"}
    # User tried to tweak the python recipe's container mode via set-settings,
    # so the round-tripped payload is the code string.
    settings_json = json.dumps({"payload": "import dataiku\n"})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-settings",
            "recipe1",
            "--settings",
            settings_json,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    # Must point at the right verbs, not the json.dumps red herring.
    assert "code recipe" in result.output
    assert "set-env" in result.output
    assert "set-code" in result.output
    assert "container-mode NONE" in result.output


def test_recipe_create_plugin_recipe_params_go_to_custom_config(patch_client):
    """--params for a CustomCode_* recipe must land in params.customConfig (where
    the plugin reads its config) — NOT in the payload/rawPayload, which left the
    plugin unconfigured (verified live: plugin_recipe_create_params_bug)."""
    proj = patch_client.get_project("PROJ1")
    proj.create_recipe.return_value = MagicMock()

    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_plugin_step",
            "--type",
            "CustomCode_batch-file-processor",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--params",
            '{"sheet_mode": "all", "flag": true}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe_proto, creation_settings = proj.create_recipe.call_args[0][:2]
    assert recipe_proto["params"]["customConfig"] == {
        "sheet_mode": "all",
        "flag": True,
    }
    assert recipe_proto["params"]["containerSelection"] == {"containerMode": "INHERIT"}
    # The old (broken) path stuffed config into rawPayload — must not happen now.
    assert "rawPayload" not in creation_settings
