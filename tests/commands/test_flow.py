"""Tests for flow commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app
from tests.helpers import strip_ansi

runner = CliRunner()


def test_flow_graph(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_flow_graph_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "flow", "graph", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "nodes" in parsed


def test_flow_graph_table(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output or "recipe1" in result.output


def test_flow_zones(patch_client):
    result = runner.invoke(app, ["flow", "zones", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "zone1" in result.output or "Default" in result.output


def test_flow_zones_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "flow", "zones", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "zone1"
    assert parsed[0]["name"] == "Default"
    assert parsed[1]["id"] == "XjxKvHzB"
    assert parsed[1]["name"] == "Processing"


def test_flow_create_zone(patch_client):
    result = runner.invoke(app, ["flow", "create-zone", "MyZone", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created zone" in result.output


def test_flow_propagate(patch_client):
    result = runner.invoke(app, ["flow", "propagate", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "propagation" in result.output.lower()
    proj = patch_client.get_project("PROJ1")
    flow = proj.get_flow()
    flow.new_schema_propagation.assert_called_once_with("ds1")


def test_flow_propagate_with_options(patch_client):
    result = runner.invoke(
        app,
        [
            "flow",
            "propagate",
            "ds1",
            "--stop-at",
            "recipe_a",
            "--stop-at",
            "recipe_b",
            "--mark-ok",
            "recipe_c",
            "--no-auto-rebuild",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    flow = proj.get_flow()
    builder = flow.new_schema_propagation.return_value
    builder.stop_at.assert_any_call("recipe_a")
    builder.stop_at.assert_any_call("recipe_b")
    builder.mark_recipe_as_ok.assert_called_once_with("recipe_c")
    builder.set_auto_rebuild.assert_called_once_with(False)


def test_flow_propagate_missing_dataset(patch_client):
    """Propagate without dataset argument should fail."""
    result = runner.invoke(app, ["flow", "propagate", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_flow_propagate_partial_failure_exits_nonzero(patch_client):
    """Schema propagation that finishes with unresolved conflicts/errors must
    exit non-zero — exit 0 would let an agent rebuild on an unreconciled flow."""
    from unittest.mock import MagicMock

    flow = patch_client.get_project("PROJ1").get_flow()
    builder = flow.new_schema_propagation.return_value
    builder.start.return_value = MagicMock(
        wait_for_result=MagicMock(
            return_value={
                "success": False,
                "errors": [
                    {"recipe": "recipe_x", "message": "schema conflict on column foo"}
                ],
            }
        )
    )
    result = runner.invoke(app, ["flow", "propagate", "ds1", "--project", "PROJ1"])
    assert result.exit_code != 0, result.output
    combined = (result.stdout + result.stderr).lower()
    assert "conflict" in combined or "error" in combined


def test_flow_propagate_success_true_exits_zero(patch_client):
    """A bare {'success': True} result is the happy path — must stay exit 0."""
    result = runner.invoke(app, ["flow", "propagate", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert "complete" in result.output.lower() or "complete" in result.stderr.lower()


def test_flow_check(patch_client):
    """Flow consistency check."""
    result = runner.invoke(app, ["flow", "check", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "consistency check complete" in result.output.lower()
    proj = patch_client.get_project("PROJ1")
    flow = proj.get_flow()
    flow.start_tool.assert_called_once_with("CHECK_CONSISTENCY")


def test_flow_check_json(patch_client):
    """Flow check with JSON output."""
    result = runner.invoke(
        app, ["--format", "json", "flow", "check", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "summary" in result.output


def _set_check_state_with_fatal_error(patch_client):
    """Wire the flow CHECK_CONSISTENCY tool to report one fatal node error."""
    flow = patch_client.get_project("PROJ1").get_flow()
    tool = flow.start_tool.return_value
    tool.get_state.return_value = {
        "summary": {"ok": 0, "error": 1},
        "stateByNode": {
            "recipe_broken": {
                "recipeCheckResult": {
                    "messages": [
                        {
                            "isFatal": True,
                            "severity": "FATAL",
                            "code": "SCHEMA_MISMATCH",
                            "message": "Output schema does not match recipe.",
                        }
                    ]
                }
            }
        },
    }


def test_flow_check_fatal_error_exits_nonzero(patch_client):
    """Fatal consistency errors must exit non-zero — exit 0 would let an agent
    chain `flow check && job run` rebuild a broken flow (TSV path)."""
    _set_check_state_with_fatal_error(patch_client)
    result = runner.invoke(app, ["flow", "check", "--project", "PROJ1"])
    assert result.exit_code != 0, result.output
    # Error prose is on stderr; combine both streams to be version-robust.
    combined = (result.stdout + result.stderr).lower()
    assert "fatal error" in combined
    # The success line must NOT print when there are errors.
    assert "consistency check complete" not in combined


def test_flow_check_fatal_error_default_stdout_is_json(patch_client):
    """With errors present, default stdout must stay one parseable JSON object —
    no trailing errors table (the errors are already in the payload)."""
    _set_check_state_with_fatal_error(patch_client)
    result = runner.invoke(app, ["flow", "check", "--project", "PROJ1"])
    assert result.exit_code != 0
    parsed = json.loads(result.stdout)
    assert parsed["errors"][0]["node"] == "recipe_broken"


def test_flow_check_fatal_error_exits_nonzero_json(patch_client):
    """The same gate applies to the --format json path."""
    _set_check_state_with_fatal_error(patch_client)
    result = runner.invoke(
        app, ["--format", "json", "flow", "check", "--project", "PROJ1"]
    )
    assert result.exit_code != 0, result.output
    parsed = json.loads(result.stdout)
    assert parsed["errors"]
    assert parsed["errors"][0]["node"] == "recipe_broken"


def test_flow_sources(patch_client):
    result = runner.invoke(app, ["flow", "sources", "--project", "PROJ1"])
    assert result.exit_code == 0
    # ds1 has successors ["recipe1"], recipe1 is downstream — so ds1 is the source
    assert "ds1" in result.output


def test_flow_sources_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "flow", "sources", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    source_ids = [s["id"] for s in parsed]
    assert "ds1" in source_ids
    # recipe1 is a successor of ds1, so it should NOT be a source
    assert "recipe1" not in source_ids


def test_flow_successors(patch_client):
    result = runner.invoke(app, ["flow", "successors", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "recipe1" in result.output


def test_flow_successors_empty(patch_client):
    result = runner.invoke(app, ["flow", "successors", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    # recipe1 has no successors, so output should be empty table or empty json


def test_flow_visualize(patch_client):
    result = runner.invoke(app, ["flow", "visualize", "--project", "PROJ1"])
    assert result.exit_code == 0
    # ds1 is a source DATASET, recipe1 is its successor RECIPE
    assert "ds1" in result.output
    assert "recipe1" in result.output
    assert "DATASET" in result.output
    assert "RECIPE" in result.output


# ---------------------------------------------------------------------------
# Flow move command tests
# ---------------------------------------------------------------------------


def test_flow_move_single_dataset(patch_client):
    """Move one dataset to a zone by name."""
    result = runner.invoke(
        app, ["flow", "move", "ds1", "--zone", "Processing", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Moved" in result.output
    assert "Processing" in result.output
    # Should resolve the dataset and call add_item
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.assert_called_with("ds1")


def test_flow_move_multiple_items(patch_client):
    """Move multiple items at once."""
    result = runner.invoke(
        app,
        ["flow", "move", "ds1", "ds2", "--zone", "Processing", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output


def test_flow_move_by_zone_id(patch_client):
    """Resolve zone by ID string."""
    result = runner.invoke(
        app, ["flow", "move", "ds1", "--zone", "XjxKvHzB", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Moved" in result.output


def test_flow_move_zone_not_found_no_create(patch_client):
    """Prescriptive error when zone doesn't exist and --no-create-zone is set."""
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "ds1",
            "--zone",
            "NonExistent",
            "--no-create-zone",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert (
        "not found" in result.output.lower()
        or "not found" in (result.stderr or "").lower()
    )


def test_flow_move_auto_creates_missing_zone(patch_client):
    """By default, missing zones are created on the fly."""
    proj = patch_client.get_project("PROJ1")
    flow = proj.get_flow()

    result = runner.invoke(
        app,
        ["flow", "move", "ds1", "--zone", "BrandNewZone", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    assert "Moved" in result.output
    flow.create_zone.assert_called_with("BrandNewZone")


def test_flow_move_recipe_type(patch_client):
    """Move a recipe with --type RECIPE."""
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "recipe1",
            "--zone",
            "Processing",
            "--type",
            "RECIPE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_recipe.assert_called_with("recipe1")


def test_flow_move_managed_folder_by_name(patch_client):
    """Move a managed folder using its display name (not opaque ID).

    resolve_folder() should be used instead of get_managed_folder() directly,
    because get_managed_folder() is lazy and only accepts the 8-char ID.
    """
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "Data Folder",
            "--zone",
            "Processing",
            "--type",
            "MANAGED_FOLDER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output


def test_flow_move_managed_folder_by_id(patch_client):
    """Move a managed folder using its ID."""
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "folder1",
            "--zone",
            "Processing",
            "--type",
            "MANAGED_FOLDER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output


def test_flow_sources_with_dataset(patch_client):
    """flow sources DATASET traces upstream to find source nodes."""
    # Mock graph: ds1 -> recipe1, recipe1 has no successors
    # So recipe1's parent is ds1, and ds1 has no parents = source
    result = runner.invoke(app, ["flow", "sources", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output


def test_flow_sources_without_dataset(patch_client):
    """flow sources (no arg) lists all project root sources."""
    result = runner.invoke(app, ["flow", "sources", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output


# --- set-zone ---


def test_flow_set_zone_name(patch_client):
    result = runner.invoke(
        app,
        ["flow", "set-zone", "Default", "--name", "Ingestion", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Updated zone" in result.output


def test_flow_set_zone_color(patch_client):
    result = runner.invoke(
        app,
        ["flow", "set-zone", "Default", "--color", "#FF5500", "--project", "PROJ1"],
    )
    assert result.exit_code == 0


def test_flow_set_zone_no_args(patch_client):
    result = runner.invoke(app, ["flow", "set-zone", "Default", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "--short-desc" in strip_ansi(result.output)


def test_flow_set_zone_short_desc(patch_client):
    result = runner.invoke(
        app,
        [
            "flow",
            "set-zone",
            "Default",
            "--short-desc",
            "Ingests raw sales files",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated zone" in result.output
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[0]
    assert zone._raw["shortDesc"] == "Ingests raw sales files"
    zone.get_settings.return_value.save.assert_called()


def test_flow_set_zone_description(patch_client):
    result = runner.invoke(
        app,
        [
            "flow",
            "set-zone",
            "Default",
            "--description",
            "Long-form details about this functional unit.",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[0]
    assert zone._raw["description"] == "Long-form details about this functional unit."


def test_flow_set_zone_description_from_file(patch_client, tmp_path):
    desc_file = tmp_path / "desc.md"
    desc_file.write_text("Description from a file.")
    result = runner.invoke(
        app,
        [
            "flow",
            "set-zone",
            "Default",
            "--description",
            f"@{desc_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[0]
    assert zone._raw["description"] == "Description from a file."


def test_flow_set_zone_short_desc_enables_display_setting(patch_client):
    """Writing a shortDesc flips the project's showFlowZoneDescriptions display
    setting when it is off — otherwise the description never renders."""
    proj = patch_client.get_project("PROJ1")
    proj_settings = proj.get_settings.return_value
    proj_settings.get_raw.return_value = {
        "settings": {"flowDisplaySettings": {"showFlowZoneDescriptions": False}}
    }
    result = runner.invoke(
        app,
        ["flow", "set-zone", "Default", "--short-desc", "Text", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    fds = proj_settings.get_raw.return_value["settings"]["flowDisplaySettings"]
    assert fds["showFlowZoneDescriptions"] is True
    proj_settings.save.assert_called_once()
    assert "Show flow zone descriptions" in strip_ansi(result.output)


def test_flow_set_zone_short_desc_display_setting_already_on(patch_client):
    result = runner.invoke(
        app,
        ["flow", "set-zone", "Default", "--short-desc", "Text", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.get_settings.return_value.save.assert_not_called()


def test_flow_set_zone_short_desc_clear(patch_client):
    """--short-desc '' clears the short description."""
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[0]
    zone._raw["shortDesc"] = "old text"
    result = runner.invoke(
        app,
        ["flow", "set-zone", "Default", "--short-desc", "", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert zone._raw["shortDesc"] == ""


def test_flow_create_zone_with_color(patch_client):
    result = runner.invoke(
        app, ["flow", "create-zone", "ETL", "--color", "#00FF00", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created zone" in result.output


def test_flow_create_zone_with_short_desc(patch_client):
    result = runner.invoke(
        app,
        [
            "flow",
            "create-zone",
            "Ingestion",
            "--short-desc",
            "Loads raw source files",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created zone" in result.output
    flow = patch_client.get_project("PROJ1").get_flow()
    created = flow.create_zone.return_value
    assert created._raw["shortDesc"] == "Loads raw source files"
    created.get_settings.return_value.save.assert_called()


def test_flow_create_zone_plain_skips_settings(patch_client):
    """create-zone without color/descriptions doesn't touch settings at all."""
    flow = patch_client.get_project("PROJ1").get_flow()
    created = flow.create_zone.return_value
    created.get_settings.reset_mock()
    result = runner.invoke(app, ["flow", "create-zone", "Bare", "--project", "PROJ1"])
    assert result.exit_code == 0
    created.get_settings.assert_not_called()


def test_flow_zones_table_shows_short_desc(patch_client):
    result = runner.invoke(app, ["flow", "zones", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Cleans raw sales data" in strip_ansi(result.output)


def test_flow_zones_json_includes_descriptions(patch_client):
    result = runner.invoke(app, ["flow", "zones", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[1]["shortDesc"] == "Cleans raw sales data"
    assert "description" in parsed[1]


def test_flow_ai_describe_zone(patch_client):
    result = runner.invoke(
        app, ["flow", "ai-describe-zone", "Processing", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "AI summary of the Processing zone" in out
    assert "not saved" in out
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[1]
    zone.generate_ai_description.assert_called_once_with(
        language="english", purpose="generic", length="medium", save_description=False
    )


def test_flow_ai_describe_zone_save(patch_client):
    result = runner.invoke(
        app,
        ["flow", "ai-describe-zone", "Processing", "--save", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "saved" in strip_ansi(result.output)
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[1]
    assert zone.generate_ai_description.call_args.kwargs["save_description"] is True


def test_flow_ai_describe_zone_not_found(patch_client):
    result = runner.invoke(
        app, ["flow", "ai-describe-zone", "NoSuchZone", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "not found" in strip_ansi(result.output)


def test_flow_ai_describe_zone_empty_response(patch_client):
    """Empty zone → DSS returns a non-JSON body → prescriptive error, not a
    bare 'Expecting value: line 1 column 1' (observed on live DSS)."""
    flow = patch_client.get_project("PROJ1").get_flow()
    zone = flow.list_zones.return_value[0]
    zone.generate_ai_description.side_effect = ValueError(
        "Expecting value: line 1 column 1 (char 0)"
    )
    result = runner.invoke(
        app, ["flow", "ai-describe-zone", "Default", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    out = strip_ansi(result.output)
    assert "empty zone" in out.lower()
    assert "set-zone" in out


# ── KB/eval-store move support ─────────────────────────────────────────────
# (delete-zone behaviour is covered in the granular "delete-zone" block below.)


def test_flow_move_knowledge_bank_type(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "kb1",
            "--zone",
            "Processing",
            "--type",
            "KNOWLEDGE_BANK",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj.get_knowledge_bank.assert_called_with("kb1")


def test_flow_move_model_evaluation_store_type(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "mes1",
            "--zone",
            "Processing",
            "--type",
            "MODEL_EVALUATION_STORE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output
    proj.get_model_evaluation_store.assert_called_with("mes1")


def test_flow_move_folder_type_on_dataset_gives_cross_type_hint(patch_client):
    """`flow move ds1 --type MANAGED_FOLDER` on a real dataset must surface the
    prescriptive cross-type hint, not re-raise the resolver's SystemExit as a
    generic abort. resolve_folder raises SystemExit on a miss; the move handler
    must treat that as a not-found so the probe runs."""
    proj = patch_client.get_project("PROJ1")
    # By-ID folder lookup fails (ds1 is not a folder); the name fallback in
    # resolve_folder then calls exit_with_error (SystemExit) since ds1 isn't in
    # list_managed_folders. The DATASET probe still succeeds (ds1 is a dataset).
    proj.get_managed_folder.side_effect = Exception("NotFoundException: does not exist")

    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "ds1",
            "--zone",
            "Processing",
            "--type",
            "MANAGED_FOLDER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    stripped = strip_ansi(result.output)
    assert "is a DATASET" in stripped
    assert "--type DATASET" in stripped or "--type AUTO" in stripped


def test_flow_move_type_accepts_lowercase(patch_client):
    """case_sensitive=False: a lowercase --type must parse and move the item."""
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "ds1",
            "--zone",
            "Processing",
            "--type",
            "dataset",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output


def test_flow_move_invalid_type_rejected(patch_client):
    """Invalid --type is rejected by click.Choice (exit 2, 'Invalid value')."""
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "ds1",
            "--zone",
            "Processing",
            "--type",
            "WIDGET",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Invalid value" in stripped


# --- delete-zone (granular force/protection) ---


def _flow_zones(patch_client):
    flow = patch_client.get_project("PROJ1").get_flow()
    default_zone, processing_zone = flow.list_zones.return_value
    return default_zone, processing_zone


def test_flow_delete_zone_empty_succeeds(patch_client):
    _default, processing = _flow_zones(patch_client)
    processing._raw = {"items": []}
    result = runner.invoke(
        app, ["flow", "delete-zone", "Processing", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Deleted flow zone" in result.output
    processing.delete.assert_called_once()


def test_flow_delete_zone_nonempty_refuses_without_force(patch_client):
    _default, processing = _flow_zones(patch_client)
    result = runner.invoke(
        app, ["flow", "delete-zone", "Processing", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "not deleting" in result.output
    assert "--force" in result.output
    processing.delete.assert_not_called()


def test_flow_delete_zone_force_yes_deletes_nonempty(patch_client):
    _default, processing = _flow_zones(patch_client)
    result = runner.invoke(
        app,
        ["flow", "delete-zone", "Processing", "--force", "--yes", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    processing.delete.assert_called_once()
    assert "moved to the default zone" in result.output


def test_flow_delete_zone_force_without_yes_blocked(patch_client):
    _default, processing = _flow_zones(patch_client)
    result = runner.invoke(
        app, ["flow", "delete-zone", "Processing", "--force", "--project", "PROJ1"]
    )
    # Safety guard blocks (exit 77) without --yes for a non-empty zone.
    assert result.exit_code == 77
    processing.delete.assert_not_called()


def test_flow_delete_zone_default_protected(patch_client):
    default, _processing = _flow_zones(patch_client)
    default.id = "default"
    result = runner.invoke(
        app, ["flow", "delete-zone", "default", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "cannot be deleted" in result.output
    default.delete.assert_not_called()


def test_flow_move_comma_separated_items(patch_client):
    """'ds1,ds2' splits into two items — commas can't appear in flow names."""
    result = runner.invoke(
        app,
        [
            "flow",
            "move",
            "ds1,ds2",
            "ds3",
            "--zone",
            "Processing",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output
    proj = patch_client.get_project("PROJ1")
    moved = [c.args[0] for c in proj.get_dataset.call_args_list]
    assert {"ds1", "ds2", "ds3"} <= set(moved)
