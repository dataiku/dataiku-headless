"""Tests for dashboard commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_dashboard_list(patch_client):
    result = runner.invoke(app, ["dashboard", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "dashboard1" in result.output


def test_dashboard_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "dashboard", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "dashboard1"
    assert parsed[0]["name"] == "Sales Dashboard"


def test_dashboard_get(patch_client):
    result = runner.invoke(
        app, ["dashboard", "get", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "dashboard1" in result.output


def test_dashboard_get_shows_working_url(patch_client):
    result = runner.invoke(
        app, ["dashboard", "get", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert (
        "https://dss.example.com/projects/PROJ1/dashboards/dashboard1/view/"
        in result.output
    )


def test_dashboard_get_tile_count(patch_client):
    """Tile count must read from pages[i].grid.tiles (real DSS structure)."""
    result = runner.invoke(
        app, ["dashboard", "get", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # conftest fixture has 1 tile in grid.tiles
    assert "1" in result.output


def test_dashboard_get_json(patch_client):
    result = runner.invoke(
        app,
        ["--format", "json", "dashboard", "get", "dashboard1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "dashboard1"
    assert parsed["name"] == "Sales Dashboard"


def test_dashboard_create(patch_client):
    result = runner.invoke(
        app, ["dashboard", "create", "New Dashboard", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created dashboard" in result.output
    assert "new_dashboard_1" in result.output
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dashboard.call_args[1]
    assert call_kwargs["dashboard_name"] == "New Dashboard"
    assert call_kwargs["settings"]["pages"][0]["id"] == "page1"
    assert call_kwargs["settings"]["pages"][0]["grid"]["tiles"] == []


def test_dashboard_create_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "dashboard",
            "create",
            "New Dashboard",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == {
        "id": "new_dashboard_1",
        "name": "New Dashboard",
        # trailing slash is load-bearing: /view (no slash) 404s in the DSS UI
        "url": "https://dss.example.com/projects/PROJ1/dashboards/new_dashboard_1/view/",
    }


def test_dashboard_create_with_definition(patch_client):
    defn = json.dumps({"pages": [{"title": "Page 1"}]})
    result = runner.invoke(
        app,
        [
            "dashboard",
            "create",
            "Custom Dashboard",
            "--project",
            "PROJ1",
            "--definition",
            defn,
        ],
    )
    assert result.exit_code == 0
    assert "Created dashboard" in result.output
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dashboard.call_args[1]
    assert call_kwargs["dashboard_name"] == "Custom Dashboard"
    assert call_kwargs["settings"] == {"pages": [{"title": "Page 1"}]}


def test_dashboard_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_dashboard.side_effect = Exception(
        "409 Conflict: dashboard already exists"
    )
    result = runner.invoke(
        app,
        ["dashboard", "create", "Existing", "--project", "PROJ1", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_dashboard_create_already_exists_fails(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_dashboard.side_effect = Exception(
        "409 Conflict: dashboard already exists"
    )
    result = runner.invoke(
        app,
        ["dashboard", "create", "Existing", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_dashboard_delete(patch_client):
    result = runner.invoke(
        app, ["dashboard", "delete", "dashboard1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted dashboard" in result.output
    proj = patch_client.get_project("PROJ1")
    dashboard = proj.get_dashboard("dashboard1")
    dashboard.delete.assert_called_once()


def test_dashboard_get_definition(patch_client):
    result = runner.invoke(
        app, ["dashboard", "get-definition", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "dashboard1"
    assert parsed["name"] == "Sales Dashboard"
    assert len(parsed["pages"]) == 1


def test_dashboard_set_definition(patch_client):
    new_def = json.dumps({"id": "dashboard1", "name": "Updated", "pages": []})
    result = runner.invoke(
        app,
        [
            "dashboard",
            "set-definition",
            "dashboard1",
            "--project",
            "PROJ1",
            "--definition",
            new_def,
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    dashboard = proj.get_dashboard("dashboard1")
    dashboard.get_settings().save.assert_called_once()


def test_dashboard_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "dashboard_def.json"
    defn_file.write_text(
        json.dumps({"id": "dashboard1", "name": "FromFile", "pages": []})
    )
    result = runner.invoke(
        app,
        [
            "dashboard",
            "set-definition",
            "dashboard1",
            "--project",
            "PROJ1",
            "--definition",
            f"@{defn_file}",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    dashboard = proj.get_dashboard("dashboard1")
    dashboard.get_settings().save.assert_called_once()


# --- set-metadata ---


def test_dashboard_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "dashboard",
            "set-metadata",
            "dashboard1",
            "--description",
            "Sales overview",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output
    dashboard = patch_client.get_project("PROJ1").get_dashboard("dashboard1")
    dashboard.get_settings().save.assert_called()


def test_dashboard_set_metadata_tags(patch_client):
    result = runner.invoke(
        app,
        [
            "dashboard",
            "set-metadata",
            "dashboard1",
            "--tags",
            "sales,kpi",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


def test_dashboard_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["dashboard", "set-metadata", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# --- list-tiles ---


def test_dashboard_list_tiles(patch_client):
    result = runner.invoke(
        app, ["dashboard", "list-tiles", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "i1" in result.output
    assert "0" in result.output  # page index


def test_dashboard_list_tiles_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "dashboard",
            "list-tiles",
            "dashboard1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["insight_id"] == "i1"
    assert parsed[0]["page"] == 0


def test_dashboard_list_tiles_empty(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_dashboard("dashboard1").get_settings()
    settings.get_raw.return_value = {
        "id": "dashboard1",
        "name": "Empty",
        "pages": [{"id": "p1", "grid": {"tiles": []}}],
    }
    result = runner.invoke(
        app, ["dashboard", "list-tiles", "dashboard1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0


# --- add-tile ---


def test_dashboard_add_tile(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_dashboard("dashboard1").get_settings()
    raw = {
        "id": "dashboard1",
        "name": "Dash",
        "pages": [{"id": "p1", "grid": {"tiles": []}}],
    }
    settings.get_raw.return_value = raw
    proj.get_insight("insight1").get_settings().get_raw.return_value = {
        "id": "insight1",
        "type": "chart",
    }
    result = runner.invoke(
        app,
        [
            "dashboard",
            "add-tile",
            "dashboard1",
            "--insight",
            "insight1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added insight" in result.output
    settings.save.assert_called_once()
    tile = raw["pages"][0]["grid"]["tiles"][0]
    assert tile["insightId"] == "insight1"
    # DSS requires both fields or the dashboard fails to render with
    # "Insight type null is unknown".
    assert tile["tileType"] == "INSIGHT"
    assert tile["insightType"] == "chart"
    assert tile["box"] == {"top": 0, "left": 0, "width": 18, "height": 10}
    # a top-level showTitle is dropped by DSS on save — titles live in titleOptions
    assert "showTitle" not in tile
    assert "resizeMode" not in tile
    assert tile["titleOptions"]["showTitle"] == "YES"
    assert tile["autoLoad"] is True
    # chart tiles hide the chart's legend unless the tile opts in — multi-series
    # charts are unreadable without it
    assert tile["tileParams"]["showLegend"] is True
    assert tile["tileParams"]["inheritLegendPlacement"] is True


def test_dashboard_add_tile_unknown_insight_type_fails(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_dashboard("dashboard1").get_settings()
    settings.get_raw.return_value = {
        "id": "dashboard1",
        "name": "Dash",
        "pages": [{"id": "p1", "grid": {"tiles": []}}],
    }
    # Insight whose type cannot be resolved -> refuse to build a null-type tile.
    proj.get_insight("ghost").get_settings().get_raw.return_value = {"id": "ghost"}
    result = runner.invoke(
        app,
        [
            "dashboard",
            "add-tile",
            "dashboard1",
            "--insight",
            "ghost",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Could not resolve the type" in result.output
    settings.save.assert_not_called()


def _dash_with_tiles(patch_client, tiles):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_dashboard("dashboard1").get_settings()
    raw = {
        "id": "dashboard1",
        "name": "Dash",
        "pages": [{"id": "p1", "grid": {"tiles": tiles}}],
    }
    settings.get_raw.return_value = raw
    return raw


def test_dashboard_add_tile_flows_beside_when_room(patch_client):
    raw = _dash_with_tiles(
        patch_client,
        [{"insightId": "i1", "box": {"left": 0, "top": 0, "width": 18, "height": 10}}],
    )
    result = runner.invoke(
        app,
        ["dashboard", "add-tile", "dashboard1", "--insight", "insight2", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    new_tile = raw["pages"][0]["grid"]["tiles"][1]
    assert new_tile["box"] == {"top": 0, "left": 18, "width": 18, "height": 10}


def test_dashboard_add_tile_wraps_to_new_row_when_full(patch_client):
    raw = _dash_with_tiles(
        patch_client,
        [{"insightId": "i1", "box": {"left": 0, "top": 0, "width": 24, "height": 10}}],
    )
    result = runner.invoke(
        app,
        ["dashboard", "add-tile", "dashboard1", "--insight", "insight2", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    new_tile = raw["pages"][0]["grid"]["tiles"][1]
    # 24 + 18 > 36: wraps below the existing row
    assert new_tile["box"] == {"top": 10, "left": 0, "width": 18, "height": 10}


def test_dashboard_add_tile_dataset_table_gets_view_kind(patch_client):
    raw = _dash_with_tiles(patch_client, [])
    proj = patch_client.get_project("PROJ1")
    proj.get_insight("table1").get_settings().get_raw.return_value = {
        "id": "table1",
        "type": "dataset_table",
        "name": "My table",
    }
    result = runner.invoke(
        app,
        ["dashboard", "add-tile", "dashboard1", "--insight", "table1", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    tile = raw["pages"][0]["grid"]["tiles"][0]
    # without EXPLORE the tile stays blank in dashboard view mode
    assert tile["tileParams"]["viewKind"] == "EXPLORE"
    assert tile["titleOptions"]["title"] == "My table"
    # the legend switch is a chart-tile concern only
    assert "showLegend" not in tile["tileParams"]


def test_dashboard_add_tile_width_out_of_range(patch_client):
    result = runner.invoke(
        app,
        [
            "dashboard",
            "add-tile",
            "dashboard1",
            "--insight",
            "insight1",
            "--width",
            "40",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "36" in result.output


# --- validate ---


def _validate(patch_client, tiles, insights=None, page_extra=None):
    proj = patch_client.get_project("PROJ1")
    page = {"id": "p1", "grid": {"tiles": tiles}}
    page.update(page_extra or {})
    proj.get_dashboard("dashboard1").get_settings().get_raw.return_value = {
        "id": "dashboard1",
        "name": "Dash",
        "pages": [page],
    }
    proj.list_insights.return_value = insights if insights is not None else []
    return runner.invoke(app, ["dashboard", "validate", "dashboard1", "-P", "PROJ1"])


def _insight_tile(iid, box, itype="chart", **extra):
    return {
        "tileType": "INSIGHT",
        "insightId": iid,
        "insightType": itype,
        "box": box,
        **extra,
    }


def test_dashboard_validate_passes(patch_client):
    result = _validate(
        patch_client,
        [
            _insight_tile("i1", {"top": 0, "left": 0, "width": 18, "height": 10}),
            _insight_tile("i2", {"top": 0, "left": 18, "width": 18, "height": 10}),
        ],
        insights=[{"id": "i1", "type": "chart"}, {"id": "i2", "type": "chart"}],
    )
    assert result.exit_code == 0
    assert "passes pre-flight" in result.output


def test_dashboard_validate_overflowing_box(patch_client):
    result = _validate(
        patch_client,
        [_insight_tile("i1", {"top": 0, "left": 30, "width": 12, "height": 6})],
        insights=[{"id": "i1", "type": "chart"}],
    )
    assert result.exit_code == 1
    assert "overflows the 36-column grid" in result.output
    assert "clipped" in result.output


def test_dashboard_validate_overlapping_tiles(patch_client):
    result = _validate(
        patch_client,
        [
            _insight_tile("i1", {"top": 0, "left": 0, "width": 12, "height": 4}),
            _insight_tile("i2", {"top": 2, "left": 6, "width": 12, "height": 6}),
        ],
        insights=[{"id": "i1", "type": "chart"}, {"id": "i2", "type": "chart"}],
    )
    assert result.exit_code == 1
    assert "overlap" in result.output
    assert "displaces" in result.output
    # Each tile's box is named so two tiles sharing a label are still tellable apart.
    assert "(top 0, left 0, 12x4)" in result.output
    assert "(top 2, left 6, 12x6)" in result.output


def test_dashboard_validate_blank_dataset_table_tile(patch_client):
    result = _validate(
        patch_client,
        [
            _insight_tile(
                "t1",
                {"top": 0, "left": 0, "width": 36, "height": 8},
                itype="dataset_table",
            )
        ],
        insights=[{"id": "t1", "type": "dataset_table"}],
    )
    assert result.exit_code == 1
    assert "viewKind" in result.output
    assert "blank" in result.output


def test_dashboard_validate_dangling_insight_reference(patch_client):
    result = _validate(
        patch_client,
        [_insight_tile("ghost", {"top": 0, "left": 0, "width": 18, "height": 10})],
        insights=[{"id": "other", "type": "chart"}],
    )
    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_dashboard_validate_tiles_outside_grid(patch_client):
    result = _validate(
        patch_client,
        [],
        page_extra={
            "tiles": [
                _insight_tile("i1", {"top": 0, "left": 0, "width": 18, "height": 10})
            ]
        },
    )
    assert result.exit_code == 1
    assert "grid.tiles" in result.output


def test_dashboard_add_tile_invalid_page(patch_client):
    result = runner.invoke(
        app,
        [
            "dashboard",
            "add-tile",
            "dashboard1",
            "--insight",
            "insight1",
            "--page",
            "99",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


# --- remove-tile ---


def test_dashboard_remove_tile(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_dashboard("dashboard1").get_settings()
    raw = {
        "id": "dashboard1",
        "name": "Dash",
        "pages": [{"id": "p1", "grid": {"tiles": [{"insightId": "insight1"}]}}],
    }
    settings.get_raw.return_value = raw
    result = runner.invoke(
        app,
        [
            "dashboard",
            "remove-tile",
            "dashboard1",
            "--insight",
            "insight1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Removed 1 tile" in result.output
    assert raw["pages"][0]["grid"]["tiles"] == []
    settings.save.assert_called_once()


def test_dashboard_remove_tile_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "dashboard",
            "remove-tile",
            "dashboard1",
            "--insight",
            "NONEXISTENT",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_dashboard_remove_tile_scoped_to_page(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_dashboard("dashboard1").get_settings()
    raw = {
        "id": "dashboard1",
        "name": "Dash",
        "pages": [
            {"id": "p0", "grid": {"tiles": [{"insightId": "insight1"}]}},
            {"id": "p1", "grid": {"tiles": [{"insightId": "insight1"}]}},
        ],
    }
    settings.get_raw.return_value = raw
    result = runner.invoke(
        app,
        [
            "dashboard",
            "remove-tile",
            "dashboard1",
            "--insight",
            "insight1",
            "--page",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["pages"][0]["grid"]["tiles"] == []
    assert len(raw["pages"][1]["grid"]["tiles"]) == 1  # page 1 untouched
