"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

import json
from tests.commands.recipe.helpers import app, runner
from tests.commands.recipe.helpers import setup_prepare_mock as _setup_prepare_mock


# Prepare recipe step commands
# ---------------------------------------------------------------------------


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


def test_recipe_add_step_dateformatter_wrong_param_names_rejected(patch_client):
    """DateFormatter with legacy 'column'/'outputColumn' must be caught before it
    hits DSS (which returns a misleading 'Empty column name' error). Correct
    params are inCol/outCol."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "DateFormatter",
            "--params",
            '{"column":"ts","outputColumn":"fmt","format":"yyyy-MM-dd","timezone_id":"UTC"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "inCol" in result.output
    assert "Empty column name" in result.output
    settings.save.assert_not_called()


def test_recipe_add_step_datetruncate_wrong_param_names_rejected(patch_client):
    """DateTruncate with legacy 'column' must be caught. Correct params use
    inCol/outCol + datePart."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "DateTruncate",
            "--params",
            '{"column":"ts","unit":"DAY"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "inCol" in result.output
    settings.save.assert_not_called()


def test_recipe_add_step_unixtimestampparser_wrong_param_names_rejected(patch_client):
    """UNIXTimestampParser with legacy 'column' must be caught. Correct params
    use inCol/outCol + milliseconds (boolean)."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "UNIXTimestampParser",
            "--params",
            '{"column":"ts","unit":"SECONDS"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "inCol" in result.output
    settings.save.assert_not_called()


def test_recipe_add_step_create_column_with_grel_expr_typo_rejected(patch_client):
    """CreateColumnWithGREL with params.expr (typo for params.expression) must be
    caught before save. DSS silently ignores unknown processor params, so the
    formula becomes a no-op without any error — only surfaces when real data
    arrives. The shortcut add-formula --expr maps to params.expression."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "CreateColumnWithGREL",
            "--params",
            '{"column":"x","expr":"toNumber(duration)"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "expression" in result.output
    assert "expr" in result.output
    settings.save.assert_not_called()


def test_recipe_add_step_create_column_with_grel_expression_accepted(patch_client):
    """CreateColumnWithGREL with the correct 'expression' key passes validation."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "CreateColumnWithGREL",
            "--params",
            '{"column":"x","expression":"toNumber(duration)"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.save.assert_called_once()


def test_recipe_add_step_dateformatter_correct_params_accepted(patch_client):
    """DateFormatter with correct inCol/outCol params must pass CLI validation."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "DateFormatter",
            "--params",
            '{"inCol":"ts","outCol":"fmt","format":"yyyy-MM-dd","timezone_id":"UTC"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.save.assert_called_once()


def test_recipe_add_step_warns_dateparser_no_outcol(patch_client):
    """DateParser without outCol silently produces nulls — CLI should warn."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "DateParser",
            "--params",
            '{"appliesTo":"SINGLE_COLUMN","columns":["ts"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outType":{"name":"out","type":"date"}}',
            "--project",
            "PROJ1",
        ],
    )
    # Should succeed but with a warning
    assert result.exit_code == 0
    assert "outCol" in result.output
    assert "nulls" in result.output


def test_recipe_add_step_dateparser_with_outcol_no_warning(patch_client):
    """DateParser with outCol should not warn."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "DateParser",
            "--params",
            '{"appliesTo":"SINGLE_COLUMN","columns":["ts"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"parsed","outType":{"name":"out","type":"date"}}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "nulls" not in result.output


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
            "--yes",
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
            "--yes",
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
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


# -- replace-step --


def test_recipe_replace_step_with_type_and_params(patch_client):
    """replace-step swaps the step at --index for the new type+params, atomic."""
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Step0", "params": {"v": 0}},
            {"metaType": "PROCESSOR", "type": "Step1", "params": {"v": 1}},
            {"metaType": "PROCESSOR", "type": "Step2", "params": {"v": 2}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "1",
            "--type",
            "ColumnRenamer",
            "--params",
            '{"renamings":[{"from":"a","to":"b"}]}',
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    steps = settings.obj_payload["steps"]
    assert len(steps) == 3  # surrounding steps preserved
    assert steps[0]["type"] == "Step0"
    assert steps[1]["type"] == "ColumnRenamer"
    assert steps[1]["params"] == {"renamings": [{"from": "a", "to": "b"}]}
    assert steps[1]["metaType"] == "PROCESSOR"
    assert steps[2]["type"] == "Step2"
    settings.save.assert_called_once()


def test_recipe_replace_step_with_definition(patch_client):
    """--definition replaces the step with a full JSON object."""
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[
            {"metaType": "PROCESSOR", "type": "Old", "params": {}},
        ],
    )
    full = json.dumps(
        {"type": "FillEmptyWithValue", "params": {"column": "x", "value": "0"}}
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "0",
            "--definition",
            full,
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FillEmptyWithValue"
    assert step["params"] == {"column": "x", "value": "0"}
    # metaType auto-defaulted
    assert step["metaType"] == "PROCESSOR"


def test_recipe_replace_step_preserves_name_when_provided(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Old", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "0",
            "--type",
            "ColumnRenamer",
            "--params",
            "{}",
            "--name",
            "Renamed step",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["steps"][0]["name"] == "Renamed step"


def test_recipe_replace_step_blocks_without_yes(patch_client):
    """Safety guard fires without --yes (exit 77)."""
    _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Old", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "0",
            "--type",
            "ColumnRenamer",
            "--params",
            "{}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 77


def test_recipe_replace_step_out_of_range(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Step0", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "5",
            "--type",
            "ColumnRenamer",
            "--params",
            "{}",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


def test_recipe_replace_step_requires_type_or_definition(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Old", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "0",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "either --definition or both --type and --params" in result.output


def test_recipe_replace_step_definition_must_be_object(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Old", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "replace-step",
            "prep1",
            "--index",
            "0",
            "--definition",
            "[1, 2, 3]",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "JSON object" in result.output


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
    assert step["params"]["action"] == "KEEP_ROW"


def test_recipe_add_filter_rows_explicit_remove(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--formula",
            "price > 100",
            "--action",
            "REMOVE_ROW",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["action"] == "REMOVE_ROW"


def test_recipe_add_filter_rows_rejects_unsupported_action(patch_client):
    # The FilterOnCustomFormula / FilterOnValue processors this command emits
    # support only KEEP_ROW / REMOVE_ROW. CLEAR_CELL / FLAG must be rejected
    # (they were previously advertised in --help but never validated).
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--formula",
            "price > 100",
            "--action",
            "CLEAR_CELL",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "KEEP_ROW" in result.output and "REMOVE_ROW" in result.output
    # No step should have been written for the invalid action.
    assert settings.obj_payload["steps"] == []


def test_recipe_add_filter_rows_action_case_insensitive(patch_client):
    # --action is normalized; lowercase input maps to the canonical value.
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--formula",
            "price > 100",
            "--action",
            "remove_row",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["action"] == "REMOVE_ROW"


def test_recipe_add_geodistance_unit_case_insensitive(patch_client):
    # --unit is a GeoDistanceUnitMiles click.Choice wired case_sensitive=False;
    # lowercase input must still parse and the payload keeps the canonical case.
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from",
            "origin",
            "--to",
            "destination",
            "--unit",
            "kilometers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "GeoDistanceProcessor"
    assert step["params"]["outputUnit"] == "KILOMETERS"


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
    assert step["params"]["appliesTo"] == "SINGLE_COLUMN"
    assert step["params"]["columns"] == ["age"]
    assert step["params"]["value"] == "0"


def test_recipe_add_fill_empty_repeatable_column(patch_client):
    """Multiple --column flags produce ONE step covering all columns with appliesTo=COLUMNS."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fill-empty",
            "prep1",
            "--column",
            "HBO",
            "--column",
            "Netflix",
            "--column",
            "ESPN",
            "--value",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 1
    step = settings.obj_payload["steps"][0]
    assert step["params"]["appliesTo"] == "COLUMNS"
    assert step["params"]["columns"] == ["HBO", "Netflix", "ESPN"]


def test_recipe_add_fill_empty_csv_columns(patch_client):
    """--columns CSV alternative produces ONE multi-column step."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fill-empty",
            "prep1",
            "--columns",
            "HBO,Netflix,ESPN",
            "--value",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 1
    step = settings.obj_payload["steps"][0]
    assert step["params"]["appliesTo"] == "COLUMNS"
    assert step["params"]["columns"] == ["HBO", "Netflix", "ESPN"]


def test_recipe_add_fill_empty_no_columns_errors(patch_client):
    """Neither --column nor --columns provided → prescriptive error."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fill-empty",
            "prep1",
            "--value",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    settings.save.assert_not_called()


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


def test_recipe_create_window_lag_offsets(patch_client):
    """--lag-offsets COL:1,2,3 writes lagValues comma-list and lag=true."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "mw",
            "-i",
            "data",
            "--output-ds",
            "out",
            "-k",
            "stock",
            "--order-key",
            "date",
            "--lag-offsets",
            "price:1,2,3,4,5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    values = settings.obj_payload["values"]
    price_entry = next(v for v in values if v["column"] == "price")
    assert price_entry["lag"] is True
    assert price_entry["lagValues"] == "1,2,3,4,5"


def test_recipe_create_window_lead_offsets(patch_client):
    """--lead-offsets COL:1,2 writes leadValues."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "mw",
            "-i",
            "data",
            "--output-ds",
            "out",
            "--lead-offsets",
            "y:1,2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    values = settings.obj_payload["values"]
    y_entry = next(v for v in values if v["column"] == "y")
    assert y_entry["lead"] is True
    assert y_entry["leadValues"] == "1,2"


def test_recipe_create_window_rename(patch_client):
    """--rename SRC:DST writes outputColumnNameOverrides dict."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w",
            "-i",
            "data",
            "--output-ds",
            "out",
            "--rename",
            "Value_lag1:lag1_3",
            "--rename",
            "Value_lag2:lag2_3",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["outputColumnNameOverrides"] == {
        "Value_lag1": "lag1_3",
        "Value_lag2": "lag2_3",
    }


def test_recipe_create_window_frame(patch_client):
    """--frame-preceding/--frame-following set windows[0] frame fields."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w",
            "-i",
            "data",
            "--output-ds",
            "out",
            "-k",
            "stock",
            "--order-key",
            "date",
            "--frame-preceding",
            "2",
            "--frame-following",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    win0 = settings.obj_payload["windows"][0]
    assert win0["enableLimits"] is True
    assert win0["limitPreceding"] is True
    assert win0["precedingRows"] == 2
    assert win0["limitFollowing"] is True
    assert win0["followingRows"] == 0


def test_recipe_create_window_frame_unbounded(patch_client):
    """--frame-unbounded sets the unbounded full-partition frame.

    The DSS Window default is cumulative within partition (UNBOUNDED PRECEDING
    TO CURRENT ROW). --frame-unbounded must produce a true full-partition
    aggregate — same value for every row in the partition. That requires both
    enableLimits=True with both limit flags cleared AND the payload-level
    legacyUnboundedWindowStreamBehavior=True flag (without the legacy flag
    DSS still streams cumulatively).
    """
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w",
            "-i",
            "data",
            "--output-ds",
            "out",
            "--frame-unbounded",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    win0 = settings.obj_payload["windows"][0]
    assert win0["enableLimits"] is True
    assert win0["limitPreceding"] is False
    assert win0["limitFollowing"] is False
    assert settings.obj_payload["legacyUnboundedWindowStreamBehavior"] is True


def test_recipe_create_window_cume_dist_and_ntile(patch_client):
    """--enable-cume-dist + --enable-ntile N set top-level booleans + ntileValues."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w",
            "-i",
            "data",
            "--output-ds",
            "out",
            "--enable-cume-dist",
            "--enable-ntile",
            "10",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["cumeDist"] is True
    assert settings.obj_payload["ntile"] is True
    assert settings.obj_payload["ntileValues"] == 10


def test_recipe_create_group_extended_aggs_first_last_concat_distinct(patch_client):
    """Extended aggs (first, last, first_last_not_null, concat_distinct, sum2) patch the column dict."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    cs = {}
    settings.set_column_aggregations.return_value = cs

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "g",
            "-i",
            "data",
            "--output-ds",
            "out",
            "-k",
            "k",
            "--agg",
            "x:first,last,first_last_not_null,concat_distinct,sum2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert cs["first"] is True
    assert cs["last"] is True
    assert cs["firstLastNotNull"] is True
    assert cs["concatDistinct"] is True
    assert cs["sum2"] is True


def test_recipe_create_group_rename(patch_client):
    """--rename writes outputColumnNameOverrides on the Group payload."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "g",
            "-i",
            "data",
            "--output-ds",
            "out",
            "-k",
            "k",
            "--agg",
            "x:count",
            "--rename",
            "Customer_ID_count:Count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["outputColumnNameOverrides"] == {
        "Customer_ID_count": "Count"
    }


def test_recipe_create_group_rename_group_key(patch_client):
    """--rename also renames the group-key column, not only aggregates.

    Verified live on Challenge_019 (Alteryx Excel-record-locator migration):
    `--rename FileName:'XLS File'` produced an output dataset with the group-key
    column renamed in place — no downstream Prepare add-rename required.
    """
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "g",
            "-i",
            "data",
            "--output-ds",
            "out",
            "-k",
            "FileName",
            "--agg",
            "v:max",
            "--rename",
            "FileName:XLS File",
            "--rename",
            "v_max:Value",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["outputColumnNameOverrides"] == {
        "FileName": "XLS File",
        "v_max": "Value",
    }


def test_recipe_create_topn_bottom_columns_rename_and_rank_flags(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "worst",
            "-i",
            "sales",
            "--output-ds",
            "worst3",
            "--bottom",
            "3",
            "--sort-col",
            "revenue",
            "--rank",
            "--row-number",
            "--columns",
            "id,revenue,rank",
            "--rename",
            "rank:rk",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    p = settings.obj_payload
    assert p["topN"] == 3
    assert p["firstRows"] == 0
    assert p["lastRows"] == 3
    assert p["rank"] is True
    assert p["rowNumber"] is True
    assert p["retrievedColumnsSelectionMode"] == "SELECTED"
    assert p["retrievedColumns"] == ["id", "revenue", "rank"]
    assert p["outputColumnNameOverrides"] == {"rank": "rk"}
