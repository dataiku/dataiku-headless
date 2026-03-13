"""Tests for recipe commands."""

from __future__ import annotations

import json

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
    result = runner.invoke(app, ["recipe", "get", "recipe1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "type" in parsed


def test_recipe_run(patch_client):
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_recipe_run_wait(patch_client):
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1", "--wait"])
    assert result.exit_code == 0


# --- New commands ---


def test_recipe_create(patch_client):
    result = runner.invoke(app, [
        "recipe", "create", "new_recipe",
        "--type", "python",
        "--input", "input_ds",
        "--output", "output_ds",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("python", "new_recipe")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("input_ds")
    builder.with_existing_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_delete(patch_client):
    result = runner.invoke(app, ["recipe", "delete", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted recipe" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.delete.assert_called_once()


def test_recipe_set_code_inline(patch_client):
    result = runner.invoke(app, [
        "recipe", "set-code", "recipe1",
        "--code", "print('hello')",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Updated code" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.set_payload.assert_called_once_with("print('hello')")
    settings.save.assert_called()


def test_recipe_set_code_from_file(patch_client, tmp_path):
    code_file = tmp_path / "script.py"
    code_file.write_text("import dataiku\nds = dataiku.Dataset('test')")
    result = runner.invoke(app, [
        "recipe", "set-code", "recipe1",
        "--code", f"@{code_file}",
        "--project", "PROJ1",
    ])
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
    assert "import dataiku" in result.output


def test_recipe_set_definition(patch_client):
    new_def = json.dumps({"type": "sql", "customFields": {"key": "val"}})
    result = runner.invoke(app, [
        "recipe", "set-definition", "recipe1",
        "--definition", new_def,
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.save.assert_called()


def test_recipe_add_input(patch_client):
    result = runner.invoke(app, [
        "recipe", "add-input", "recipe1",
        "--ref", "extra_input",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Added input" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("main", "extra_input")
    settings.save.assert_called()


def test_recipe_add_output(patch_client):
    result = runner.invoke(app, [
        "recipe", "add-output", "recipe1",
        "--ref", "extra_output",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Added output" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_output.assert_called_once_with("main", "extra_output")
    settings.save.assert_called()


def test_recipe_add_input_custom_role(patch_client):
    result = runner.invoke(app, [
        "recipe", "add-input", "recipe1",
        "--ref", "lookup_ds",
        "--role", "lookup",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("lookup", "lookup_ds")
