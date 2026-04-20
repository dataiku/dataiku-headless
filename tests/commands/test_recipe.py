"""Tests for recipe commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


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
    # Should build recipe's output refs
    builder.with_output.assert_called_once_with("output_ds")


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


def test_recipe_delete_prompts_without_yes(patch_client):
    result = runner.invoke(
        app, ["recipe", "delete", "recipe1", "--project", "PROJ1"], input="y\n"
    )
    assert result.exit_code == 0
    assert "Delete recipe 'recipe1' from PROJ1?" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.delete.assert_called_once()


def test_recipe_delete_aborts_on_no(patch_client):
    result = runner.invoke(
        app, ["recipe", "delete", "recipe1", "--project", "PROJ1"], input="n\n"
    )
    assert result.exit_code != 0
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
    assert "Added input" in result.output
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


# --- GenAI recipe creation ---


def test_recipe_create_embed(patch_client):
    """New KB: get_knowledge_bank raises, so with_output_knowledge_bank is used."""
    proj = patch_client.get_project("PROJ1")
    proj.get_knowledge_bank.side_effect = Exception("not found")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed",
            "my_embed",
            "--input",
            "text_data",
            "--output-kb",
            "my_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created embed recipe" in result.output
    proj.new_recipe.assert_called_once_with("nlp_llm_rag_embedding", "my_embed")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("text_data")
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-small", "CHROMA"
    )
    builder.build.assert_called_once()


def test_recipe_create_embed_custom_vector_store(patch_client):
    """New KB with custom vector store type."""
    proj = patch_client.get_project("PROJ1")
    proj.get_knowledge_bank.side_effect = Exception("not found")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed",
            "my_embed",
            "--input",
            "text_data",
            "--output-kb",
            "my_kb",
            "--embedding-llm",
            "openai:text-embedding-3-large",
            "--vector-store-type",
            "FAISS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_recipe.return_value
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-large", "FAISS"
    )


def test_recipe_create_embed_with_embed_column(patch_client):
    """--embed-column sets knowledgeColumn in obj_payload after creation."""
    proj = patch_client.get_project("PROJ1")
    proj.get_knowledge_bank.side_effect = Exception("not found")
    recipe_mock = proj.get_recipe.return_value
    settings_mock = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed",
            "my_embed",
            "--input",
            "text_data",
            "--output-kb",
            "my_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--embed-column",
            "description",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "description" in result.output
    assert settings_mock.obj_payload["knowledgeColumn"] == "description"
    settings_mock.save.assert_called_once()


def test_recipe_create_embed_without_embed_column_warns(patch_client):
    """Without --embed-column, a warning is shown and save is NOT called."""
    proj = patch_client.get_project("PROJ1")
    proj.get_knowledge_bank.side_effect = Exception("not found")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed",
            "my_embed",
            "--input",
            "text_data",
            "--output-kb",
            "my_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "No --embed-column specified" in result.output
    # get_recipe should NOT have been called (no embed_column to set)
    proj.get_recipe.assert_not_called()


def test_recipe_create_embed_docs(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input",
            "documents",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created embed-docs recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("embed_documents", "doc_embed")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_not_called()
    builder.with_output_knowledge_bank.assert_called_once()
    builder.build.assert_called_once()


def test_recipe_create_embed_docs_with_vlm(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input",
            "documents",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--vlm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_called_once_with("openai:gpt-4o")


def test_recipe_create_extract(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-extract",
            "my_extract",
            "--input",
            "documents",
            "--output-ds",
            "extracted_text",
            "--vlm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created extract recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("extract_content", "my_extract")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("documents")
    builder.with_vlm.assert_called_once_with("openai:gpt-4o")
    builder.with_existing_output.assert_called_once_with("extracted_text")
    builder.build.assert_called_once()


def test_recipe_create_llm_eval_minimal(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "my_eval",
            "--input",
            "responses",
            "--eval-store",
            "eval_store_1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created LLM eval recipe" in result.output
    proj.new_recipe.assert_called_once_with("nlp_llm_evaluation", "my_eval")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("responses")
    builder.with_output_evaluation_store.assert_called_once_with("eval_store_1")
    builder.with_output.assert_not_called()
    builder.with_output_metrics.assert_not_called()
    builder.build.assert_called_once()


def test_recipe_create_llm_eval_full(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-ds",
            "eval_scored",
            "--output-metrics",
            "eval_metrics",
            "--task-type",
            "QUESTION_ANSWERING",
            "--metrics",
            "answerRelevancy,faithfulness",
            "--input-col",
            "question",
            "--output-col",
            "answer",
            "--ground-truth-col",
            "expected",
            "--context-col",
            "context",
            "--completion-llm",
            "openai:gpt-4o",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("qa_data")
    builder.with_output_evaluation_store.assert_called_once_with("eval_store_1")
    builder.with_output.assert_called_once_with("eval_scored")
    builder.with_output_metrics.assert_called_once_with("eval_metrics")

    # Verify post-creation payload settings
    recipe = builder.build.return_value
    settings = recipe.get_settings.return_value
    payload = settings.obj_payload
    assert payload["taskType"] == "QUESTION_ANSWERING"
    assert payload["metrics"] == ["answerRelevancy", "faithfulness"]
    assert payload["inputColumnName"] == "question"
    assert payload["outputColumnName"] == "answer"
    assert payload["groundTruthColumnName"] == "expected"
    assert payload["contextColumnName"] == "context"
    assert payload["completionLLMId"] == "openai:gpt-4o"
    assert payload["embeddingLLMId"] == "openai:text-embedding-3-small"
    settings.save.assert_called()


def test_recipe_create_llm_eval_initializes_missing_payload(patch_client):
    from unittest.mock import PropertyMock

    proj = patch_client.get_project("PROJ1")
    recipe = proj.new_recipe.return_value.build.return_value
    settings = recipe.get_settings.return_value
    # obj_payload is a read-only property that returns None (no payload yet)
    type(settings).obj_payload = PropertyMock(return_value=None)
    # Provide raw_params dict so _get_recipe_payload can write to it
    settings.raw_params = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--task-type",
            "QUESTION_ANSWERING",
            "--project",
            "PROJ1",
        ],
    )

    assert result.exit_code == 0
    # _get_recipe_payload falls through to raw_params when obj_payload is None
    assert settings.raw_params["payload"]["taskType"] == "QUESTION_ANSWERING"
    settings.save.assert_called()


def test_recipe_create_llm_eval_requires_existing_output_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")
    dataset_mock = proj.get_dataset("eval_scored")
    dataset_mock.get_definition.side_effect = Exception(
        "NotFoundException: dataset does not exist"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-ds",
            "eval_scored",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Output dataset 'eval_scored'" in result.output
    assert "then retry" in result.output
    proj.new_recipe.assert_not_called()


def test_recipe_create_llm_eval_requires_existing_metrics_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")

    def _get_dataset(name):
        dataset = proj.get_dataset.return_value
        if name == "eval_metrics":
            dataset.get_definition.side_effect = Exception(
                "NotFoundException: dataset does not exist"
            )
        return dataset

    proj.get_dataset.side_effect = _get_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-metrics",
            "eval_metrics",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Metrics output dataset 'eval_metrics'" in result.output
    proj.new_recipe.assert_not_called()


def test_recipe_create_llm_eval_preserves_non_not_found_dataset_errors(patch_client):
    proj = patch_client.get_project("PROJ1")
    dataset_mock = proj.get_dataset("eval_scored")
    dataset_mock.get_definition.side_effect = Exception("403 Forbidden")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-ds",
            "eval_scored",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Permission denied" in result.output
    proj.new_recipe.assert_not_called()


def test_recipe_create_agent_eval_minimal(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent eval recipe" in result.output
    proj.new_recipe.assert_called_once_with("nlp_agent_evaluation", "agent_eval")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("agent_runs")
    builder.with_output_evaluation_store.assert_called_once_with("agent_store_1")

    # Default input format
    recipe = builder.build.return_value
    settings = recipe.get_settings.return_value
    assert settings.obj_payload["inputFormat"] == "AGENT_EXECUTION"
    settings.save.assert_called()


def test_recipe_create_agent_eval_requires_existing_output_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")
    dataset_mock = proj.get_dataset("eval_out")
    dataset_mock.get_definition.side_effect = Exception(
        "NotFoundException: dataset does not exist"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--output-ds",
            "eval_out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Output dataset 'eval_out'" in result.output
    proj.new_recipe.assert_not_called()


def test_recipe_create_agent_eval_requires_existing_metrics_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")

    def _get_dataset(name):
        dataset = proj.get_dataset.return_value
        if name == "eval_metrics":
            dataset.get_definition.side_effect = Exception(
                "NotFoundException: dataset does not exist"
            )
        return dataset

    proj.get_dataset.side_effect = _get_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--output-metrics",
            "eval_metrics",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Metrics output dataset 'eval_metrics'" in result.output
    proj.new_recipe.assert_not_called()


def test_recipe_create_agent_eval_full(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--output-ds",
            "eval_out",
            "--output-metrics",
            "eval_metrics",
            "--metrics",
            "toolCallExactMatch,agentGoalAccuracyWithoutReference",
            "--completion-llm",
            "openai:gpt-4o",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--input-format",
            "PROMPT_RECIPE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_recipe.return_value
    builder.with_output.assert_called_once_with("eval_out")
    builder.with_output_metrics.assert_called_once_with("eval_metrics")

    recipe = builder.build.return_value
    settings = recipe.get_settings.return_value
    payload = settings.obj_payload
    assert payload["inputFormat"] == "PROMPT_RECIPE"
    assert payload["metrics"] == [
        "toolCallExactMatch",
        "agentGoalAccuracyWithoutReference",
    ]
    assert payload["completionLLMId"] == "openai:gpt-4o"
    assert payload["embeddingLLMId"] == "openai:text-embedding-3-small"


def test_recipe_get_json_error_payload(patch_client):
    # get_recipe() is lazy; the existence check happens on get_settings()
    patch_client.get_project(
        "PROJ1"
    ).get_recipe.return_value.get_settings.side_effect = Exception("'recipe'")
    result = runner.invoke(
        app,
        ["--errors", "json", "recipe", "get", "missing_recipe", "--project", "PROJ1"],
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    parsed = json.loads(result.stderr)
    assert parsed["error"]["code"] == "not_found"
    assert parsed["error"]["exit_code"] == 3
    assert (
        parsed["error"]["message"]
        == "Recipe 'missing_recipe' not found in project 'PROJ1'."
    )
    assert parsed["error"]["details"] == [
        "List recipes: dku recipe list -P PROJ1",
        "Inspect the project flow: dku project inspect PROJ1 -o json",
    ]


# ── Schema inspection commands ───────────────────────────────────────


def test_recipe_check_schema_no_changes(patch_client):
    """check-schema exits 0 when no changes needed."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "no schema updates" in result.output.lower()


def test_recipe_check_schema_changes_needed(patch_client):
    """check-schema exits 1 when changes are needed."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe("recipe1")
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True
    updates.data = {
        "totalIncompatibilities": 2,
        "computables": [
            {
                "datasetName": "output_ds",
                "type": "DATASET",
                "newSchema": {
                    "columns": [
                        {"name": "col1", "type": "string"},
                        {"name": "col2", "type": "int"},
                    ]
                },
                "schemaChanged": True,
            }
        ],
    }
    result = runner.invoke(
        app,
        [
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "schema updates required" in result.output.lower()


def test_recipe_check_schema_json(patch_client):
    """check-schema JSON output."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert "totalIncompatibilities" in result.output


def test_recipe_apply_schema_no_changes(patch_client):
    """apply-schema does nothing when no changes needed."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "apply-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "no schema updates" in result.output.lower()


def test_recipe_apply_schema_with_changes(patch_client):
    """apply-schema applies updates when changes exist."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe("recipe1")
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True
    updates.data = {"totalIncompatibilities": 1, "computables": []}
    updates.apply.return_value = [{"status": "ok"}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "apply-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "applied" in result.output.lower()
    updates.apply.assert_called_once()


# ── Visual recipe: create-join ────────────────────────────────────────


def test_recipe_create_join(patch_client):
    """Basic join recipe creation with 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created LEFT join recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("join", "my_join")
    builder = proj.new_recipe.return_value
    assert builder.with_input.call_count == 2
    builder.with_existing_output.assert_called_once_with("joined_data")
    builder.build.assert_called_once()


def test_recipe_create_join_requires_two_inputs(patch_client):
    """Join needs >= 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "at least 2" in result.output


def test_recipe_create_join_with_join_key(patch_client):
    """--join-key adds EQ condition to first join."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-key",
            "customer_id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(join_dict["on"]) == 1
    assert join_dict["on"][0]["column1"]["name"] == "customer_id"
    assert join_dict["on"][0]["column2"]["name"] == "customer_id"
    assert join_dict["on"][0]["type"] == "EQ"
    settings.save.assert_called()


def test_recipe_create_join_with_different_column_names(patch_client):
    """--join-key col1=col2 maps different column names."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-key",
            "order_cust_id=id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert join_dict["on"][0]["column1"]["name"] == "order_cust_id"
    assert join_dict["on"][0]["column2"]["name"] == "id"


def test_recipe_create_join_multiple_keys(patch_client):
    """Multiple --join-key flags add multiple conditions."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-key",
            "customer_id",
            "--join-key",
            "region=region_code",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(join_dict["on"]) == 2
    assert join_dict["on"][0]["column1"]["name"] == "customer_id"
    assert join_dict["on"][1]["column1"]["name"] == "region"
    assert join_dict["on"][1]["column2"]["name"] == "region_code"


def test_recipe_create_join_no_key_backward_compat(patch_client):
    """Without --join-key, join recipe is created with default behavior."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created LEFT join recipe" in result.output
    # get_settings should NOT be called for join key configuration
    proj = patch_client.get_project("PROJ1")
    # builder.build is called, but no post-build settings modification
    proj.new_recipe.return_value.build.assert_called_once()


# ── Visual recipe: create-join --join-type and indexed keys ────────────


def _setup_join_mock(patch_client, num_joins=1):
    """Configure mock for join recipe tests with real dicts for raw_joins."""
    proj = patch_client.get_project("PROJ1")
    recipe_obj = proj.get_recipe.return_value
    settings = recipe_obj.get_settings.return_value
    mock_joins = [
        {"type": "LEFT", "on": [], "table1": 0, "table2": i + 1}
        for i in range(num_joins)
    ]
    type(settings).raw_joins = property(lambda self: mock_joins)
    return proj, settings, mock_joins


def test_recipe_create_join_with_join_type_inner(patch_client):
    """--join-type INNER sets type on all join pairs."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-type",
            "INNER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created INNER join recipe" in result.output
    assert mock_joins[0]["type"] == "INNER"


def test_recipe_create_join_cross_no_keys(patch_client):
    """CROSS join skips key configuration."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_cross",
            "-i",
            "records",
            "-i",
            "months",
            "--output-ds",
            "expanded",
            "--join-type",
            "CROSS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created CROSS join recipe" in result.output
    assert mock_joins[0]["type"] == "CROSS"


def test_recipe_create_join_cross_ignores_keys(patch_client):
    """CROSS join warns when --join-key is provided."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_cross",
            "-i",
            "records",
            "-i",
            "months",
            "--output-ds",
            "expanded",
            "--join-type",
            "CROSS",
            "--join-key",
            "id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "CROSS join ignores" in result.output


def test_recipe_create_join_invalid_type_error(patch_client):
    """Invalid join type raises error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "out",
            "--join-type",
            "FULL_OUTER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid join type" in result.output


def test_recipe_create_join_multi_input_indexed_keys(patch_client):
    """Indexed --join-key targets specific join pairs."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client, num_joins=2)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "multi_join",
            "-i",
            "main",
            "-i",
            "lookup_a",
            "-i",
            "lookup_b",
            "--output-ds",
            "enriched",
            "--join-key",
            "entity=company",
            "--join-key",
            "1:region=region_name",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Join 0 should have entity=company condition
    assert len(mock_joins[0]["on"]) >= 1
    assert mock_joins[0]["on"][0]["column1"]["name"] == "entity"
    # Join 1 should have region=region_name condition
    assert len(mock_joins[1]["on"]) >= 1
    assert mock_joins[1]["on"][0]["column1"]["name"] == "region"


def test_recipe_create_join_five_inputs_creates_four_join_pairs(patch_client):
    """With 5 inputs, the CLI extends raw_joins to 4 pairs (DSS's builder
    pre-creates only 1 pair, so we must fill the rest)."""
    # Simulate DSS's builder pre-creating a single default join pair for 2+ inputs.
    _proj, _settings, mock_joins = _setup_join_mock(patch_client, num_joins=1)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "five_way",
            "-i",
            "main",
            "-i",
            "dim_a",
            "-i",
            "dim_b",
            "-i",
            "dim_c",
            "-i",
            "dim_d",
            "--output-ds",
            "fully_enriched",
            "--join-key",
            "k0=a_key",
            "--join-key",
            "1:k1=b_key",
            "--join-key",
            "2:k2=c_key",
            "--join-key",
            "3:k3=d_key",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    # 5 inputs → 4 join pairs
    assert len(mock_joins) == 4
    # Each pair fans out from table 0 to tables 1..4
    for i, j in enumerate(mock_joins):
        assert j["table1"] == 0
        assert j["table2"] == i + 1
    # All four keys should be wired (not just the first)
    assert mock_joins[0]["on"][0]["column1"]["name"] == "k0"
    assert mock_joins[1]["on"][0]["column1"]["name"] == "k1"
    assert mock_joins[2]["on"][0]["column1"]["name"] == "k2"
    assert mock_joins[3]["on"][0]["column1"]["name"] == "k3"


# ── Visual recipe: create-pivot ────────────────────────────────────────


def test_recipe_create_pivot_basic(patch_client):
    """Basic pivot recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "long_data",
            "--output-ds",
            "wide_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created pivot recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("pivot", "my_pivot")


def test_recipe_create_pivot_with_keys(patch_client):
    """Pivot with row/column/value configuration."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created pivot recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    recipe_obj = proj.get_recipe("my_pivot")
    settings = recipe_obj.get_settings()
    settings.save.assert_called()


# ── Visual recipe: create-sampling ─────────────────────────────────────


def test_recipe_create_sampling_basic(patch_client):
    """Basic sampling recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sampling",
            "sample_1k",
            "-i",
            "big_data",
            "--output-ds",
            "sample",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created sampling recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("sampling", "sample_1k")


def test_recipe_create_sampling_with_method_and_size(patch_client):
    """Sampling with method and size configuration."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sampling",
            "sample_head",
            "-i",
            "data",
            "--output-ds",
            "head_sample",
            "--method",
            "HEAD_SEQUENTIAL",
            "--size",
            "500",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "HEAD_SEQUENTIAL" in result.output
    proj = patch_client.get_project("PROJ1")
    recipe_obj = proj.get_recipe("sample_head")
    settings = recipe_obj.get_settings()
    settings.save.assert_called()


# ── Visual recipe: create-sort with --sort-col ────────────────────────


def test_recipe_create_sort_with_sort_col(patch_client):
    """--sort-col configures sort column."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sort",
            "my_sort",
            "-i",
            "data",
            "--output-ds",
            "sorted",
            "--sort-col",
            "price",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "sort" in result.output.lower() or "Created" in result.output


def test_recipe_create_sort_desc(patch_client):
    """--sort-col col:desc sorts descending."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sort",
            "my_sort",
            "-i",
            "data",
            "--output-ds",
            "sorted",
            "--sort-col",
            "price:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# ── Visual recipe: create-topn with configuration ─────────────────────


def test_recipe_create_topn_basic(patch_client):
    """Basic topn creation with default N=10."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "my_topn",
            "-i",
            "data",
            "--output-ds",
            "top_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "top 10" in result.output
    assert settings.obj_payload["topN"] == 10
    settings.save.assert_called()


def test_recipe_create_topn_with_rank_by(patch_client):
    """--rank-by sets orders in payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "top5",
            "-i",
            "sales",
            "--output-ds",
            "top5_sales",
            "--n",
            "5",
            "--rank-by",
            "revenue:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "top 5" in result.output
    assert settings.obj_payload["topN"] == 5
    assert settings.obj_payload["orders"] == [{"column": "revenue", "desc": True}]


def test_recipe_create_topn_with_partition(patch_client):
    """--partition-key sets partitioningColumns for top N per group."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "top3_per_cat",
            "-i",
            "products",
            "--output-ds",
            "top_products",
            "--n",
            "3",
            "--rank-by",
            "price:desc",
            "--partition-key",
            "category",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["topN"] == 3
    assert settings.obj_payload["firstRows"] == 3
    assert settings.obj_payload["orders"] == [{"column": "price", "desc": True}]
    assert settings.obj_payload["keys"] == ["category"]


def test_recipe_create_topn_with_flags(patch_client):
    """--sort-col and --n configure topn recipe."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "my_topn",
            "-i",
            "data",
            "--output-ds",
            "top10",
            "--sort-col",
            "revenue:desc",
            "--n",
            "10",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["topN"] == 10
    assert settings.obj_payload["orders"] == [{"column": "revenue", "desc": True}]


# ── Visual recipe: create-pivot with --agg-type ──────────────────────


def test_recipe_create_pivot_with_agg_type(patch_client):
    """--agg-type sets valueFunctions in payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    pivots = settings.obj_payload["pivots"]
    assert pivots[0]["keyColumns"] == ["month"]
    assert pivots[0]["valueColumns"] == [{"column": "revenue", "function": "SUM"}]
    assert settings.obj_payload["explicitIdentifiers"] == ["product"]


def test_recipe_create_pivot_no_global_count(patch_client):
    """--no-global-count should flip pivots[0].globalCount to False."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    # Start the mocked payload as a dict so the CLI's .setdefault() works
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--no-global-count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["pivots"][0]["globalCount"] is False


def test_recipe_create_pivot_invalid_agg_type(patch_client):
    """--agg-type with unknown type gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--agg-type",
            "MEDIAN",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown aggregation type" in result.output


# ── Window recipe: --compute flag ─────────────────────────────────────


def test_recipe_create_window_with_compute_rank(patch_client):
    """--compute rowNumber::rn sets top-level boolean in payload AND warns that
    the custom output name won't be honored (DSS has no payload field for it)."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--partition-key",
            "customer_id",
            "--order-key",
            "date",
            "--compute",
            "rowNumber::rn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # rowNumber is a top-level boolean in DSS Window payload
    assert settings.obj_payload["rowNumber"] is True
    # User asked for `rn` but DSS will name it `rownumber` — warn loudly
    assert "does not support custom output column names" in result.output
    assert "→ column 'rownumber'" in result.output


def test_recipe_create_window_no_warning_when_name_matches_dss(patch_client):
    """When the user's custom name matches what DSS will produce, no warning."""
    # patch_client fixture seeds the recipe mock; we only need to invoke the CLI.
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w2",
            "-i",
            "data",
            "--output-ds",
            "out",
            "--partition-key",
            "cat",
            "--order-key",
            "id",
            # Explicit name that matches DSS's generated name
            "--compute",
            "rowNumber::rownumber",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "does not support custom output column names" not in result.output


def test_recipe_create_window_with_compute_lag(patch_client):
    """--compute lag:col:output enables lag on the column in values[]."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--partition-key",
            "customer_id",
            "--order-key",
            "date",
            "--compute",
            "lag:price:price_lag1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # lag is a per-column boolean in values[] array
    values = settings.obj_payload["values"]
    price_entry = next(v for v in values if v["column"] == "price")
    assert price_entry["lag"] is True


def test_recipe_create_window_multiple_computes(patch_client):
    """Multiple --compute flags: top-level + per-column."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--compute",
            "rowNumber::rn",
            "--compute",
            "sum:amount:cumulative_amount",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # rowNumber as top-level boolean
    assert settings.obj_payload["rowNumber"] is True
    # sum as per-column flag in values[]
    values = settings.obj_payload["values"]
    amount_entry = next(v for v in values if v["column"] == "amount")
    assert amount_entry["sum"] is True


def test_recipe_create_window_invalid_compute_type(patch_client):
    """--compute with unknown type gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "my_window",
            "-i",
            "transactions",
            "--output-ds",
            "windowed",
            "--compute",
            "median:price:price_med",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown window computation type" in result.output


def test_recipe_create_window_compute_missing_column(patch_client):
    """--compute sum without source column gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "my_window",
            "-i",
            "transactions",
            "--output-ds",
            "windowed",
            "--compute",
            "sum::cumsum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "requires a source column" in result.output


# ── set-definition --payload flag ─────────────────────────────────────


def test_recipe_set_definition_payload(patch_client):
    """--payload writes to obj_payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    new_payload = json.dumps({"topN": 5, "orders": [{"column": "price", "desc": True}]})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            new_payload,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated payload" in result.output
    settings.save.assert_called()


def test_recipe_set_definition_no_flag(patch_client):
    """Missing both --definition and --payload gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Provide either" in result.output


def test_recipe_set_definition_both_flags(patch_client):
    """Both --definition and --payload is an error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            '{"type": "python"}',
            "--payload",
            '{"topN": 5}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Cannot use both" in result.output


def test_recipe_set_definition_deep_merge(patch_client):
    """--deep-merge recursively merges nested payload objects."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {
        "topN": 5,
        "postFilter": {"enabled": False, "distinct": True},
        "keys": ["customer_id"],
    }

    # Deep merge should update postFilter.enabled without losing postFilter.distinct
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
    assert result.exit_code == 0
    assert "deep-merged" in result.output
    payload = settings.obj_payload
    assert payload["postFilter"]["enabled"] is True
    assert payload["postFilter"]["distinct"] is True  # preserved
    assert payload["topN"] == 5  # preserved
    assert payload["keys"] == ["customer_id"]  # preserved
    settings.save.assert_called()


def test_recipe_set_definition_deep_merge_replaces_non_dict(patch_client):
    """--deep-merge replaces non-dict values in patch."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"topN": 5, "keys": ["old_key"]}

    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            '{"topN": 10, "keys": ["new_key"]}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    payload = settings.obj_payload
    assert payload["topN"] == 10
    assert payload["keys"] == ["new_key"]


def test_recipe_set_definition_deep_merge_without_payload(patch_client):
    """--deep-merge without --payload is an error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            '{"type": "python"}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--deep-merge can only be used with --payload" in result.output


# ── Prepare step: add-fold ─────────────────────────────────────────────


def test_recipe_add_fold_by_name(patch_client):
    """Fold by explicit column names."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--columns",
            "jan,feb,mar",
            "--key-column",
            "month",
            "--value-column",
            "sales",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "MultiColumnFold" in result.output
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "MultiColumnFold"
    assert step["params"]["columns"] == ["jan", "feb", "mar"]
    assert step["params"]["foldNameColumn"] == "month"
    assert step["params"]["foldValueColumn"] == "sales"
    assert step["params"]["foldRemoveFoldedColumns"] is True


def test_recipe_add_fold_by_pattern(patch_client):
    """Fold by regex pattern."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--pattern",
            ".*-25",
            "--key-column",
            "month",
            "--value-column",
            "value",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "MultiColumnByPrefixFold" in result.output
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "MultiColumnByPrefixFold"
    assert step["params"]["columnNamePattern"] == ".*-25"
    assert step["params"]["columnNameColumn"] == "month"
    assert step["params"]["columnContentColumn"] == "value"
    assert step["params"]["foldRemoveFoldedColumns"] is True


def test_recipe_add_fold_requires_columns_or_pattern(patch_client):
    """Error when neither --columns nor --pattern given."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--key-column",
            "month",
            "--value-column",
            "sales",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Specify --columns or --pattern" in result.output


def test_recipe_add_fold_both_columns_and_pattern_error(patch_client):
    """Error when both --columns and --pattern given."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--columns",
            "jan,feb",
            "--pattern",
            ".*-25",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not both" in result.output


# ── Visual recipe: create-group with --agg ────────────────────────────


def test_recipe_create_group(patch_client):
    """Basic group recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("grouping", "my_group")
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")


def test_recipe_create_group_no_global_count(patch_client):
    """--no-global-count disables the DSS default per-group count column."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "tight_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum",
            "--no-global-count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.set_global_count_enabled.assert_called_once_with(False)
    settings.save.assert_called()


def test_recipe_create_group_with_agg(patch_client):
    """--agg configures column aggregations after build."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum,avg",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.set_column_aggregations.assert_called_once_with(
        "amount",
        sum=True,
        avg=True,
        min=False,
        max=False,
        count=False,
        count_distinct=False,
        concat=False,
        stddev=False,
    )
    settings.save.assert_called()


def test_recipe_create_group_multiple_agg(patch_client):
    """Multiple --agg flags configure different columns."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum,avg",
            "--agg",
            "order_id:count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.set_column_aggregations.call_count == 2


def test_recipe_create_group_invalid_agg_format(patch_client):
    """--agg without colon gives clear error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "--agg",
            "amount_sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --agg format" in result.output


def test_recipe_create_group_invalid_agg_function(patch_client):
    """--agg with unknown function gives clear error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "--agg",
            "amount:median",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown aggregation" in result.output


def test_recipe_create_group_no_agg_backward_compat(patch_client):
    """Without --agg, group recipe uses default COUNT behavior."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output


def test_recipe_create_group_multi_key(patch_client):
    """Multiple -k flags add all grouping keys."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "-k",
            "category",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")
    settings.add_grouping_key.assert_called_once_with("category")
    settings.save.assert_called()


def test_recipe_create_group_three_keys(patch_client):
    """Three -k flags: first to builder, remaining via settings."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "-k",
            "category",
            "-k",
            "year",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")
    assert settings.add_grouping_key.call_count == 2
    settings.add_grouping_key.assert_any_call("category")
    settings.add_grouping_key.assert_any_call("year")


def test_recipe_create_group_multi_key_with_agg(patch_client):
    """Multi-key plus aggregation in single settings call."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "-k",
            "category",
            "--agg",
            "amount:sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.add_grouping_key.assert_called_once_with("category")
    settings.set_column_aggregations.assert_called_once()
    settings.save.assert_called()


# ── Auto apply-schema ─────────────────────────────────────────────────


def test_visual_recipe_auto_applies_schema(patch_client):
    """Visual recipe creation auto-applies schema updates."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    updates.apply.assert_called_once()


def test_auto_apply_schema_failure_warns_not_crashes(patch_client):
    """Schema auto-apply failure emits warning, doesn't crash."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    recipe_mock.compute_schema_updates.side_effect = Exception("schema error")

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "deduped",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created distinct recipe" in result.output


def test_recipe_create_distinct_defaults_to_all_input_columns(patch_client):
    """Without --on, create-distinct populates keys with every input column.

    Prevents the silent bug where DSS defaults to keys=[first_col] +
    selectAllColumns=false, which projects the output to a single column.
    """
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [
            {"name": "customer_id", "type": "string"},
            {"name": "order_date", "type": "date"},
            {"name": "amount", "type": "double"},
        ]
    }
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "dedup",
            "-i",
            "orders",
            "--output-ds",
            "unique_orders",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["keys"] == [
        {"column": "customer_id"},
        {"column": "order_date"},
        {"column": "amount"},
    ]
    assert settings.obj_payload["selectAllColumns"] is True
    settings.save.assert_called()


def test_recipe_create_distinct_with_explicit_on_flag(patch_client):
    """--on col1 --on col2 sets only the specified keys (skips schema lookup)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "dedup",
            "-i",
            "orders",
            "--output-ds",
            "unique_per_customer",
            "--on",
            "customer_id",
            "--on",
            "order_date",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["keys"] == [
        {"column": "customer_id"},
        {"column": "order_date"},
    ]
    assert settings.obj_payload["selectAllColumns"] is True


# ── Dynamic connection discovery ──────────────────────────────────────


def test_ensure_output_finds_managed_connection(patch_client):
    """Uses first connection with allowManagedDatasets=True."""
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_definition.side_effect = Exception(
        "NotFoundException"
    )

    patch_client.list_connections.return_value = {
        "my_sql_conn": {"type": "PostgreSQL", "allowManagedDatasets": False},
        "s3_managed": {"type": "S3", "allowManagedDatasets": True},
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "new_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("s3_managed")


def test_ensure_output_falls_back_on_permission_error(patch_client):
    """Falls back to filesystem_managed when list_connections fails (403)."""
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_definition.side_effect = Exception(
        "NotFoundException"
    )
    patch_client.list_connections.side_effect = Exception("403 Forbidden")

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "new_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_managed")


# ---------------------------------------------------------------------------
# Prepare recipe step commands
# ---------------------------------------------------------------------------


def _setup_prepare_mock(patch_client, steps=None):
    """Configure mock for prepare recipe tests. Returns (proj, recipe_mock, settings)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "shaker",
        "name": "prep1",
    }
    payload = {"steps": list(steps) if steps else []}
    settings.obj_payload = payload
    settings.raw_steps = payload["steps"]
    settings._obj_payload = payload
    return proj, recipe_mock, settings


# -- list-steps --


def test_recipe_list_steps_empty(patch_client):
    _setup_prepare_mock(patch_client, steps=[])
    result = runner.invoke(app, ["recipe", "list-steps", "prep1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "No steps" in result.output


def test_recipe_list_steps_table(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[
            {
                "metaType": "PROCESSOR",
                "type": "ColumnRenamer",
                "name": "Rename cols",
                "params": {"renamings": [{"from": "a", "to": "b"}]},
            },
            {
                "metaType": "PROCESSOR",
                "type": "CreateColumnWithGREL",
                "params": {"expression": "upper(city)", "column": "city_upper"},
            },
        ],
    )
    result = runner.invoke(app, ["recipe", "list-steps", "prep1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ColumnRenamer" in result.output
    assert "CreateColumnWithGREL" in result.output


def test_recipe_list_steps_json(patch_client):
    steps = [
        {"metaType": "PROCESSOR", "type": "ColumnRenamer", "params": {"renamings": []}},
    ]
    _setup_prepare_mock(patch_client, steps=steps)
    result = runner.invoke(
        app, ["recipe", "list-steps", "prep1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["type"] == "ColumnRenamer"


def test_recipe_list_steps_wrong_type(patch_client):
    """Non-prepare recipe gives prescriptive error."""
    # Default mock returns type: "python"
    result = runner.invoke(
        app, ["recipe", "list-steps", "recipe1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "not 'prepare'" in result.output


# -- add-step --


def test_recipe_add_step_basic(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "ColumnRenamer",
            "--params",
            '{"renamings":[{"from":"a","to":"b"}]}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 1
    assert settings.obj_payload["steps"][0]["type"] == "ColumnRenamer"
    settings.save.assert_called_once()


def test_recipe_add_step_at_index(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
            {"metaType": "PROCESSOR", "type": "Step1", "params": {}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "Inserted",
            "--params",
            "{}",
            "--at",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][1]["type"] == "Inserted"
    assert len(settings.obj_payload["steps"]) == 3


def test_recipe_add_step_with_name(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "FillEmptyWithValue",
            "--params",
            '{"column":"age","value":"0"}',
            "--name",
            "Fill missing ages",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["name"] == "Fill missing ages"
    assert step["type"] == "FillEmptyWithValue"


def test_recipe_add_step_wrong_type(patch_client):
    """Non-prepare recipe gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "recipe1",
            "--type",
            "ColumnRenamer",
            "--params",
            "{}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not 'prepare'" in result.output


# -- remove-step --


def test_recipe_remove_step_single(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
            {"metaType": "PROCESSOR", "type": "Step1", "params": {}},
            {"metaType": "PROCESSOR", "type": "Step2", "params": {}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "remove-step",
            "prep1",
            "--index",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 2
    assert settings.obj_payload["steps"][0]["type"] == "Step0"
    assert settings.obj_payload["steps"][1]["type"] == "Step2"
    settings.save.assert_called_once()


def test_recipe_remove_step_multiple(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": f"Step{i}", "params": {}}
            for i in range(4)
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "remove-step",
            "prep1",
            "--index",
            "0",
            "--index",
            "3",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 2
    assert settings.obj_payload["steps"][0]["type"] == "Step1"
    assert settings.obj_payload["steps"][1]["type"] == "Step2"


def test_recipe_remove_step_out_of_range(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "remove-step",
            "prep1",
            "--index",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


# -- get-step --


def test_recipe_get_step(patch_client):
    step = {
        "metaType": "PROCESSOR",
        "type": "CreateColumnWithGREL",
        "params": {"expression": "upper(x)", "column": "y"},
    }
    _setup_prepare_mock(patch_client, steps=[step])
    result = runner.invoke(
        app,
        [
            "recipe",
            "get-step",
            "prep1",
            "--index",
            "0",
            "-o",
            "json",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "CreateColumnWithGREL"
    assert parsed["params"]["expression"] == "upper(x)"


def test_recipe_get_step_out_of_range(patch_client):
    _setup_prepare_mock(patch_client, steps=[])
    result = runner.invoke(
        app,
        [
            "recipe",
            "get-step",
            "prep1",
            "--index",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "no steps" in result.output.lower()


# -- disable-step / enable-step --


def test_recipe_disable_step(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "disable-step",
            "prep1",
            "--index",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][0]["disabled"] is True
    settings.save.assert_called_once()


def test_recipe_enable_step(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Step0", "params": {}, "disabled": True},
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "enable-step",
            "prep1",
            "--index",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][0]["disabled"] is False
    settings.save.assert_called_once()


def test_recipe_disable_step_multiple(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": f"Step{i}", "params": {}}
            for i in range(3)
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "disable-step",
            "prep1",
            "--index",
            "0",
            "--index",
            "2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][0]["disabled"] is True
    assert settings.obj_payload["steps"][2]["disabled"] is True


# ---------------------------------------------------------------------------
# Prepare recipe step shortcuts
# ---------------------------------------------------------------------------


def test_recipe_add_formula(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-formula",
            "prep1",
            "--expr",
            "upper(city)",
            "--column",
            "city_upper",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "CreateColumnWithGREL"
    assert step["params"]["expression"] == "upper(city)"
    assert step["params"]["column"] == "city_upper"
    settings.save.assert_called_once()


def test_recipe_add_rename_single(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-rename",
            "prep1",
            "--from",
            "old_name",
            "--to",
            "new_name",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "ColumnRenamer"
    assert step["params"]["renamings"] == [{"from": "old_name", "to": "new_name"}]


def test_recipe_add_rename_bulk(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-rename",
            "prep1",
            "--mappings",
            '{"col_a":"column_a","col_b":"column_b"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    renamings = settings.obj_payload["steps"][0]["params"]["renamings"]
    assert len(renamings) == 2
    names = {r["from"] for r in renamings}
    assert names == {"col_a", "col_b"}


def test_recipe_add_rename_validation(patch_client):
    """--from without --to gives error."""
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-rename",
            "prep1",
            "--from",
            "old_name",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--from" in result.output or "--to" in result.output


def test_recipe_add_filter_rows_by_value(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--column",
            "status",
            "--values",
            "active,pending",
            "--action",
            "KEEP_ROW",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FilterOnValue"
    assert step["params"]["columns"] == ["status"]
    assert step["params"]["values"] == ["active", "pending"]
    assert step["params"]["action"] == "KEEP_ROW"


def test_recipe_add_filter_rows_by_formula(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--formula",
            "price > 100",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FilterOnCustomFormula"
    assert step["params"]["expression"] == "price > 100"
    assert step["params"]["action"] == "REMOVE_ROW"


def test_recipe_add_fill_empty(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fill-empty",
            "prep1",
            "--column",
            "age",
            "--value",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FillEmptyWithValue"
    assert step["params"]["columns"] == ["age"]
    assert step["params"]["value"] == "0"


def test_recipe_add_delete_columns(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-delete-columns",
            "prep1",
            "--columns",
            "tmp1,tmp2,debug_col",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "ColumnsSelector"
    assert step["params"]["columns"] == ["tmp1", "tmp2", "debug_col"]
    assert step["params"]["keep"] is False


def test_recipe_add_find_replace(patch_client):
    """Default --matching is SUBSTRING."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-find-replace",
            "prep1",
            "--column",
            "category",
            "--find",
            "Electronics",
            "--replace",
            "Tech",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FindReplace"
    assert step["params"]["columns"] == ["category"]
    assert step["params"]["mapping"] == [{"from": "Electronics", "to": "Tech"}]
    assert step["params"]["matching"] == "SUBSTRING"


def test_recipe_add_find_replace_full_string_opt_in(patch_client):
    """Exact-match mode is opt-in via --matching FULL_STRING."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-find-replace",
            "prep1",
            "--column",
            "status",
            "--find",
            "ACTIVE",
            "--replace",
            "active",
            "--matching",
            "FULL_STRING",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["matching"] == "FULL_STRING"


# ── Visual recipe: create-window with --partition-key / --order-key ────


def test_recipe_create_window_basic(patch_client):
    """Basic window recipe creation without flags."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "my_window",
            "-i",
            "transactions",
            "--output-ds",
            "windowed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created window recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("window", "my_window")


def test_recipe_create_window_with_partition_key(patch_client):
    """--partition-key sets partitioningColumns in payload.

    Writes both to top-level (for backwards compat) AND nested under
    windows[0] with enablePartitioning=true (DSS's canonical location).
    Writing only to top-level causes the Window recipe to silently ignore
    partitioning and produce global aggregations.
    """
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
            "transactions",
            "--output-ds",
            "windowed",
            "--partition-key",
            "customer_id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Top-level (backwards compat)
    assert settings.obj_payload["partitioningColumns"] == [{"column": "customer_id"}]
    # Nested windows[0] (canonical) — enable flag MUST be true
    win0 = settings.obj_payload["windows"][0]
    assert win0["enablePartitioning"] is True
    assert win0["partitioningColumns"] == ["customer_id"]
    settings.save.assert_called()


def test_recipe_create_window_partition_and_order_sets_enable_flags(patch_client):
    """Partition + order both set their enable flags inside windows[0]."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--partition-key",
            "customer_id",
            "--order-key",
            "last_update_date:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    win0 = settings.obj_payload["windows"][0]
    assert win0["enablePartitioning"] is True
    assert win0["partitioningColumns"] == ["customer_id"]
    assert win0["enableOrdering"] is True
    assert win0["orders"] == [{"column": "last_update_date", "desc": True}]


def test_recipe_create_window_with_order_key(patch_client):
    """--order-key sets orders in payload (ascending by default)."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--order-key",
            "date",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["orders"] == [{"column": "date", "desc": False}]
    settings.save.assert_called()


def test_recipe_create_window_order_key_desc(patch_client):
    """--order-key with :desc suffix sets descending order."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--partition-key",
            "customer_id",
            "--order-key",
            "amount:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["partitioningColumns"] == [{"column": "customer_id"}]
    assert settings.obj_payload["orders"] == [{"column": "amount", "desc": True}]
    settings.save.assert_called()


def test_recipe_create_window_multiple_keys(patch_client):
    """Multiple --partition-key and --order-key flags."""
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
            "transactions",
            "--output-ds",
            "windowed",
            "--partition-key",
            "customer_id",
            "--partition-key",
            "region",
            "--order-key",
            "date",
            "--order-key",
            "amount:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["partitioningColumns"] == [
        {"column": "customer_id"},
        {"column": "region"},
    ]
    assert settings.obj_payload["orders"] == [
        {"column": "date", "desc": False},
        {"column": "amount", "desc": True},
    ]


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
    creation_settings = call_args[0][1]
    assert creation_settings["rawCreation"] is True
    raw_payload = json.loads(creation_settings["rawPayload"])
    assert raw_payload == {"mode": "advanced", "threshold": 0.5}


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
    raw_payload = json.loads(proj.create_recipe.call_args[0][1]["rawPayload"])
    assert raw_payload == {"key": "value"}


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
            "recipe",
            "get-settings",
            "recipe1",
            "--project",
            "PROJ1",
            "-o",
            "json",
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
        ["recipe", "get-settings", "my_py", "--project", "PROJ1", "-o", "json"],
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
        ["recipe", "get-settings", "extract", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["type"] == "sql_query"
    assert parsed["payload"] == "SELECT id, name FROM t WHERE active = 1"

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
# Geo Join recipe tests
# ---------------------------------------------------------------------------


def _setup_geojoin_mock(patch_client):
    """Configure mock for geo join recipe tests, patching the direct creator."""
    from unittest.mock import patch

    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"joins": [{"table1": 0, "table2": 1, "on": []}]}
    settings._obj_payload = settings.obj_payload

    builder = MagicMock()
    builder.with_input.return_value = builder
    builder.with_existing_output.return_value = builder
    builder.build.return_value = recipe_mock

    patcher = patch(
        "dku_cli.commands.recipe.GeoJoinRecipeCreator", return_value=builder
    )
    mock_cls = patcher.start()
    return proj, builder, settings, mock_cls, patcher


def test_recipe_create_geojoin(patch_client):
    """Basic geo join recipe creation with 2 inputs."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "stores",
                "-i",
                "customers",
                "--output-ds",
                "nearby",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        assert "Created geo join recipe" in result.output
        mock_cls.assert_called_once_with("my_geojoin", proj)
        assert builder.with_input.call_count == 2
        builder.with_existing_output.assert_called_once_with("nearby")
        builder.build.assert_called_once()
    finally:
        patcher.stop()


def test_recipe_create_geojoin_requires_exactly_two_inputs(patch_client):
    """Geo join needs exactly 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly 2" in result.output


def test_recipe_create_geojoin_rejects_three_inputs(patch_client):
    """Geo join rejects 3 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "-i",
            "ds3",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly 2" in result.output


def test_recipe_create_geojoin_invalid_operator(patch_client):
    """Invalid geo operator gives prescriptive error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--operator",
            "INVALID",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid geo operator" in result.output


def test_recipe_create_geojoin_invalid_distance_unit(patch_client):
    """Invalid distance unit gives prescriptive error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--distance-unit",
            "parsec",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid distance unit" in result.output


def test_recipe_create_geojoin_with_operator(patch_client):
    """--operator INTERSECTS sets geo join operator."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--operator",
                "INTERSECTS",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        assert "INTERSECTS" in result.output
        geo_join = settings.obj_payload["joins"][0]
        assert geo_join["geoOperator"] == "INTERSECTS"
        assert geo_join["geoJoin"] is True
    finally:
        patcher.stop()


def test_recipe_create_geojoin_with_distance(patch_client):
    """--distance and --distance-unit configure distance threshold."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--distance",
                "5000",
                "--distance-unit",
                "km",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        geo_join = settings.obj_payload["joins"][0]
        assert geo_join["geoDistance"] == 5000.0
        assert geo_join["geoUnit"] == "km"
    finally:
        patcher.stop()


def test_recipe_create_geojoin_with_geo_columns(patch_client):
    """--geo-column specifies left and right geo columns."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "-g",
                "location_left",
                "-g",
                "location_right",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        geo_join = settings.obj_payload["joins"][0]
        assert geo_join["geoColumn1"] == "location_left"
        assert geo_join["geoColumn2"] == "location_right"
    finally:
        patcher.stop()


def test_recipe_create_geojoin_geo_columns_requires_two(patch_client):
    """--geo-column must be specified exactly twice."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "-g",
            "only_one",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly twice" in result.output


def test_recipe_create_geojoin_auto_applies_schema(patch_client):
    """Schema auto-propagation happens after creation."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        recipe_mock = proj.get_recipe.return_value
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        # _auto_apply_schema calls compute_schema_updates().apply()
        recipe_mock.compute_schema_updates.assert_called()
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Fuzzy Join recipe tests
# ---------------------------------------------------------------------------


def _setup_fuzzyjoin_mock(patch_client):
    """Configure mock for fuzzy join recipe tests, patching the direct creator."""
    from unittest.mock import patch

    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"joins": [{"table1": 0, "table2": 1, "on": []}]}
    settings._obj_payload = settings.obj_payload

    builder = MagicMock()
    builder.with_input.return_value = builder
    builder.with_existing_output.return_value = builder
    builder.build.return_value = recipe_mock

    patcher = patch(
        "dku_cli.commands.recipe.FuzzyJoinRecipeCreator", return_value=builder
    )
    mock_cls = patcher.start()
    return proj, builder, settings, mock_cls, patcher


def test_recipe_create_fuzzy_join(patch_client):
    """Basic fuzzy join recipe creation."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "matched",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        assert "Created fuzzy join recipe" in result.output
        mock_cls.assert_called_once_with("my_fuzzy", proj)
        assert builder.with_input.call_count == 2
        builder.with_existing_output.assert_called_once_with("matched")
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_requires_two_inputs(patch_client):
    """Fuzzy join needs exactly 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-fuzzy-join",
            "my_fuzzy",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly 2" in result.output


def test_recipe_create_fuzzy_join_invalid_method(patch_client):
    """Invalid fuzzy method gives prescriptive error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-fuzzy-join",
            "my_fuzzy",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--method",
            "SOUNDEX",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid fuzzy method" in result.output


def test_recipe_create_fuzzy_join_with_fuzzy_key(patch_client):
    """--fuzzy-key adds FUZZY condition to join."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--fuzzy-key",
                "name",
                "--max-distance",
                "3",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        fj = settings.obj_payload["joins"][0]
        assert fj["fuzzyJoinMethod"] == "LEVENSHTEIN"
        assert fj["fuzzyJoinMaxDistance"] == 3
        assert len(fj["on"]) == 1
        assert fj["on"][0]["type"] == "FUZZY"
        assert fj["on"][0]["column1"]["name"] == "name"
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_with_exact_and_fuzzy_keys(patch_client):
    """Both --join-key (exact) and --fuzzy-key can be combined."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--join-key",
                "city",
                "--fuzzy-key",
                "name",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        fj = settings.obj_payload["joins"][0]
        conditions = fj["on"]
        assert len(conditions) == 2
        fuzzy_conds = [c for c in conditions if c["type"] == "FUZZY"]
        eq_conds = [c for c in conditions if c["type"] == "EQ"]
        assert len(fuzzy_conds) == 1
        assert len(eq_conds) == 1
        assert fuzzy_conds[0]["column1"]["name"] == "name"
        assert eq_conds[0]["column1"]["name"] == "city"
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_left_right_key(patch_client):
    """Fuzzy key with left=right syntax."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--fuzzy-key",
                "first_name=fname",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["column1"]["name"] == "first_name"
        assert cond["column2"]["name"] == "fname"
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Geo prepare shortcut tests
# ---------------------------------------------------------------------------


def test_recipe_add_geopoint(patch_client):
    """add-geopoint creates GeoPointCreator step."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geopoint",
            "prep1",
            "--lat-column",
            "latitude",
            "--lon-column",
            "longitude",
            "--output-column",
            "location",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "GeoPointCreator"
    assert step["params"]["lat_column"] == "latitude"
    assert step["params"]["lon_column"] == "longitude"
    assert step["params"]["out_column"] == "location"
    settings.save.assert_called_once()


def test_recipe_add_geopoint_default_column(patch_client):
    """Default output column is 'geopoint'."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geopoint",
            "prep1",
            "--lat-column",
            "lat",
            "--lon-column",
            "lon",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["out_column"] == "geopoint"


def test_recipe_add_geodistance(patch_client):
    """add-geodistance creates GeoDistanceProcessor step."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from-column",
            "origin",
            "--to-column",
            "destination",
            "--output-column",
            "dist_km",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "GeoDistanceProcessor"
    assert step["params"]["input1_column"] == "origin"
    assert step["params"]["input2_column"] == "destination"
    assert step["params"]["output_column"] == "dist_km"
    settings.save.assert_called_once()


def test_recipe_add_geodistance_default_output(patch_client):
    """Default output column is 'geo_distance'."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from-column",
            "origin",
            "--to-column",
            "destination",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["output_column"] == "geo_distance"
