"""Tests for flow commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_flow_graph(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_flow_graph_json(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1", "-o", "json"])
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
    result = runner.invoke(app, ["flow", "zones", "--project", "PROJ1", "-o", "json"])
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
    result = runner.invoke(app, ["flow", "check", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    assert "summary" in result.output


def test_flow_sources(patch_client):
    result = runner.invoke(app, ["flow", "sources", "--project", "PROJ1"])
    assert result.exit_code == 0
    # ds1 has successors ["recipe1"], recipe1 is downstream — so ds1 is the source
    assert "ds1" in result.output


def test_flow_sources_json(patch_client):
    result = runner.invoke(app, ["flow", "sources", "--project", "PROJ1", "-o", "json"])
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


def test_flow_move_zone_not_found(patch_client):
    """Prescriptive error when zone doesn't exist."""
    result = runner.invoke(
        app, ["flow", "move", "ds1", "--zone", "NonExistent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert (
        "not found" in result.output.lower()
        or "not found" in (result.stderr or "").lower()
    )


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


def test_flow_create_zone_with_color(patch_client):
    result = runner.invoke(
        app, ["flow", "create-zone", "ETL", "--color", "#00FF00", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created zone" in result.output
