"""Tests for app-designer commands."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _make_export_response(manifest_dict: dict | None) -> MagicMock:
    """Build a fake _perform_raw response whose body is a ZIP containing
    project_config/app-manifest.json. Pass `None` to omit the file (project
    that never had setup data — fallback should return empty dict)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if manifest_dict is not None:
            zf.writestr("project_config/app-manifest.json", json.dumps(manifest_dict))
        zf.writestr("project.json", json.dumps({"projectKey": "PROJ1"}))
    raw_bytes = buf.getvalue()
    response = MagicMock()
    response.iter_content.return_value = [raw_bytes]
    return response


def _set_regular_project(
    patch_client,
    manifest_dict: dict | None = None,
    allow_write_after_promote: bool = False,
) -> tuple[MagicMock, MagicMock]:
    """Configure the mock to behave like a REGULAR project.

    `get_app_manifest` raises IllegalArgumentException (matches DSS server
    behavior on REGULAR), and the export endpoint returns a ZIP carrying
    the supplied manifest (or no manifest).

    When `allow_write_after_promote=True`, simulates the
    `_write_manifest` round-trip: first call still raises (the read attempt),
    but the second call (after `projectAppType=APP_TEMPLATE` flip) succeeds
    and returns a writable manifest mock. Returns (settings_mock, write_mock)
    so callers can assert against them.
    """
    proj = patch_client.get_project("PROJ1")
    settings_mock = MagicMock()
    settings_raw = {"projectAppType": "REGULAR"}
    settings_mock.get_raw.return_value = settings_raw
    proj.get_settings.return_value = settings_mock
    patch_client._perform_raw.return_value = _make_export_response(manifest_dict)
    patch_client._perform_empty.return_value = None

    if allow_write_after_promote:
        write_mock = MagicMock()
        write_mock.save.return_value = None

        # Side-effect callable: raise on every "still REGULAR" read, succeed
        # once the test flipped projectAppType to APP_TEMPLATE.
        def _side_effect(*_args, **_kwargs):
            if settings_raw.get("projectAppType") == "APP_TEMPLATE":
                return write_mock
            raise Exception(
                "IllegalArgumentException: Project PROJ1 is "
                "neither an app template nor an app instance"
            )

        proj.get_app_manifest.side_effect = _side_effect
        return settings_mock, write_mock

    proj.get_app_manifest.side_effect = Exception(
        "IllegalArgumentException: Project PROJ1 is "
        "neither an app template nor an app instance"
    )
    return settings_mock, MagicMock()


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
    """Set-definition that wipes existing sections requires --yes + --confirm-name."""
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
            "--yes",
            "--confirm-name",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Updated app manifest" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_app_manifest().save.assert_called()


def test_app_designer_set_definition_from_file(tmp_path, patch_client):
    """Wiping sections via @file.json still requires --yes + --confirm-name."""
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
            "--yes",
            "--confirm-name",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Updated app manifest" in result.output


def test_app_designer_set_definition_preserving_sections_no_guard(patch_client):
    """A set-definition that keeps the existing sections does NOT trigger
    the CASCADE guard — only wipes do."""
    new_def = json.dumps(
        {
            "useAppHomepage": True,
            "label": "Same sections, new label",
            "homepageSections": [{"tiles": [{"type": "DASHBOARD_LINK"}]}],
        }
    )
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
    assert result.exit_code == 0, result.output
    assert "Updated app manifest" in result.output


def test_app_designer_set_definition_blocks_section_wipe_without_yes(patch_client):
    """PUT-{} foot-gun regression: a payload that drops all sections is
    blocked at tier-3 CASCADE (exit 77) without --yes."""
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-definition",
            "--project",
            "PROJ1",
            "--definition",
            "{}",
        ],
    )
    assert result.exit_code == 77, result.output
    assert "wipes all" in result.output or "homepageSection" in result.output


def test_app_designer_set_definition_blocks_section_wipe_without_confirm_name(
    patch_client,
):
    """--yes alone is not enough for tier-3; --confirm-name is required."""
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-definition",
            "--project",
            "PROJ1",
            "--definition",
            "{}",
            "--yes",
        ],
    )
    assert result.exit_code == 77


def test_app_designer_set_definition_rejects_wrong_confirm_name(patch_client):
    """A mismatched --confirm-name still blocks (cascade name mismatch)."""
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-definition",
            "--project",
            "PROJ1",
            "--definition",
            "{}",
            "--yes",
            "--confirm-name",
            "WRONG_KEY",
        ],
    )
    assert result.exit_code == 77


def test_app_designer_set_definition_first_setup_no_guard(patch_client):
    """If the project has no current sections, the guard does not fire — no
    destructive intent, just an initial manifest write."""
    proj = patch_client.get_project("PROJ1")
    # Override the manifest to have no sections (fresh project)
    proj.get_app_manifest.side_effect = None
    fresh_manifest = MagicMock()
    fresh_manifest.get_raw.return_value = {"useAppHomepage": False}
    fresh_manifest.raw_data = {"useAppHomepage": False}
    fresh_manifest.save.return_value = None
    proj.get_app_manifest.return_value = fresh_manifest
    result = runner.invoke(
        app,
        [
            "app-designer",
            "set-definition",
            "--project",
            "PROJ1",
            "--definition",
            json.dumps({"useAppHomepage": True, "label": "First setup"}),
        ],
    )
    assert result.exit_code == 0, result.output


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


def test_app_designer_enable_default_mode_is_setup(patch_client):
    """Default `enable` is Project Setup — must NOT touch projectAppType.

    Regression for SOL_SAS_INVENTORY_SCORER: the old behavior silently
    flipped REGULAR projects to APP_TEMPLATE, breaking them as Solutions
    references."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_settings.return_value
    settings.get_raw.return_value = {"projectAppType": "REGULAR"}

    result = runner.invoke(app, ["app-designer", "enable", "--project", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert "Project Setup enabled" in result.output
    assert "REGULAR" in result.output
    # Settings.save() must NOT have been called — projectAppType untouched
    settings.save.assert_not_called()


def test_app_designer_enable_template_mode_flips_to_app_template(patch_client):
    """--mode template converts REGULAR → APP_TEMPLATE explicitly."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_settings.return_value
    raw_settings = {"projectAppType": "REGULAR"}
    settings.get_raw.return_value = raw_settings

    result = runner.invoke(
        app,
        ["app-designer", "enable", "--project", "PROJ1", "--mode", "template"],
    )
    assert result.exit_code == 0, result.output
    assert "App template enabled" in result.output
    assert raw_settings["projectAppType"] == "APP_TEMPLATE"
    settings.save.assert_called()


def test_app_designer_enable_template_mode_idempotent_when_already_template(
    patch_client,
):
    """If projectAppType is already APP_TEMPLATE, --mode template doesn't
    re-save settings."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_settings.return_value
    settings.get_raw.return_value = {"projectAppType": "APP_TEMPLATE"}

    result = runner.invoke(
        app,
        ["app-designer", "enable", "--project", "PROJ1", "--mode", "template"],
    )
    assert result.exit_code == 0
    settings.save.assert_not_called()


def test_app_designer_enable_rejects_invalid_mode(patch_client):
    """Unknown --mode value returns a prescriptive error."""
    result = runner.invoke(
        app,
        ["app-designer", "enable", "--project", "PROJ1", "--mode", "bogus"],
    )
    assert result.exit_code != 0
    assert "must be 'setup' or 'template'" in result.output


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


def test_app_designer_get_falls_back_to_export_for_regular_project(patch_client):
    """REGULAR projects can hold Project Setup data — `get` must fall back
    to reading project_config/app-manifest.json from /export when
    proj.get_app_manifest() raises the IllegalArgumentException."""
    setup_manifest = {
        "useAppHomepage": True,
        "label": "Project Setup",
        "homepageSections": [{"sectionTitle": "Step 1", "tiles": []}],
    }
    _set_regular_project(patch_client, setup_manifest)
    result = runner.invoke(app, ["app-designer", "get", "--project", "PROJ1"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["useAppHomepage"] is True
    assert parsed["label"] == "Project Setup"
    assert parsed["homepageSections"][0]["sectionTitle"] == "Step 1"


def test_app_designer_get_export_fallback_returns_empty_when_no_manifest(patch_client):
    """REGULAR project with no setup data → export ZIP has no app-manifest
    entry → fallback returns {} (not an error)."""
    _set_regular_project(patch_client, manifest_dict=None)
    result = runner.invoke(app, ["app-designer", "get", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_app_designer_set_definition_round_trips_through_app_template_on_regular(
    patch_client,
):
    """Set on a REGULAR project: SDK get_app_manifest raises. The CLI
    transparently promotes projectAppType to APP_TEMPLATE, writes the
    manifest, then restores REGULAR — preserving the caller's project
    surface."""
    settings_mock, write_mock = _set_regular_project(
        patch_client,
        manifest_dict={
            "useAppHomepage": True,
            "homepageSections": [{"tiles": [{"type": "DASHBOARD_LINK"}]}],
        },
        allow_write_after_promote=True,
    )
    new_def = json.dumps(
        {
            "useAppHomepage": True,
            "label": "Updated via round-trip",
            "homepageSections": [{"tiles": [{"type": "DASHBOARD_LINK"}]}],
        }
    )
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
    assert result.exit_code == 0, result.output
    # The manifest was written via the SDK (after promotion)
    write_mock.save.assert_called()
    assert write_mock.raw_data["label"] == "Updated via round-trip"
    # Final settings.save() restored projectAppType to REGULAR
    assert settings_mock.get_raw.return_value["projectAppType"] == "REGULAR"
    # settings.save() was called twice — promote and restore
    assert settings_mock.save.call_count == 2
