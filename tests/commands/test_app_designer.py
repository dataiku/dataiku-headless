"""Tests for app-designer commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_app_designer_get(patch_client):
    result = runner.invoke(app, ["app-designer", "get", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["useAppHomepage"] is True
    assert parsed["label"] == "My Test App"


# ---------------------------------------------------------------------------
# set-definition
# ---------------------------------------------------------------------------


def test_app_designer_set_definition(patch_client):
    new_def = json.dumps({"useAppHomepage": False, "label": "Updated"})
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-definition",
            "--project",
            "PROJ1",
            "--definition",
            new_def,
        ],
    )
    assert result.exit_code == 0
    assert "Updated app manifest" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


def test_app_designer_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "manifest.json"
    defn_file.write_text(json.dumps({"useAppHomepage": True, "label": "FromFile"}))
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-definition",
            "--project",
            "PROJ1",
            "--definition",
            f"@{defn_file}",
        ],
    )
    assert result.exit_code == 0
    assert "Updated app manifest" in result.output


# ---------------------------------------------------------------------------
# list-tiles
# ---------------------------------------------------------------------------


def test_app_designer_list_tiles(patch_client):
    result = runner.invoke(app, ["app-designer", "list-tiles", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "SCENARIO_RUN" in result.output
    assert "PROJECT_VARIABL" in result.output  # Rich may truncate long type names
    assert "Build Flow" in result.output


def test_app_designer_list_tiles_json(patch_client):
    result = runner.invoke(
        app, ["app-designer", "list-tiles", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["type"] == "SCENARIO_RUN"
    assert parsed[0]["section"] == "0"
    assert parsed[0]["index"] == "0"
    assert parsed[1]["type"] == "PROJECT_VARIABLES_EDIT"


# ---------------------------------------------------------------------------
# add-tile
# ---------------------------------------------------------------------------


def test_app_designer_add_tile_scenario_run(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "SCENARIO_RUN",
            "--scenario",
            "DAILY",
            "--prompt",
            "Run Daily",
        ],
    )
    assert result.exit_code == 0
    assert "Added SCENARIO_RUN tile" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


def test_app_designer_add_tile_dashboard_link(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "DASHBOARD_LINK",
        ],
    )
    assert result.exit_code == 0
    assert "Added DASHBOARD_LINK tile" in result.output


def test_app_designer_add_tile_variables_edit(patch_client):
    params_json = json.dumps(
        [{"name": "threshold", "type": "INT", "label": "Threshold"}]
    )
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "PROJECT_VARIABLES_EDIT",
            "--params",
            params_json,
            "--behavior",
            "MODAL",
            "--prompt",
            "Settings",
        ],
    )
    assert result.exit_code == 0
    assert "Added PROJECT_VARIABLES_EDIT tile" in result.output


def test_app_designer_add_tile_inline_python(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "INLINE_PYTHON_RUN",
            "--code",
            "print('hello')",
            "--button-text",
            "Run",
        ],
    )
    assert result.exit_code == 0
    assert "Added INLINE_PYTHON_RUN tile" in result.output


def test_app_designer_add_tile_definition(patch_client):
    tile_json = json.dumps({"type": "DOWNLOAD_DATASET", "prompt": "Export"})
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--definition",
            tile_json,
        ],
    )
    assert result.exit_code == 0
    assert "Added DOWNLOAD_DATASET tile" in result.output


def test_app_designer_add_tile_missing_type_and_definition(patch_client):
    result = runner.invoke(app, ["app-designer", "add-tile", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_app_designer_add_tile_scenario_missing_scenario_id(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "SCENARIO_RUN",
        ],
    )
    assert result.exit_code != 0


def test_app_designer_add_tile_to_new_section(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "DASHBOARD_LINK",
            "--section",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "section 2" in result.output


# ---------------------------------------------------------------------------
# remove-tile
# ---------------------------------------------------------------------------


def test_app_designer_remove_tile(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "remove-tile",
            "--project",
            "PROJ1",
            "--section",
            "0",
            "--index",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "Removed PROJECT_VARIABLES_EDIT tile" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


def test_app_designer_remove_tile_out_of_range(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "remove-tile",
            "--project",
            "PROJ1",
            "--section",
            "0",
            "--index",
            "99",
        ],
    )
    assert result.exit_code != 0


def test_app_designer_remove_tile_section_out_of_range(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "remove-tile",
            "--project",
            "PROJ1",
            "--section",
            "99",
            "--index",
            "0",
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------


def test_app_designer_enable(patch_client):
    result = runner.invoke(app, ["app-designer", "enable", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "enabled" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


def test_app_designer_enable_with_label(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "enable",
            "--project",
            "PROJ1",
            "--label",
            "New Label",
            "--description",
            "New desc",
        ],
    )
    assert result.exit_code == 0
    assert "enabled" in result.output


def test_app_designer_disable(patch_client):
    result = runner.invoke(app, ["app-designer", "disable", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "disabled" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


# ---------------------------------------------------------------------------
# set-section
# ---------------------------------------------------------------------------


def test_app_designer_set_section(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-section",
            "--project",
            "PROJ1",
            "--section",
            "0",
            "--title",
            "Step 1) Upload",
            "--text",
            "Upload your data files here.",
        ],
    )
    assert result.exit_code == 0
    assert "Updated section 0" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


def test_app_designer_set_section_creates_new(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-section",
            "--project",
            "PROJ1",
            "--section",
            "3",
            "--title",
            "New Section",
        ],
    )
    assert result.exit_code == 0
    assert "Updated section 3" in result.output


# ---------------------------------------------------------------------------
# add-tile with --dataset, --dashboard, --folder, --help-text
# ---------------------------------------------------------------------------


def test_app_designer_add_tile_with_dataset(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "INLINE_DATASET_EDIT",
            "--dataset",
            "my_data",
            "--prompt",
            "Edit Config",
            "--help-text",
            "Edit the configuration dataset.",
        ],
    )
    assert result.exit_code == 0
    assert "Added INLINE_DATASET_EDIT tile" in result.output


def test_app_designer_add_tile_with_dashboard(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "DASHBOARD_LINK",
            "--dashboard",
            "dash123",
            "--prompt",
            "View Results",
        ],
    )
    assert result.exit_code == 0
    assert "Added DASHBOARD_LINK tile" in result.output


def test_app_designer_add_tile_with_folder(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "MANAGED_FOLDER_BROWSE",
            "--folder",
            "fld456",
            "--prompt",
            "Browse Export",
        ],
    )
    assert result.exit_code == 0
    assert "Added MANAGED_FOLDER_BROWSE tile" in result.output


def test_app_designer_add_tile_upload_with_dataset_and_behavior(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "UPLOAD_DATASET_SET_FILE",
            "--dataset",
            "raw_input",
            "--behavior",
            "INLINE_UPLOAD_REDETECT_AND_INFER",
            "--prompt",
            "Upload Data",
        ],
    )
    assert result.exit_code == 0
    assert "Added UPLOAD_DATASET_SET_FILE tile" in result.output


def test_app_designer_add_tile_scenario_with_button_text(patch_client):
    result = runner.invoke(
        app,
        [
            "app-designer",
            "add-tile",
            "--project",
            "PROJ1",
            "--type",
            "SCENARIO_RUN",
            "--scenario",
            "BUILD",
            "--prompt",
            "Build Pipeline",
            "--button-text",
            "Build",
        ],
    )
    assert result.exit_code == 0
    assert "Added SCENARIO_RUN tile" in result.output


# ---------------------------------------------------------------------------
# prescriptive error on non-app project
# ---------------------------------------------------------------------------


def test_app_designer_get_non_app_project(patch_client):
    """Error should suggest 'dku app-designer enable' when project is not an app."""
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest.side_effect = Exception(
        "IllegalArgumentException: Project PROJ1 is neither an app template nor an app instance"
    )
    result = runner.invoke(app, ["app-designer", "get", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "not an app template" in result.output
    assert "app-designer enable" in result.output
