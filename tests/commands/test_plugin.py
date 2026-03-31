"""Tests for plugin commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock
from zipfile import ZipFile

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _write_plugin_zip(path, plugin_id: str) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "plugin.json", json.dumps({"id": plugin_id, "version": "1.0.0"})
        )


def test_plugin_list_table(patch_client):
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "my-plugin" in result.output


def test_plugin_list_json(patch_client):
    result = runner.invoke(app, ["plugin", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "my-plugin"
    assert parsed[0]["version"] == "1.0.0"


def test_plugin_list_handles_dict_quirk(mock_client):
    """dataikuapi returns dicts from list_plugins(), not objects."""
    plugins = mock_client.list_plugins()
    assert isinstance(plugins[0], dict)
    assert "id" in plugins[0]


def test_plugin_push_missing_file():
    result = runner.invoke(app, ["plugin", "push", "/nonexistent/plugin.zip"])
    assert result.exit_code != 0


def test_plugin_settings_view(patch_client):
    plugin_obj = MagicMock()
    settings = MagicMock()
    settings.get_raw.return_value = {
        "codeEnvName": "plugin_test_managed",
        "config": {"param1": "value1", "password_param": "secret"},
    }
    plugin_obj.get_settings.return_value = settings
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "settings", "my-plugin"])
    assert result.exit_code == 0
    assert "****" in result.output
    assert "secret" not in result.output


def test_plugin_push_reads_plugin_id_from_archive(tmp_path, patch_client):
    plugin_obj = MagicMock()
    patch_client.get_plugin.return_value = plugin_obj
    patch_client.list_plugins.return_value = [
        {"id": "real-plugin", "version": "1.0.0", "isDev": False}
    ]

    zip_path = tmp_path / "release-1.2.3.zip"
    _write_plugin_zip(zip_path, "real-plugin")

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code == 0
    plugin_obj.update_from_zip.assert_called_once()
    patch_client.install_plugin_from_archive.assert_not_called()
    assert "Updated plugin 'real-plugin'" in result.output


def test_plugin_push_installs_when_plugin_is_missing(tmp_path, patch_client):
    patch_client.list_plugins.return_value = []

    zip_path = tmp_path / "release-1.2.3.zip"
    _write_plugin_zip(zip_path, "real-plugin")

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code == 0
    patch_client.install_plugin_from_archive.assert_called_once()
    assert "Installed plugin 'real-plugin'" in result.output


# --- get ---


def _mock_plugin_with_settings(patch_client, plugin_id="my-plugin"):
    """Set up a plugin with settings mock, returns the plugin object."""
    plugin_obj = MagicMock()
    settings = MagicMock()
    settings.get_raw.return_value = {
        "codeEnvName": "plugin_test_managed",
        "config": {"param1": "value1"},
    }
    plugin_obj.get_settings.return_value = settings
    patch_client.get_plugin.return_value = plugin_obj
    return plugin_obj, settings


def test_plugin_get_table(patch_client):
    _mock_plugin_with_settings(patch_client)

    result = runner.invoke(app, ["plugin", "get", "my-plugin"])
    assert result.exit_code == 0
    assert "my-plugin" in result.output
    assert "plugin_test_managed" in result.output


def test_plugin_get_json(patch_client):
    _mock_plugin_with_settings(patch_client)

    result = runner.invoke(app, ["plugin", "get", "my-plugin", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "my-plugin"
    assert parsed["codeEnvName"] == "plugin_test_managed"


def test_plugin_get_not_found(patch_client):
    patch_client.list_plugins.return_value = []

    result = runner.invoke(app, ["plugin", "get", "nonexistent"])
    assert result.exit_code != 0


# --- delete ---


def test_plugin_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["plugin", "delete", "my-plugin"])
    assert result.exit_code != 0


def test_plugin_delete_with_confirm(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    future.wait_for_result.return_value = {}
    plugin_obj.delete.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "delete", "my-plugin", "--yes"])
    assert result.exit_code == 0
    plugin_obj.delete.assert_called_once_with(force=False)
    assert "Deleted plugin 'my-plugin'" in result.output


def test_plugin_delete_force(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    future.wait_for_result.return_value = {}
    plugin_obj.delete.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "delete", "my-plugin", "--yes", "--force"])
    assert result.exit_code == 0
    plugin_obj.delete.assert_called_once_with(force=True)


# --- create-code-env ---


def test_plugin_create_code_env(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    future.wait_for_result.return_value = {"envName": "plugin_test_managed_py310"}
    plugin_obj.create_code_env.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "create-code-env", "my-plugin"])
    assert result.exit_code == 0
    plugin_obj.create_code_env.assert_called_once()
    assert "plugin_test_managed_py310" in result.output


def test_plugin_create_code_env_json(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    future.wait_for_result.return_value = {"envName": "plugin_test_managed_py310"}
    plugin_obj.create_code_env.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(
        app, ["plugin", "create-code-env", "my-plugin", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["pluginId"] == "my-plugin"
    assert parsed["envName"] == "plugin_test_managed_py310"


def test_plugin_create_code_env_no_wait(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    plugin_obj.create_code_env.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "create-code-env", "my-plugin", "--no-wait"])
    assert result.exit_code == 0
    future.wait_for_result.assert_not_called()
    assert "started" in result.output


# --- set-code-env ---


def test_plugin_set_code_env(patch_client):
    plugin_obj, settings = _mock_plugin_with_settings(patch_client)

    result = runner.invoke(
        app, ["plugin", "set-code-env", "my-plugin", "my_custom_env"]
    )
    assert result.exit_code == 0
    settings.set_code_env.assert_called_once_with("my_custom_env")
    settings.save.assert_called_once()
    assert "Assigned code environment 'my_custom_env'" in result.output


# --- update-code-env ---


def test_plugin_update_code_env(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    future.wait_for_result.return_value = {}
    plugin_obj.update_code_env.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "update-code-env", "my-plugin"])
    assert result.exit_code == 0
    plugin_obj.update_code_env.assert_called_once()
    assert "Updated code environment" in result.output


def test_plugin_update_code_env_no_wait(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    plugin_obj.update_code_env.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "update-code-env", "my-plugin", "--no-wait"])
    assert result.exit_code == 0
    future.wait_for_result.assert_not_called()
    assert "started" in result.output


# --- usages ---


def test_plugin_usages_table(patch_client):
    plugin_obj = MagicMock()
    usage_obj = MagicMock()
    usage_obj.get_raw.return_value = {
        "usages": [
            {
                "projectKey": "PROJ1",
                "objectType": "RECIPE",
                "objectId": "compute_data",
                "elementKind": "PYTHON",
            }
        ]
    }
    plugin_obj.list_usages.return_value = usage_obj
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "usages", "my-plugin"])
    assert result.exit_code == 0
    assert "PROJ1" in result.output
    assert "RECIPE" in result.output


def test_plugin_usages_json(patch_client):
    plugin_obj = MagicMock()
    usage_obj = MagicMock()
    raw_data = {
        "usages": [
            {
                "projectKey": "PROJ1",
                "objectType": "RECIPE",
                "objectId": "compute_data",
                "elementKind": "PYTHON",
            }
        ]
    }
    usage_obj.get_raw.return_value = raw_data
    plugin_obj.list_usages.return_value = usage_obj
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "usages", "my-plugin", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["usages"][0]["projectKey"] == "PROJ1"


def test_plugin_usages_empty(patch_client):
    plugin_obj = MagicMock()
    usage_obj = MagicMock()
    usage_obj.get_raw.return_value = {"usages": []}
    plugin_obj.list_usages.return_value = usage_obj
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "usages", "my-plugin"])
    assert result.exit_code == 0
    assert "No usages found" in result.output


def test_plugin_usages_with_project_filter(patch_client):
    plugin_obj = MagicMock()
    usage_obj = MagicMock()
    usage_obj.get_raw.return_value = {"usages": []}
    plugin_obj.list_usages.return_value = usage_obj
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "usages", "my-plugin", "-P", "PROJ1"])
    assert result.exit_code == 0
    plugin_obj.list_usages.assert_called_once_with(project_key="PROJ1")


# --- push from directory ---


def test_plugin_push_directory(tmp_path, patch_client):
    """Push from a directory containing plugin.json — auto-zips and uploads."""
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"id": "dir-plugin", "version": "1.0.0"})
    )
    (plugin_dir / "python-lib").mkdir()
    (plugin_dir / "python-lib" / "helper.py").write_text("# helper")

    plugin_obj = MagicMock()
    patch_client.get_plugin.return_value = plugin_obj
    patch_client.list_plugins.return_value = [
        {"id": "dir-plugin", "version": "0.9.0", "isDev": True}
    ]

    result = runner.invoke(app, ["plugin", "push", str(plugin_dir)])
    assert result.exit_code == 0
    plugin_obj.update_from_zip.assert_called_once()
    assert "Updated plugin 'dir-plugin'" in result.output


def test_plugin_push_directory_install(tmp_path, patch_client):
    """Push from a directory when plugin is not installed — installs new."""
    plugin_dir = tmp_path / "new-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"id": "new-plugin", "version": "1.0.0"})
    )

    patch_client.list_plugins.return_value = []

    result = runner.invoke(app, ["plugin", "push", str(plugin_dir)])
    assert result.exit_code == 0
    patch_client.install_plugin_from_archive.assert_called_once()
    assert "Installed plugin 'new-plugin'" in result.output


def test_plugin_push_directory_no_plugin_json(tmp_path):
    """Directory without plugin.json gives prescriptive error."""
    empty_dir = tmp_path / "bad-plugin"
    empty_dir.mkdir()

    result = runner.invoke(app, ["plugin", "push", str(empty_dir)])
    assert result.exit_code != 0
    assert "plugin.json" in result.output


def test_plugin_push_unsupported_file_type(tmp_path):
    """Non-zip, non-directory path gives prescriptive error."""
    tarball = tmp_path / "plugin.tar.gz"
    tarball.write_text("not a zip")

    result = runner.invoke(app, ["plugin", "push", str(tarball)])
    assert result.exit_code != 0
    assert "Unsupported file type" in result.output


# ── Plugin recipes tests ────────────────────────────────────────────


def test_plugin_recipes_with_components(patch_client):
    """List plugin recipes when DSS returns customRecipes in list_plugins()."""
    patch_client.list_plugins.return_value = [
        {
            "id": "my-plugin",
            "version": "1.0.0",
            "isDev": True,
            "customRecipes": [
                {"id": "my-recipe", "label": "My Custom Recipe"},
                {"id": "other-recipe", "label": "Other Recipe"},
            ],
        },
    ]
    # Use JSON to avoid table truncation
    result = runner.invoke(app, ["plugin", "recipes", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    types = [r["type"] for r in parsed]
    assert "CustomCode_my-plugin_my-recipe" in types
    assert "CustomCode_my-plugin_other-recipe" in types
    assert parsed[0]["label"] == "My Custom Recipe"


def test_plugin_recipes_without_components(patch_client):
    """When DSS doesn't return customRecipes, show naming pattern."""
    patch_client.list_plugins.return_value = [
        {"id": "some-plugin", "version": "2.0.0", "isDev": False},
    ]
    # Use JSON to avoid table truncation
    result = runner.invoke(app, ["plugin", "recipes", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["type"] == "CustomCode_some-plugin_<recipeId>"


def test_plugin_recipes_filter_by_plugin_id(patch_client):
    """Filter recipes by specific plugin ID."""
    patch_client.list_plugins.return_value = [
        {
            "id": "plugin-a",
            "version": "1.0.0",
            "isDev": False,
            "customRecipes": [{"id": "rec-a", "label": "Recipe A"}],
        },
        {
            "id": "plugin-b",
            "version": "1.0.0",
            "isDev": False,
            "customRecipes": [{"id": "rec-b", "label": "Recipe B"}],
        },
    ]
    result = runner.invoke(app, ["plugin", "recipes", "plugin-a"])
    assert result.exit_code == 0
    assert "CustomCode_plugin-a_rec-a" in result.output
    assert "plugin-b" not in result.output


def test_plugin_recipes_not_found(patch_client):
    """Unknown plugin ID gives exit 3 with prescriptive error."""
    patch_client.list_plugins.return_value = [
        {"id": "existing", "version": "1.0.0", "isDev": False},
    ]
    result = runner.invoke(app, ["plugin", "recipes", "nonexistent"])
    assert result.exit_code != 0


def test_plugin_recipes_json_output(patch_client):
    """JSON output returns structured data."""
    patch_client.list_plugins.return_value = [
        {
            "id": "my-plugin",
            "version": "1.0.0",
            "isDev": True,
            "customRecipes": [
                {"id": "my-recipe", "label": "My Recipe"},
            ],
        },
    ]
    result = runner.invoke(app, ["plugin", "recipes", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["type"] == "CustomCode_my-plugin_my-recipe"


def test_plugin_recipes_no_plugins(patch_client):
    """No plugins installed shows helpful message."""
    patch_client.list_plugins.return_value = []
    result = runner.invoke(app, ["plugin", "recipes"])
    assert result.exit_code == 0
    assert "No plugins installed" in result.output
