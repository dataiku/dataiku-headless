"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from tests.commands.recipe.helpers import app, runner
from tests.commands.recipe.helpers import setup_prepare_mock as _setup_prepare_mock


def test_recipe_list(patch_client):
    result = runner.invoke(app, ["recipe", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "recipe1" in result.output


def test_recipe_list_json(patch_client):
    result = runner.invoke(app, ["recipe", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "recipe1"
    assert parsed[0]["type"] == "python"


def test_recipe_get(patch_client):
    result = runner.invoke(app, ["recipe", "get", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "input_ds" in result.output


def test_recipe_get_json(patch_client):
    result = runner.invoke(
        app, ["recipe", "get", "recipe1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "type" in parsed


def test_recipe_get_definition_json(patch_client):
    """get-definition returns both definition and payload in JSON mode."""
    result = runner.invoke(
        app,
        ["recipe", "get-definition", "recipe1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "definition" in parsed
    assert "payload" in parsed
    assert "type" in parsed["definition"]


def test_recipe_get_definition_table(patch_client):
    """get-definition shows key fields in table mode."""
    result = runner.invoke(
        app, ["recipe", "get-definition", "recipe1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Type" in result.output
    assert "Payload" in result.output


def test_recipe_get_definition_sql_query_raw_payload(patch_client):
    """SQL query recipes have raw text payloads — obj_payload raises JSONDecodeError.
    get-definition must not crash and should show a text preview of the SQL.
    """
    from unittest.mock import PropertyMock
    import json as _json

    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "sql_query",
        "name": "extract_base_plan",
    }
    settings._str_payload = (
        "SELECT * FROM ${projectKey}_src WHERE reporting_date > '2024-12-31'"
    )
    # obj_payload should NOT be consulted for sql_query recipes; simulate the
    # real dataikuapi behavior where it raises on invalid JSON.
    type(settings).obj_payload = PropertyMock(
        side_effect=_json.JSONDecodeError("Expecting value", "", 0)
    )
    settings.get_flat_input_refs.return_value = ["src", "dim_a", "dim_b"]
    settings.get_flat_output_refs.return_value = ["extract_base_plan"]

    result = runner.invoke(
        app, ["recipe", "get-definition", "extract_base_plan", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    assert "sql_query" in result.output
    assert "src" in result.output
    assert "extract_base_plan" in result.output
    # The SQL preview should appear (truncated is OK)
    assert "SELECT" in result.output or "reporting_date" in result.output


def test_recipe_get_definition_sql_query_json_output(patch_client):
    """In JSON mode, SQL recipe payload must serialize as a string, not crash."""
    from unittest.mock import PropertyMock
    import json as _json

    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "sql_query",
        "name": "my_sql",
    }
    settings._str_payload = "SELECT count(*) FROM ${projectKey}_dim_a"
    type(settings).obj_payload = PropertyMock(
        side_effect=_json.JSONDecodeError("Expecting value", "", 0)
    )
    settings.get_flat_input_refs.return_value = ["dim_a"]
    settings.get_flat_output_refs.return_value = ["my_sql_out"]

    result = runner.invoke(
        app, ["recipe", "get-definition", "my_sql", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = _json.loads(result.output)
    assert parsed["definition"]["type"] == "sql_query"
    assert parsed["payload"] == "SELECT count(*) FROM ${projectKey}_dim_a"


def test_recipe_run(patch_client):
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_recipe_run_wait(patch_client):
    result = runner.invoke(
        app, ["recipe", "run", "recipe1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0


def test_recipe_run_with_type(patch_client):
    """Run with --type uses job builder."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "recipe1",
            "--type",
            "RECURSIVE_BUILD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")
    builder = proj.new_job.return_value
    # Should build recipe's output refs, resolving the object type (defaults to
    # DATASET so managed-folder / saved-model outputs don't error).
    builder.with_output.assert_called_once_with("output_ds", object_type="DATASET")


def test_recipe_run_invalid_type_rejected_at_parse(patch_client):
    """--type is the JobType click.Choice; an invalid build type is rejected
    at parse time (exit 2) instead of reaching proj.new_job()."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "recipe1",
            "--type",
            "RECURSIVE",  # typo of RECURSIVE_BUILD
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_not_called()


def test_recipe_run_type_case_insensitive(patch_client):
    """--type accepts lowercase input (case_sensitive=False) and forwards the
    canonical uppercase value to proj.new_job()."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "recipe1",
            "--type",
            "recursive_build",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")


def test_recipe_run_auto_update_schema(patch_client):
    """Run with --auto-update-schema uses job builder."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "recipe1",
            "--auto-update-schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_called_once_with(True)


def test_recipe_run_shaker_with_rename_emits_apply_schema_hint(patch_client):
    """A successful Prepare run with rename/formula steps emits a hint pointing
    at apply-schema. The first run propagates upstream schema only — agents
    routinely see stale output schemas until a second apply-schema + re-run."""
    _setup_prepare_mock(
        patch_client,
        steps=[
            {
                "type": "ColumnRenamer",
                "params": {"renamings": [{"from": "a", "to": "b"}]},
            },
        ],
    )
    result = runner.invoke(
        app, ["recipe", "run", "prep1", "--wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "apply-schema" in result.output
    assert "prep1" in result.output


def test_recipe_run_shaker_with_formula_emits_apply_schema_hint(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[
            {
                "type": "CreateColumnWithGREL",
                "params": {"column": "x", "expression": "1"},
            },
        ],
    )
    result = runner.invoke(
        app, ["recipe", "run", "prep1", "--wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "apply-schema" in result.output


def test_recipe_run_shaker_no_schema_steps_no_hint(patch_client):
    """Prepare with non-schema-changing steps (e.g. FilterOnCustomFormula) → no hint."""
    _setup_prepare_mock(
        patch_client,
        steps=[
            {"type": "FilterOnCustomFormula", "params": {"expression": "x > 0"}},
        ],
    )
    result = runner.invoke(
        app, ["recipe", "run", "prep1", "--wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "apply-schema" not in result.output


def test_recipe_run_with_auto_update_schema_no_hint(patch_client):
    """Hint is suppressed when --auto-update-schema is already passed."""
    _setup_prepare_mock(
        patch_client,
        steps=[
            {
                "type": "ColumnRenamer",
                "params": {"renamings": [{"from": "a", "to": "b"}]},
            },
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "prep1",
            "--wait",
            "--auto-update-schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "apply-schema" not in result.output


def test_recipe_run_failure_prints_log_command(patch_client):
    """When the recipe run fails, the CLI must print the job ID and a
    copy-paste 'dku job log' command so the agent can inspect the failure
    without extra discovery calls."""
    proj = patch_client.get_project("PROJ1")
    started_job = proj.new_job.return_value.start.return_value
    started_job.id = "Build_failed_123"
    started_job.get_status.return_value = {"baseStatus": {"state": "FAILED"}}

    result = runner.invoke(
        app, ["recipe", "run", "recipe1", "--wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 4, result.output
    assert "Build_failed_123" in result.output
    assert "dku job log Build_failed_123" in result.output
    assert "PROJ1" in result.output


def test_recipe_run_always_uses_builder_path(patch_client):
    """Even without --type or --auto-update-schema, run uses the job builder
    path (not recipe.run()) so the job ID is known on failure."""
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    # The builder was invoked with the default job type
    proj.new_job.assert_called_with("NON_RECURSIVE_FORCED_BUILD")
    builder = proj.new_job.return_value
    builder.start.assert_called_once()


# --- New commands ---


def test_recipe_create(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "new_recipe",
            "--type",
            "python",
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
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("python", "new_recipe")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("input_ds")
    # Python is a code recipe — no --connection means with_output() (project default)
    builder.with_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_create_multiple_inputs(patch_client):
    """Regression: `-i A -i B` must wire BOTH inputs, not silently drop the first."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "multi_input",
            "--type",
            "python",
            "-i",
            "a",
            "-i",
            "b",
            "-i",
            "c",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Every -i must reach with_input — previously only the last was wired.
    assert builder.with_input.call_count == 3
    called_inputs = [call.args[0] for call in builder.with_input.call_args_list]
    assert called_inputs == ["a", "b", "c"]


def test_recipe_create_plugin_type_uses_raw_mode(patch_client):
    """CustomCode_* plugin types bypass new_recipe() and use DSSRecipeCreator in raw mode."""
    proj = patch_client.get_project("PROJ1")

    with patch("dataikuapi.dss.recipe.DSSRecipeCreator") as mock_creator_cls:
        mock_builder = MagicMock()
        mock_creator_cls.return_value = mock_builder

        result = runner.invoke(
            app,
            [
                "recipe",
                "create",
                "plugin_recipe",
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
        mock_creator_cls.assert_called_once_with(
            "CustomCode_my-recipe", "plugin_recipe", proj
        )
        mock_builder.set_raw_mode.assert_called_once()
        mock_builder.with_input.assert_called_once()
        mock_builder.with_output.assert_called_once()
        mock_builder.build.assert_called_once()
        # Should NOT have called proj.new_recipe for plugin types
        proj.new_recipe.assert_not_called()


def test_recipe_create_code_recipe_fallback(patch_client):
    """CodeRecipeCreator lacks with_existing_output — falls back to with_output."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Remove with_existing_output to simulate CodeRecipeCreator
    del builder.with_existing_output
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "code_recipe",
            "--type",
            "python",
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
    builder.with_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_create_python_without_input(patch_client):
    """Python recipes can be created without --input (data generation use case)."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    del builder.with_existing_output  # simulate CodeRecipeCreator
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "gen_data",
            "--type",
            "python",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    builder.with_input.assert_not_called()
    builder.with_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_create_shell_without_input(patch_client):
    """Shell recipes can be created without --input."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    del builder.with_existing_output
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "gen_shell",
            "--type",
            "shell",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder.with_input.assert_not_called()


def test_recipe_create_sql_requires_input(patch_client):
    """SQL recipes must have --input — not in _INPUT_OPTIONAL_TYPES."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_sql_recipe",
            "--type",
            "sql",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--input is required" in result.output
    assert "code recipes" in result.output.lower()


def test_recipe_create_visual_requires_input(patch_client):
    """Visual recipe types (join, group, etc.) must have --input."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_join",
            "--type",
            "join",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--input is required" in result.output


def test_recipe_create_output_confusion_detected(patch_client):
    """Using --output with a dataset name suggests --output-ds."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--output",
            "my_dataset",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--output-ds" in result.output
    assert "my_dataset" in result.output


def test_recipe_create_output_dataset_alias(patch_client):
    """--output-dataset works as an alias for --output-ds."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-dataset",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Python is a code recipe — no --connection means with_output() (project default)
    builder.with_output.assert_called_once_with("output_ds")


def test_recipe_create_output_ds_already_exists(patch_client):
    """Recipe create gives specific error when output dataset already exists."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.build.side_effect = Exception("already exists: dataset 'output_ds'")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "new_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_recipe_create_with_connection(patch_client):
    """--connection uses with_new_output_dataset for code recipes."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Remove with_existing_output to simulate CodeRecipeCreator
    del builder.with_existing_output
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "code_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--connection",
            "filesystem_managed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    builder.with_new_output_dataset.assert_called_once_with(
        "output_ds", "filesystem_managed"
    )
    builder.with_output.assert_not_called()
    builder.build.assert_called_once()


def test_recipe_create_visual_with_connection_auto_creates_output(patch_client):
    """Visual recipes with --connection auto-create the output via with_new_output().

    Visual recipe builders (JoinRecipeCreator, GroupingRecipeCreator, ...)
    inherit with_new_output(name, connection) from SingleOutputRecipeCreator
    via VirtualInputsSingleOutputRecipeCreator. The CLI routes --connection
    through that path so visual recipes can create their output on the target
    connection in one call (no need to pre-create the output dataset).
    """
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Visual builders have with_new_output but NOT with_new_output_dataset
    del builder.with_new_output_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "visual_recipe",
            "--type",
            "join",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--connection",
            "sql_managed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created recipe" in result.output
    builder.with_new_output.assert_called_once_with("output_ds", "sql_managed")
    builder.with_existing_output.assert_not_called()


def test_recipe_create_visual_without_connection_uses_existing_output(patch_client):
    """Visual recipes without --connection still require a pre-existing output."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "visual_recipe",
            "--type",
            "join",
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
    builder = patch_client.get_project("PROJ1").new_recipe.return_value
    builder.with_existing_output.assert_called_once_with("output_ds")
    builder.with_new_output.assert_not_called()


def test_recipe_create_sync_with_connection(patch_client):
    """-t sync --connection X routes to with_new_output() (SingleOutputRecipeCreator path).

    Canonical cross-connection landing pattern (file -> managed SQL table, etc.).
    Before this fix, `sync` was mis-classified as visual and forced users to
    pre-create the output dataset (which defaults to unwritable `query` mode on
    SQL connections).
    """
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # SingleOutputRecipeCreator has with_new_output but NOT with_new_output_dataset
    del builder.with_new_output_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "sync_csv_to_sql",
            "--type",
            "sync",
            "--input",
            "my_csv",
            "--output-ds",
            "my_sql_table",
            "--connection",
            "sql_managed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created recipe" in result.output
    proj.new_recipe.assert_called_once_with("sync", "sync_csv_to_sql")
    builder.with_new_output.assert_called_once_with("my_sql_table", "sql_managed")
    builder.with_existing_output.assert_not_called()


def test_recipe_create_sql_query_with_connection(patch_client):
    """-t sql_query --connection X routes to with_new_output()."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    del builder.with_new_output_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_sql_step",
            "--type",
            "sql_query",
            "--input",
            "src_table",
            "--output-ds",
            "derived_table",
            "--connection",
            "sql_managed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    builder.with_new_output.assert_called_once_with("derived_table", "sql_managed")


def test_recipe_create_connection_required_error(patch_client):
    """Missing managed connection gives actionable error suggesting --connection."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    del builder.with_existing_output
    builder.build.side_effect = Exception(
        "java.lang.IllegalArgumentException: Need to create output dataset or folder, "
        "but creationInfo params are suppressing it"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "code_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--connection" in result.output
    assert "filesystem_managed" in result.output


def test_recipe_create_visual_type_connection_error_suggests_pre_create(patch_client):
    """Visual recipe (prepare) should suggest pre-creating the output dataset, not --connection."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Simulate a visual recipe — has with_existing_output
    builder.with_existing_output.side_effect = None
    builder.build.side_effect = Exception(
        "java.lang.IllegalArgumentException: Need to create output dataset or folder, "
        "but creationInfo params are suppressing it"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "prep1",
            "--type",
            "prepare",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    # Should suggest creating the output dataset, NOT --connection
    assert "does not exist" in result.output or "created first" in result.output
    assert "dku dataset create" in result.output
    # Should NOT suggest --connection for visual recipes
    assert "add --connection" not in result.output


def test_recipe_delete(patch_client):
    result = runner.invoke(
        app, ["recipe", "delete", "recipe1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted recipe" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.delete.assert_called_once()


def test_recipe_rename(patch_client):
    result = runner.invoke(
        app,
        ["recipe", "rename", "recipe1", "--name", "recipe1_new", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Renamed" in result.output
    assert "recipe1_new" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.rename.assert_called_once_with("recipe1_new")


def test_recipe_rename_same_name_error(patch_client):
    """Renaming to the same name gives prescriptive error."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.rename.side_effect = ValueError("Recipe name is already recipe1")
    result = runner.invoke(
        app,
        ["recipe", "rename", "recipe1", "--name", "recipe1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_recipe_rename_requires_name(patch_client):
    """--name is required."""
    result = runner.invoke(app, ["recipe", "rename", "recipe1", "--project", "PROJ1"])
    assert result.exit_code != 0


# --- status ---


def test_recipe_status_table(patch_client):
    """Status shows engine, severity, and messages."""
    result = runner.invoke(app, ["recipe", "status", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "DSS" in result.output  # engine
    assert "SUCCESS" in result.output  # severity
    assert "Recipe is valid" in result.output  # message title


def test_recipe_status_json(patch_client):
    """JSON output returns structured status."""
    result = runner.invoke(
        app, ["recipe", "status", "recipe1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["engine"] == "DSS"
    assert parsed["severity"] == "SUCCESS"
    assert len(parsed["messages"]) == 1
    assert parsed["messages"][0]["severity"] == "SUCCESS"


def test_recipe_status_no_engine(patch_client):
    """Recipes without engine concept show (none)."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    status_mock = recipe.get_status.return_value
    status_mock.get_selected_engine_details.side_effect = ValueError(
        "This recipe doesn't have a selected engine"
    )
    result = runner.invoke(app, ["recipe", "status", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "(none)" in result.output


def test_recipe_status_no_messages(patch_client):
    """Recipes with no messages show informational text."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    status_mock = recipe.get_status.return_value
    status_mock.get_status_messages.return_value = []
    status_mock.get_status_severity.return_value = None
    result = runner.invoke(app, ["recipe", "status", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "no status messages" in result.output.lower()


def test_recipe_status_env_project(patch_client, monkeypatch):
    """Resolves project from DKU_PROJECT env var."""
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["recipe", "status", "recipe1"])
    assert result.exit_code == 0


def test_recipe_delete_blocks_without_yes(patch_client):
    result = runner.invoke(app, ["recipe", "delete", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 77
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.delete.assert_not_called()


def test_recipe_set_code_inline(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            "print('hello')",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated code" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.set_payload.assert_called_once_with("print('hello')")
    settings.save.assert_called()


def test_recipe_set_code_from_file(patch_client, tmp_path):
    code_file = tmp_path / "script.py"
    code_file.write_text("import dataiku\nds = dataiku.Dataset('test')")
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            f"@{code_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    payload_arg = settings.set_payload.call_args[0][0]
    assert "import dataiku" in payload_arg
    assert "Dataset('test')" in payload_arg


def test_recipe_get_code(patch_client):
    result = runner.invoke(app, ["recipe", "get-code", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "# Python code" in result.output


def test_recipe_get_code_json(patch_client):
    result = runner.invoke(
        app, ["recipe", "get-code", "recipe1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["code"].startswith("# Python code")
    assert "import dataiku" in result.output


def test_recipe_set_code_from_stdin(patch_client):
    stdin_code = "import dataiku\nprint('from stdin')"
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            "-",
            "--project",
            "PROJ1",
        ],
        input=stdin_code,
    )
    assert result.exit_code == 0
    assert "Updated code" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    payload_arg = settings.set_payload.call_args[0][0]
    assert "import dataiku" in payload_arg
    assert "from stdin" in payload_arg


def test_recipe_create_type_as_name_detected(patch_client):
    """Detect when recipe_name is actually a recipe type (e.g. 'python')."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "python",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "looks like a recipe type" in result.output
    assert "dku recipe create <NAME> --type python" in result.output


def test_recipe_set_definition(patch_client):
    new_def = json.dumps({"type": "sql", "customFields": {"key": "val"}})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            new_def,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.save.assert_called()


def test_recipe_add_input(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "extra_input",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added dataset 'extra_input'" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("main", "extra_input")
    settings.save.assert_called()


def test_recipe_add_output(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-output",
            "recipe1",
            "extra_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added output" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_output.assert_called_once_with("main", "extra_output")
    settings.save.assert_called()


def test_recipe_create_download_basic(patch_client):
    """create-download writes payload-less raw recipe with sources[]."""
    proj = patch_client.get_project("PROJ1")
    proj.list_managed_folders.return_value = [{"id": "FF1", "name": "raw_csvs"}]
    recipe_handle = MagicMock()
    raw_def = {}
    recipe_handle.get_settings.return_value.get_recipe_raw_definition.return_value = (
        raw_def
    )
    proj.create_recipe.return_value = recipe_handle

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-download",
            "fetch",
            "--output-folder",
            "raw_csvs",
            "--source",
            "HTTPS:https://example.com/a.csv",
            "--source",
            "S3:s3://bucket/key.parquet",
            "--delete-extra",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    params = raw_def["params"]
    assert params["deleteExtraFiles"] is True
    assert params["copyEvenUpToDateFiles"] is False
    assert params["sources"][0] == {
        "providerType": "HTTPS",
        "params": {"url": "https://example.com/a.csv"},
    }
    assert params["sources"][1]["providerType"] == "S3"
    assert params["sources"][1]["params"]["url"] == "s3://bucket/key.parquet"


def test_recipe_create_download_invalid_provider(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_managed_folders.return_value = [{"id": "FF1", "name": "f"}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-download",
            "x",
            "--output-folder",
            "f",
            "--source",
            "GOPHER:gopher://...",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --source provider" in result.output


def test_recipe_create_download_malformed_source(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_managed_folders.return_value = [{"id": "FF1", "name": "f"}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-download",
            "x",
            "--output-folder",
            "f",
            "--source",
            "no-colon-here",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Expected 'PROVIDER:URL'" in result.output


def test_recipe_create_export_basic(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_managed_folders.return_value = [{"id": "FF1", "name": "exports"}]
    recipe_handle = MagicMock()
    raw_def = {}
    recipe_handle.get_settings.return_value.get_recipe_raw_definition.return_value = (
        raw_def
    )
    proj.create_recipe.return_value = recipe_handle

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-export",
            "to_csv",
            "-i",
            "sales",
            "--output-folder",
            "exports",
            "--format",
            "csv",
            "--apply-exploration-filters",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    ep = raw_def["params"]["exportParams"]
    assert ep["format"] == "csv"
    assert ep["applyExplorationFilters"] is True
    assert ep["applyColoring"] is False


def test_recipe_create_export_invalid_format(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-export",
            "x",
            "-i",
            "sales",
            "--output-folder",
            "out",
            "--format",
            "xml",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_recipe_replace_input(patch_client):
    """replace-input swaps inputs[role].items[i].ref where ref matches old."""
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe.return_value
    settings = recipe.get_settings.return_value
    raw = {"inputs": {"main": {"items": [{"ref": "old_ds"}, {"ref": "other_ds"}]}}}
    settings.get_recipe_raw_definition.return_value = raw
    settings.obj_payload = {
        "virtualInputs": [
            {"index": 0, "dataset": "old_ds"},
            {"index": 1, "dataset": "other_ds"},
        ]
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-input",
            "recipe1",
            "old_ds",
            "new_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    items = raw["inputs"]["main"]["items"]
    assert items[0]["ref"] == "new_ds"
    assert items[1]["ref"] == "other_ds"
    # Visual recipe virtualInputs should also be patched.
    assert settings.obj_payload["virtualInputs"][0]["dataset"] == "new_ds"
    assert settings.obj_payload["virtualInputs"][1]["dataset"] == "other_ds"
    settings.save.assert_called()


def test_recipe_replace_input_not_found(patch_client):
    """replace-input must error when OLD_REF isn't an input — never silently no-op."""
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe.return_value
    settings = recipe.get_settings.return_value
    raw = {"inputs": {"main": {"items": [{"ref": "real_ds"}]}}}
    settings.get_recipe_raw_definition.return_value = raw

    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-input",
            "recipe1",
            "ghost_ds",
            "new_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "no input 'ghost_ds'" in result.output


def test_recipe_replace_input_unknown_role(patch_client):
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe.return_value
    settings = recipe.get_settings.return_value
    raw = {"inputs": {"main": {"items": [{"ref": "x"}]}}}
    settings.get_recipe_raw_definition.return_value = raw

    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-input",
            "recipe1",
            "x",
            "y",
            "--role",
            "lookup",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "no input role 'lookup'" in result.output


def test_recipe_add_input_custom_role(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "lookup_ds",
            "--role",
            "lookup",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("lookup", "lookup_ds")


def test_recipe_add_input_syncs_visual_recipe_virtual_inputs(patch_client):
    """For visual recipes (join/stack/pivot/...), add-input must append to
    payload.virtualInputs[] so the new input is visible to the payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    # Simulate a 2-input visual join before add-input
    settings.obj_payload = {
        "virtualInputs": [
            {"index": 0},
            {"index": 1},
        ]
    }
    # After add_input is called, the main items should grow to 3
    settings.get_recipe_raw_definition.return_value = {
        "inputs": {
            "main": {
                "items": [
                    {"ref": "src1"},
                    {"ref": "src2"},
                    {"ref": "src3"},
                ]
            }
        }
    }

    result = runner.invoke(
        app,
        ["recipe", "add-input", "jrec", "src3", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    # virtualInputs should now have 3 entries with indices 0, 1, 2
    vi = settings.obj_payload["virtualInputs"]
    assert len(vi) == 3
    assert {v["index"] for v in vi} == {0, 1, 2}


def test_recipe_add_input_code_recipe_leaves_payload_alone(patch_client):
    """For code recipes (python/sql/r/shell), add-input must NOT touch
    the payload — they don't use virtualInputs."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    # Python recipes have no virtualInputs field at all
    settings.obj_payload = {"some_other_key": "unchanged"}

    result = runner.invoke(
        app,
        ["recipe", "add-input", "py_rec", "extra_ds", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    # Payload should be untouched — no virtualInputs key added
    assert "virtualInputs" not in settings.obj_payload
    assert settings.obj_payload["some_other_key"] == "unchanged"


# ── NET-NEW (PR surface): status --engines / --full, create --input-folder,
# create -t group routing to the dedicated create-group verb ──────────


def test_recipe_status_engines_table(patch_client):
    """--engines lists every candidate with type / label / variant / severity / message."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    status_mock = recipe.get_status.return_value
    status_mock.data = {
        "engines": [
            {
                "type": "DSS",
                "label": "DSS",
                "variantLabel": "Stream",
                "statusWarnLevel": "OK",
                "statusMessage": None,
                "recommended": False,
            },
            {
                "type": "SQL",
                "label": "In-database (SQL)",
                "variantLabel": "",
                "statusWarnLevel": "ERROR",
                "statusMessage": "Dataset 'foo' is not a SQL table dataset",
                "recommended": False,
            },
            {
                "type": "TDCH",
                "label": "TDCH",
                "variantLabel": "",
                "statusWarnLevel": "WARN",
                "statusMessage": "TDCH is disabled",
                "recommended": False,
            },
        ],
    }
    result = runner.invoke(
        app, ["recipe", "status", "recipe1", "--project", "PROJ1", "--engines"]
    )
    assert result.exit_code == 0
    # Rich may wrap cell text to fit terminal; assert tokens, not full strings
    assert "DSS" in result.output
    assert "Stream" in result.output
    assert "SQL" in result.output
    assert "In-database" in result.output
    assert "TDCH" in result.output
    assert "WARN" in result.output
    assert "ERROR" in result.output
    assert "disabled" in result.output


def test_recipe_status_engines_empty(patch_client):
    """--engines on a no-engine recipe (e.g. prediction_training) prints info, not a crash."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.get_status.return_value.data = {}
    result = runner.invoke(
        app, ["recipe", "status", "recipe1", "--project", "PROJ1", "--engines"]
    )
    assert result.exit_code == 0
    assert "no engine candidates" in result.output.lower()


def test_recipe_status_full_dumps_payload(patch_client):
    """--full dumps the entire get_status data dict as JSON (default), including
    fields the default view hides (sqlWithExecutionPlanList, pivotModalities,
    outputSchema.originalType, sqlWarning, recipe-type-keyed buckets)."""
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.get_status.return_value.data = {
        "selectedEngine": {"type": "SQL"},
        "engines": [{"type": "SQL", "label": "In-database (SQL)"}],
        "splitting": {"messages": []},
        "sqlWithExecutionPlanList": [
            {"outputName": "out_a", "sql": "SELECT * FROM x WHERE c = 'A'"},
            {"outputName": "out_b", "sql": "SELECT * FROM x WHERE NOT (c='A')"},
        ],
        "outputSchema": {
            "columns": [
                {"name": "id", "type": "bigint", "originalType": "int8"},
                {"name": "amount", "type": "double", "originalType": "numeric"},
            ]
        },
        "sqlWarning": "Could not get modalities from a previous run that match the current settings",
    }
    result = runner.invoke(
        app, ["recipe", "status", "recipe1", "--project", "PROJ1", "--full"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["selectedEngine"]["type"] == "SQL"
    assert parsed["sqlWithExecutionPlanList"][0]["outputName"] == "out_a"
    assert parsed["outputSchema"]["columns"][0]["originalType"] == "int8"
    assert "modalities" in parsed["sqlWarning"]
    assert "splitting" in parsed


def test_recipe_create_input_folder(patch_client):
    """--input-folder wires a managed folder (by name→ID) as a code-recipe input.

    Closes the folder-input gap: a Python recipe that parses files out of a
    managed folder (XML/JSON/PDF) previously had no CLI path and needed the API.
    """
    proj = patch_client.get_project("PROJ1")
    proj.get_managed_folder.return_value.id = "FOLDER123"
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "parse_xml",
            "--type",
            "python",
            "--input-folder",
            "raw_xml",
            "--output-ds",
            "parsed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created recipe" in result.output
    builder = proj.new_recipe.return_value
    wired = [c.args[0] for c in builder.with_input.call_args_list]
    assert "FOLDER123" in wired  # resolved folder ID, not the name
    builder.build.assert_called_once()


def test_recipe_create_group_routes_to_dedicated_verb(patch_client):
    """Generic `create -t group` fails in DSS ('Unknown type. Please use create_recipe
    for custom recipes') because it can't supply the group key — error must point the
    agent to `create-group`."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.build.side_effect = Exception(
        "Unknown type. Please use create_recipe for custom recipes"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_group",
            "--type",
            "group",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--connection",
            "filesystem_managed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "create-group" in result.output
    # The recommended command keeps the user's recipe name and a group-key placeholder.
    assert "my_group" in result.output
    # Rich may wrap the line; check the group-key placeholder tokens are present.
    assert "<COLUMN>" in result.output
