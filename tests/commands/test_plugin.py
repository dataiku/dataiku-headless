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
    result = runner.invoke(app, ["--format", "json", "plugin", "list"])
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


def test_plugin_list_dev_column_reads_dev_string_key(patch_client):
    """Regression: some DSS builds expose the dev flag under 'dev' as the STRING
    'True'/'False'. The DEV column must reflect it, not be hardwired to False."""
    patch_client.list_plugins.return_value = [
        {"id": "devp", "version": "0.1.0", "dev": "True"},
        {"id": "prod", "version": "1.0.0", "dev": "False"},
    ]
    result = runner.invoke(app, ["--format", "json", "plugin", "list"])
    assert result.exit_code == 0, result.output
    parsed = {p["id"]: p for p in json.loads(result.output)}
    assert parsed["devp"]["dev"] is True
    assert parsed["prod"]["dev"] is False


def test_plugin_list_dev_column_reads_isdev_bool_key(patch_client):
    """Regression: DSS 14.6 (verified live) exposes the flag as the bool 'isDev'
    with NO 'dev' key. The DEV column must read it rather than always showing
    False because it looked only at the absent 'dev' key."""
    patch_client.list_plugins.return_value = [
        {"id": "devp", "version": "0.1.0", "isDev": True},
        {"id": "prod", "version": "1.0.0", "isDev": False},
    ]
    result = runner.invoke(app, ["--format", "json", "plugin", "list"])
    assert result.exit_code == 0, result.output
    parsed = {p["id"]: p for p in json.loads(result.output)}
    assert parsed["devp"]["dev"] is True
    assert parsed["prod"]["dev"] is False


def test_plugin_get_dev_field_reads_dev_string_key(patch_client):
    """`plugin get` must read the same 'dev' string key for its Dev field."""
    plugin_obj = MagicMock()
    plugin_obj.get_settings.return_value.get_raw.return_value = {"config": {}}
    patch_client.get_plugin.return_value = plugin_obj
    patch_client.list_plugins.return_value = [
        {"id": "devp", "version": "0.1.0", "dev": "True"},
    ]
    result = runner.invoke(app, ["--format", "json", "plugin", "get", "devp"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["dev"] is True


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


def test_plugin_push_warns_recipe_still_builds(tmp_path, patch_client):
    """The post-push guidance must tell agents the recipe still builds and to
    verify by building (not by opening the UI editor)."""
    plugin_obj = MagicMock()
    patch_client.get_plugin.return_value = plugin_obj
    patch_client.list_plugins.return_value = [
        {"id": "real-plugin", "version": "1.0.0", "dev": "False"}
    ]
    zip_path = tmp_path / "release.zip"
    _write_plugin_zip(zip_path, "real-plugin")

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code == 0
    out = result.output.lower()
    assert "build" in out
    assert "ui" in out


def _write_wrapped_plugin_zip(path, plugin_id: str, wrapper: str = "my-plugin-main"):
    """A Dataiku/GitHub-export-style ZIP: everything under one top folder."""
    with ZipFile(path, "w") as archive:
        archive.writestr(
            f"{wrapper}/plugin.json",
            json.dumps({"id": plugin_id, "version": "1.0.0"}),
        )
        archive.writestr(f"{wrapper}/python-lib/foo.py", "x = 1\n")


def test_plugin_push_auto_flattens_wrapped_zip(tmp_path, patch_client):
    """Dataiku exports + GitHub 'Download ZIP' wrap content under one folder;
    push must repack flat (plugin.json at the ZIP root) before upload."""
    import io

    uploaded: dict[str, list[str]] = {}

    def _capture(f):
        with ZipFile(io.BytesIO(f.read())) as z:
            uploaded["names"] = z.namelist()

    patch_client.list_plugins.return_value = []
    patch_client.install_plugin_from_archive.side_effect = _capture

    zip_path = tmp_path / "my-plugin-main.zip"
    _write_wrapped_plugin_zip(zip_path, "real-plugin")

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code == 0, result.output
    assert "repacked flat" in result.output
    patch_client.install_plugin_from_archive.assert_called_once()
    # Wrapper dir stripped: plugin.json at root, no leading "my-plugin-main/".
    assert "plugin.json" in uploaded["names"]
    assert "python-lib/foo.py" in uploaded["names"]
    assert not any(n.startswith("my-plugin-main/") for n in uploaded["names"])


def test_plugin_push_rejects_ambiguous_wrapper(tmp_path, patch_client):
    """A loose file beside the wrapper folder is NOT auto-flattened — the
    command errors prescriptively instead of guessing."""
    zip_path = tmp_path / "weird.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("README.md", "loose\n")
        archive.writestr("my-plugin/plugin.json", json.dumps({"id": "p"}))

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code != 0
    # Wrapper-specific prescriptive guidance (distinguishes this from other
    # plugin.json failures); single token survives Rich box wrapping.
    assert "flatten" in result.output.lower()
    # Must NOT guess-and-upload an ambiguous archive.
    patch_client.install_plugin_from_archive.assert_not_called()


# --- recipes ---


def test_plugin_recipes_introspects_dev_plugin(patch_client):
    """Dev plugins are detected via the STRING 'dev' field (not bool 'isDev')
    and their custom-recipes/ components are enumerated."""
    patch_client.list_plugins.return_value = [
        {"id": "mig-tool", "version": "1.0.0", "dev": "True"},
    ]
    plugin_obj = MagicMock()
    plugin_obj.list_files.return_value = [
        {"name": "plugin.json", "path": "plugin.json"},
        {
            "name": "custom-recipes",
            "path": "custom-recipes",
            "children": [
                {
                    "name": "extract-table",
                    "path": "custom-recipes/extract-table",
                    "children": [
                        {"name": "recipe.json", "path": "..."},
                    ],
                },
            ],
        },
    ]
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["--format", "json", "plugin", "recipes"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert any(row["type"] == "CustomCode_extract-table" for row in parsed)


def test_plugin_recipes_installed_plugin_gives_honest_footer(patch_client):
    """Installed (non-dev) plugins can't be introspected via API — the verb
    must say so honestly instead of printing '(check DSS UI)'."""
    patch_client.list_plugins.return_value = [
        {"id": "batch-file-processor", "version": "1.0.0", "dev": "False"},
    ]

    result = runner.invoke(app, ["plugin", "recipes"])
    assert result.exit_code == 0
    assert "check DSS UI" not in result.output
    assert "cannot enumerate" in result.output.lower()
    assert "CustomCode_<recipeComponentId>" in result.output


def test_plugin_recipes_not_found_exits_3(patch_client):
    patch_client.list_plugins.return_value = [
        {"id": "some-plugin", "version": "1.0.0", "dev": "False"},
    ]
    result = runner.invoke(app, ["plugin", "recipes", "nonexistent"])
    assert result.exit_code == 3
    assert "not found" in result.output.lower()
    # The typer.Exit must not leak through the generic handler as an API error.
    assert "DSS API error" not in result.output


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

    result = runner.invoke(app, ["--format", "json", "plugin", "get", "my-plugin"])
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


def test_plugin_delete_force_requires_confirm_name(patch_client):
    """--force elevates to tier-3; --yes alone is not enough."""
    plugin_obj = MagicMock()
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "delete", "my-plugin", "--yes", "--force"])
    assert result.exit_code == 77
    plugin_obj.delete.assert_not_called()


def test_plugin_delete_force_with_matching_confirm_name(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    future.wait_for_result.return_value = {}
    plugin_obj.delete.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(
        app,
        [
            "plugin",
            "delete",
            "my-plugin",
            "--yes",
            "--force",
            "--confirm-name",
            "my-plugin",
        ],
    )
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
        app, ["--format", "json", "plugin", "create-code-env", "my-plugin"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["pluginId"] == "my-plugin"
    assert parsed["envName"] == "plugin_test_managed_py310"


def test_plugin_create_code_env_no_wait(patch_client):
    plugin_obj = MagicMock()
    future = MagicMock()
    plugin_obj.create_code_env.return_value = future
    # No env bound yet -> proceeds to create.
    plugin_obj.get_settings.return_value.get_raw.return_value = {}
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "create-code-env", "my-plugin", "--no-wait"])
    assert result.exit_code == 0
    future.wait_for_result.assert_not_called()
    assert "started" in result.output


def test_plugin_create_code_env_idempotent_skip(patch_client):
    """An already-bound managed env -> skip creation, warn, exit 0 (idempotent)."""
    plugin_obj = MagicMock()
    plugin_obj.get_settings.return_value.get_raw.return_value = {
        "codeEnvName": "plugin_replicate_managed_1"
    }
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "create-code-env", "my-plugin"])
    assert result.exit_code == 0
    # Must NOT create a duplicate env.
    plugin_obj.create_code_env.assert_not_called()
    assert "plugin_replicate_managed_1" in result.output
    # Prescriptive: point at the rebuild path.
    assert "dku plugin update-code-env my-plugin" in result.output


def test_plugin_create_code_env_idempotent_skip_json(patch_client):
    plugin_obj = MagicMock()
    plugin_obj.get_settings.return_value.get_raw.return_value = {
        "codeEnvName": "plugin_replicate_managed_1"
    }
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(
        app, ["--format", "json", "plugin", "create-code-env", "my-plugin"]
    )
    assert result.exit_code == 0
    plugin_obj.create_code_env.assert_not_called()
    parsed = json.loads(result.output)
    assert parsed["envName"] == "plugin_replicate_managed_1"
    assert parsed["created"] is False


def test_plugin_create_code_env_force_creates_despite_existing(patch_client):
    """--force creates a (duplicate) env even when one is already bound."""
    plugin_obj = MagicMock()
    plugin_obj.get_settings.return_value.get_raw.return_value = {
        "codeEnvName": "plugin_replicate_managed_1"
    }
    future = MagicMock()
    future.wait_for_result.return_value = {"envName": "plugin_replicate_managed_2"}
    plugin_obj.create_code_env.return_value = future
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "create-code-env", "my-plugin", "--force"])
    assert result.exit_code == 0
    plugin_obj.create_code_env.assert_called_once()
    assert "plugin_replicate_managed_2" in result.output


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

    result = runner.invoke(app, ["--format", "json", "plugin", "usages", "my-plugin"])
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
    """List plugin recipes when dev plugin file tree has custom-recipes."""
    from unittest.mock import MagicMock

    patch_client.list_plugins.return_value = [
        {"id": "my-plugin", "version": "1.0.0", "dev": "True"},
    ]
    plugin_mock = MagicMock()
    plugin_mock.list_files.return_value = [
        {
            "name": "custom-recipes",
            "children": [
                {"name": "my-recipe", "children": [{"name": "recipe.py"}]},
                {"name": "other-recipe", "children": [{"name": "recipe.py"}]},
            ],
        }
    ]
    patch_client.get_plugin.return_value = plugin_mock
    result = runner.invoke(app, ["--format", "json", "plugin", "recipes"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    types = [r["type"] for r in parsed]
    assert "CustomCode_my-recipe" in types
    assert "CustomCode_other-recipe" in types


def test_plugin_recipes_without_components(patch_client):
    """Installed (non-dev) plugins can't be introspected — show the honest
    footer with the naming pattern, not a misleading '(check DSS UI)' row."""
    patch_client.list_plugins.return_value = [
        {"id": "some-plugin", "version": "2.0.0", "dev": "False"},
    ]
    result = runner.invoke(app, ["plugin", "recipes"])
    assert result.exit_code == 0
    assert "check DSS UI" not in result.output
    assert "CustomCode_<recipeComponentId>" in result.output


def test_plugin_recipes_filter_by_plugin_id(patch_client):
    """Filter recipes by specific plugin ID."""
    patch_client.list_plugins.return_value = [
        {"id": "plugin-a", "version": "1.0.0", "isDev": False},
        {"id": "plugin-b", "version": "1.0.0", "isDev": False},
    ]
    result = runner.invoke(app, ["plugin", "recipes", "plugin-a"])
    assert result.exit_code == 0
    assert "plugin-a" in result.output
    assert "plugin-b" not in result.output


def test_plugin_recipes_not_found(patch_client):
    """Unknown plugin ID gives exit 3 with prescriptive error."""
    patch_client.list_plugins.return_value = [
        {"id": "existing", "version": "1.0.0", "isDev": False},
    ]
    result = runner.invoke(app, ["plugin", "recipes", "nonexistent"])
    assert result.exit_code != 0


def test_plugin_recipes_json_output(patch_client):
    """JSON output returns structured data for an introspectable dev plugin."""
    patch_client.list_plugins.return_value = [
        {"id": "my-plugin", "version": "1.0.0", "dev": "True"},
    ]
    plugin_mock = MagicMock()
    plugin_mock.list_files.return_value = [
        {
            "name": "custom-recipes",
            "children": [
                {"name": "my-recipe", "children": [{"name": "recipe.json"}]},
            ],
        }
    ]
    patch_client.get_plugin.return_value = plugin_mock
    result = runner.invoke(app, ["--format", "json", "plugin", "recipes"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["plugin"] == "my-plugin"
    assert parsed[0]["type"] == "CustomCode_my-recipe"


def test_plugin_recipes_no_plugins(patch_client):
    """No plugins installed shows helpful message."""
    patch_client.list_plugins.return_value = []
    result = runner.invoke(app, ["plugin", "recipes"])
    assert result.exit_code == 0
    assert "No plugins installed" in result.output


# --- list-files ---


def test_plugin_list_files(patch_client):
    result = runner.invoke(app, ["plugin", "list-files", "my-plugin"])
    assert result.exit_code == 0
    assert "python-lib/mylib.py" in result.output


def test_plugin_list_files_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "plugin", "list-files", "my-plugin"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    paths = [f["path"] for f in parsed]
    assert "python-lib/mylib.py" in paths
    assert "plugin.json" in paths


# --- get-file ---


def test_plugin_get_file(patch_client):
    result = runner.invoke(
        app, ["plugin", "get-file", "my-plugin", "--path", "python-lib/mylib.py"]
    )
    assert result.exit_code == 0
    assert "# plugin file content" in result.output


# --- put-file ---


def test_plugin_put_file(patch_client):
    result = runner.invoke(
        app,
        [
            "plugin",
            "put-file",
            "my-plugin",
            "--path",
            "python-lib/mylib.py",
            "--content",
            "# updated content",
        ],
    )
    assert result.exit_code == 0
    assert "Wrote" in result.output
    plugin = patch_client.get_plugin("my-plugin")
    plugin.put_file.assert_called_once()


def test_plugin_put_file_from_file(patch_client, tmp_path):
    content_file = tmp_path / "code.py"
    content_file.write_text("# from file")
    result = runner.invoke(
        app,
        [
            "plugin",
            "put-file",
            "my-plugin",
            "--path",
            "python-lib/mylib.py",
            "--content",
            f"@{content_file}",
        ],
    )
    assert result.exit_code == 0
    assert "Wrote" in result.output


# --- install-from-store ---


def test_plugin_install_from_store(patch_client):
    """Install plugin from store waits for completion."""
    result = runner.invoke(
        app, ["plugin", "install-from-store", "timeseries-preparation"]
    )
    assert result.exit_code == 0
    assert "Installed" in result.output
    assert "timeseries-preparation" in result.output
    patch_client.install_plugin_from_store.assert_called_once_with(
        "timeseries-preparation"
    )
    patch_client.install_plugin_from_store.return_value.wait_for_result.assert_called_once()


def test_plugin_install_from_store_no_wait(patch_client):
    """--no-wait returns immediately."""
    result = runner.invoke(
        app, ["plugin", "install-from-store", "my-plugin", "--no-wait"]
    )
    assert result.exit_code == 0
    assert "started" in result.output.lower()
    patch_client.install_plugin_from_store.return_value.wait_for_result.assert_not_called()


# --- install-from-git ---


def test_plugin_install_from_git(patch_client):
    """Install plugin from git with defaults."""
    result = runner.invoke(
        app,
        ["plugin", "install-from-git", "https://github.com/org/repo.git"],
    )
    assert result.exit_code == 0
    assert "Installed" in result.output
    patch_client.install_plugin_from_git.assert_called_once_with(
        "https://github.com/org/repo.git", checkout="master", subpath=None
    )


def test_plugin_install_from_git_with_checkout(patch_client):
    """--checkout passes through to dataikuapi."""
    result = runner.invoke(
        app,
        [
            "plugin",
            "install-from-git",
            "https://github.com/org/repo.git",
            "--checkout",
            "v2.0",
        ],
    )
    assert result.exit_code == 0
    patch_client.install_plugin_from_git.assert_called_once_with(
        "https://github.com/org/repo.git", checkout="v2.0", subpath=None
    )


def test_plugin_install_from_git_with_subpath(patch_client):
    """--subpath passes through to dataikuapi."""
    result = runner.invoke(
        app,
        [
            "plugin",
            "install-from-git",
            "https://github.com/org/monorepo.git",
            "--subpath",
            "plugins/my-plugin",
        ],
    )
    assert result.exit_code == 0
    patch_client.install_plugin_from_git.assert_called_once_with(
        "https://github.com/org/monorepo.git",
        checkout="master",
        subpath="plugins/my-plugin",
    )


# --- update-from-store ---


def test_plugin_update_from_store(patch_client):
    """Update plugin from store waits for completion."""
    result = runner.invoke(
        app, ["plugin", "update-from-store", "timeseries-preparation"]
    )
    assert result.exit_code == 0
    assert "Updated" in result.output
    plugin = patch_client.get_plugin("timeseries-preparation")
    plugin.update_from_store.assert_called_once()
    plugin.update_from_store.return_value.wait_for_result.assert_called_once()


def test_plugin_update_from_store_no_wait(patch_client):
    """--no-wait returns immediately."""
    result = runner.invoke(
        app, ["plugin", "update-from-store", "my-plugin", "--no-wait"]
    )
    assert result.exit_code == 0
    assert "started" in result.output.lower()


# --- update-from-git ---


def test_plugin_update_from_git(patch_client):
    """Update plugin from git with defaults."""
    result = runner.invoke(
        app,
        [
            "plugin",
            "update-from-git",
            "my-plugin",
            "https://github.com/org/repo.git",
        ],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output
    plugin = patch_client.get_plugin("my-plugin")
    plugin.update_from_git.assert_called_once_with(
        "https://github.com/org/repo.git", checkout="master", subpath=None
    )


def test_plugin_update_from_git_with_checkout(patch_client):
    """--checkout passes through to dataikuapi."""
    result = runner.invoke(
        app,
        [
            "plugin",
            "update-from-git",
            "my-plugin",
            "git@github.com:org/repo.git",
            "--checkout",
            "v2.1",
        ],
    )
    assert result.exit_code == 0
    plugin = patch_client.get_plugin("my-plugin")
    plugin.update_from_git.assert_called_once_with(
        "git@github.com:org/repo.git", checkout="v2.1", subpath=None
    )


# --- rename-file ---


def test_plugin_rename_file(patch_client):
    result = runner.invoke(
        app,
        [
            "plugin",
            "rename-file",
            "my-plugin",
            "--path",
            "python-lib/old.py",
            "--name",
            "new.py",
        ],
    )
    assert result.exit_code == 0
    assert "Renamed" in result.output
    plugin = patch_client.get_plugin("my-plugin")
    plugin.rename_file.assert_called_once_with("python-lib/old.py", "new.py")


# --- move-file ---


def test_plugin_move_file(patch_client):
    result = runner.invoke(
        app,
        [
            "plugin",
            "move-file",
            "my-plugin",
            "--path",
            "python-lib/utils.py",
            "--to",
            "python-lib/helpers/utils.py",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output
    plugin = patch_client.get_plugin("my-plugin")
    plugin.move_file.assert_called_once_with(
        "python-lib/utils.py", "python-lib/helpers/utils.py"
    )


# --- download ---


def test_plugin_download(patch_client, tmp_path):
    """Downloads plugin to default filename."""
    dest = tmp_path / "my-plugin.zip"

    # Mock download_plugin_to_file to create a real file
    def _fake_download(pid, path):
        with open(path, "wb") as f:
            f.write(b"PK\x03\x04" + b"\x00" * 100)  # fake zip header

    patch_client.download_plugin_to_file.side_effect = _fake_download
    result = runner.invoke(
        app, ["plugin", "download", "my-plugin", "--dest", str(dest)]
    )
    assert result.exit_code == 0
    assert "Downloaded" in result.output
    assert "my-plugin" in result.output
    assert dest.exists()
    patch_client.download_plugin_to_file.assert_called_once_with("my-plugin", str(dest))


def test_plugin_download_default_name(patch_client, tmp_path, monkeypatch):
    """Without --dest, uses <plugin_id>.zip."""
    monkeypatch.chdir(tmp_path)

    def _fake_download(pid, path):
        with open(path, "wb") as f:
            f.write(b"PK\x03\x04" + b"\x00" * 50)

    patch_client.download_plugin_to_file.side_effect = _fake_download
    result = runner.invoke(app, ["plugin", "download", "geocoder"])
    assert result.exit_code == 0
    assert "geocoder.zip" in result.output
    patch_client.download_plugin_to_file.assert_called_once_with(
        "geocoder", "geocoder.zip"
    )
