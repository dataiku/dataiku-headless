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
        app, ["--format", "json", "recipe", "list-steps", "prep1", "--project", "PROJ1"]
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


def test_recipe_add_step_warns_on_grel_numeric_alias(patch_client):
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "CreateColumnWithGREL",
            "--params",
            '{"expression":"toLong(amount)","column":"amount_num"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "toLong() -> toNumber()" in result.output


def test_recipe_add_formula_warns_on_grel_numeric_alias(patch_client):
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-formula",
            "prep1",
            "--expr",
            "toInt(amount)",
            "--column",
            "amount_num",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "toInt() -> toNumber()" in result.output


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
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
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
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
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


def test_recipe_replace_step_runs_without_yes(patch_client):
    """replace-step is a JSON edit (WRITE), not destructive — no --yes needed."""
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
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["steps"][0]["type"] == "ColumnRenamer"


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
            "--format",
            "json",
            "recipe",
            "get-step",
            "prep1",
            "--index",
            "0",
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


def test_recipe_add_formula_warns_on_status_errors(patch_client):
    """A saved formula step that fails the DSS status check warns at submit
    time (e.g. `substr` — GREL only has `substring`) instead of exploding two
    commands later at apply-schema. Non-blocking: exit 0, step saved."""
    _proj, recipe_mock, settings = _setup_prepare_mock(patch_client)
    recipe_mock.get_status.return_value.get_status_messages.return_value = [
        {
            "severity": "ERROR",
            "code": "ERR_RECIPE",
            "title": "Invalid formula",
            "message": "Unknown function 'substr'",
        }
    ]
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-formula",
            "prep1",
            "--expr",
            "substr(date,0,7)",
            "--column",
            "month",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.save.assert_called_once()
    flat = " ".join(result.output.split())
    assert "Unknown function 'substr'" in flat
    assert "lint-formula" in flat


def test_recipe_add_formula_no_warning_when_status_clean(patch_client):
    """No status errors → no lint noise after the success line."""
    _proj, recipe_mock, _settings = _setup_prepare_mock(patch_client)
    recipe_mock.get_status.return_value.get_status_messages.return_value = []
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
    assert result.exit_code == 0, result.output
    assert "status check" not in result.output


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
    # --action is a click.Choice(FilterAction): the FilterOnCustomFormula /
    # FilterOnValue processors this command emits support only KEEP_ROW /
    # REMOVE_ROW, so CLEAR_CELL / FLAG die at parse time (exit 2, usage error)
    # with the valid set shown — before the command body runs.
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
    assert result.exit_code == 2, result.output
    out = result.output.lower()
    assert "invalid value for '--action'" in out
    assert "keep_row" in out and "remove_row" in out
    # Parse error → command body never ran → no step written.
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


# ── NET-NEW (PR surface): step ordering (--at), DateParser/DateFormatter
# shape guards, ColumnsSelector SINGLE_COLUMN/COLUMNS guard, fill-empty
# schema pre-flight, filter-rows GREL unit lint ──────────────────────


def test_recipe_add_step_columns_mode_multi_list_no_warning(patch_client):
    """appliesTo='COLUMNS' with several columns is correct — no false positive."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "ColumnsSelector",
            "--params",
            '{"appliesTo":"COLUMNS","keep":true,"columns":["begin_date","end_date"]}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "silently applies" not in result.output
    settings.save.assert_called_once()


def test_recipe_add_step_single_column_multi_list_warns(patch_client):
    """ColumnsSelector with appliesTo='SINGLE_COLUMN' but several columns is a
    silent data-loss trap — DSS applies the step to only the first column (e.g.
    keep:true drops the rest with no error). The guard warns but still saves."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "ColumnsSelector",
            "--params",
            '{"appliesTo":"SINGLE_COLUMN","keep":true,"columns":["begin_date","end_date"]}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "COLUMNS" in result.output
    assert "begin_date" in result.output
    settings.save.assert_called_once()


def test_recipe_add_step_dateformatter_appliesto_columns_shape_rejected(patch_client):
    """DateFormatter with the appliesTo/columns[] shape (correct for DateParser /
    StringTransformer, WRONG for DateFormatter) must also be caught — DSS otherwise
    returns the same misleading 'Empty column name' error only at run time. The
    example surfaced in the error must pull the column name out of columns[]."""
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
            '{"appliesTo":"SINGLE_COLUMN","columns":["Begin_dt"],'
            '"format":"yyyy-MM-dd HH:mm:ss","timezone_id":"UTC"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "inCol" in result.output
    assert "Begin_dt" in result.output  # example carries the real column name
    settings.save.assert_not_called()


def test_recipe_add_step_dateformatter_correct_incol_accepted(patch_client):
    """The correct inCol/outCol shape must pass the guard (no false positive even
    though 'columns' could appear in other contexts)."""
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
            '{"inCol":"Begin_dt","outCol":"Begin_Date","format":"yyyy-MM-dd HH:mm:ss"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.save.assert_called_once()


def test_recipe_add_step_dateparser_normalizes_string_outtype(patch_client):
    """A bare-string outType saves but the build fails — the CLI normalizes it
    to the object form and warns."""
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
            '{"appliesTo":"SINGLE_COLUMN","columns":["ts"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"parsed","outType":"dateonly"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "outType" in result.output
    assert "Normalized" in result.output
    saved_step = settings.raw_steps[-1]
    assert saved_step["params"]["outType"] == {"name": "out", "type": "dateonly"}


def test_recipe_add_step_dateparser_object_outtype_not_touched(patch_client):
    """An object outType passes through unchanged (no normalization warning)."""
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "DateParser",
            "--params",
            '{"appliesTo":"SINGLE_COLUMN","columns":["ts"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"parsed","outType":{"name":"out","type":"dateonly"}}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Normalized" not in result.output


def test_recipe_add_formula_at_index(patch_client):
    """add-formula --at inserts mid-pipeline instead of appending."""
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
            "add-formula",
            "prep1",
            "--column",
            "Score",
            "--expr",
            'if(Score == "__BLANK__", "", Score)',
            "--at",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    steps = settings.obj_payload["steps"]
    assert len(steps) == 3
    assert steps[1]["type"] == "CreateColumnWithGREL"
    assert steps[1]["params"]["column"] == "Score"
    assert steps[0]["type"] == "Step0" and steps[2]["type"] == "Step1"


def test_recipe_add_formula_at_out_of_range(patch_client):
    """--at past the end is a prescriptive error, not a silent append."""
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Step0", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-formula",
            "prep1",
            "--column",
            "x",
            "--expr",
            "1",
            "--at",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output
    settings.save.assert_not_called()


def test_recipe_add_fill_empty_at_index(patch_client):
    """add-fill-empty --at lands a sentinel-fill BEFORE a later fold step."""
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "MultiColumnFold", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fill-empty",
            "prep1",
            "--column",
            "c1",
            "--value",
            "__BLANK__",
            "--at",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    steps = settings.obj_payload["steps"]
    assert len(steps) == 2
    assert steps[0]["type"] == "FillEmptyWithValue"
    assert steps[1]["type"] == "MultiColumnFold"


def test_recipe_add_fill_empty_warns_on_unknown_column(patch_client):
    """Pre-flight warning when --column doesn't match the input schema —
    catches the silent NB_COMMANDES (uppercase) typo that creates a phantom
    all-zero column. Warning only; step still appends."""
    proj, _recipe, settings = _setup_prepare_mock(patch_client)
    settings.get_flat_input_refs.return_value = ["input_ds"]
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [{"name": "nb_commandes"}, {"name": "client_id"}]
    }
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fill-empty",
            "prep1",
            "--column",
            "NB_COMMANDES",
            "--value",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    output = result.output
    # Warning surfaces the typo with a "did you mean" hint
    assert "NB_COMMANDES" in output
    assert "not found in input schema" in output
    assert "nb_commandes" in output  # closest-match suggestion
    # Step still appended (warning, not block)
    assert settings.obj_payload["steps"][0]["params"]["columns"] == ["NB_COMMANDES"]


def test_recipe_add_fill_empty_silent_when_column_matches(patch_client):
    """No warning when --column matches the input schema exactly."""
    proj, _recipe, settings = _setup_prepare_mock(patch_client)
    settings.get_flat_input_refs.return_value = ["input_ds"]
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [{"name": "age"}, {"name": "income"}]
    }
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
    assert "not found in input schema" not in result.output


def test_recipe_add_filter_rows_warns_on_grel_singular_unit(patch_client):
    """`inc(now(), -5, "year")` silently matches no rows — emit a warning
    nudging towards plural unit literals."""
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--formula",
            'date > inc(now(), -5, "year")',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    output = result.output
    assert "unrecognized unit literal" in output
    assert '"years"' in output  # plural suggestion


def test_recipe_add_filter_rows_no_warning_on_valid_units(patch_client):
    """Valid plural units don't trigger the warning."""
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--formula",
            'diff(now(), date_col, "years") < 5',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "unrecognized unit" not in result.output


def test_recipe_add_find_replace_ignore_case(patch_client):
    """--ignore-case sets normalization LOWERCASE (case-insensitive match)."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-find-replace",
            "prep1",
            "--column",
            "Region",
            "--find",
            "Europe",
            "--replace",
            "Europe",
            "--matching",
            "FULL_STRING",
            "--ignore-case",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["normalization"] == "LOWERCASE"


def test_recipe_add_find_replace_exact_by_default(patch_client):
    """Without --ignore-case the normalization stays EXACT."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-find-replace",
            "prep1",
            "--column",
            "Region",
            "--find",
            "a",
            "--replace",
            "b",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["normalization"] == "EXACT"


# -- processor-type validation at add/replace time --


def test_recipe_add_step_rejects_known_wrong_type(patch_client):
    """AddId doesn't exist — die at add time with the real alternative,
    not at run time with DSS's misleading 'plugin not installed'."""
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "AddId",
            "--params",
            "{}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not a stock Prepare processor" in result.output
    assert "rowNumber" in result.output


def test_recipe_add_step_filteronformula_suggests_custom_formula(patch_client):
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "FilterOnFormula",
            "--params",
            '{"expression":"a>1"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "FilterOnCustomFormula" in result.output


def test_recipe_add_step_unknown_type_warns_but_proceeds(patch_client):
    """Unknown types only warn — the curated list isn't exhaustive and
    plugin processors are legitimate."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "SomePluginProcessor",
            "--params",
            "{}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "known stock-processor list" in result.output
    assert len(settings.obj_payload["steps"]) == 1


def test_recipe_add_step_known_type_no_warning(patch_client):
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-step",
            "prep1",
            "--type",
            "ColumnRenamer",
            "--params",
            '{"renamings":[]}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "known stock-processor list" not in result.output


def test_recipe_replace_step_rejects_known_wrong_type(patch_client):
    _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "ColumnRenamer", "params": {}}],
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
            "Enumerator",
            "--params",
            "{}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not a stock Prepare processor" in result.output


# -- flag aliases (recurring agent guesses) --


def test_recipe_add_formula_expression_alias(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-formula",
            "prep1",
            "--expression",
            "upper(city)",
            "--column",
            "city_up",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["expression"] == "upper(city)"


def test_recipe_add_filter_rows_expr_alias(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-filter-rows",
            "prep1",
            "--expr",
            "price > 100",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FilterOnCustomFormula"
    assert step["params"]["expression"] == "price > 100"


# -- add-rename --mappings shorthand + prescriptive parse error --


def test_recipe_add_rename_mappings_shorthand(patch_client):
    """'old:new,old2:new2' — the colon syntax the CLI trains elsewhere."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-rename",
            "prep1",
            "--mappings",
            "1:CSA, 2:CBSA",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["renamings"] == [
        {"from": "1", "to": "CSA"},
        {"from": "2", "to": "CBSA"},
    ]


def test_recipe_add_rename_mappings_bad_input_prescriptive(patch_client):
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-rename",
            "prep1",
            "--mappings",
            "a:b:c,d",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "old1:new1,old2:new2" in result.output
    assert "--from" in result.output


def test_recipe_add_rename_mappings_bad_json_prescriptive(patch_client):
    _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-rename",
            "prep1",
            "--mappings",
            '{"a":"b",}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not valid JSON" in result.output
    assert "old1:new1" in result.output


# ---------------------------------------------------------------------------
# apply-spec — declarative multi-step build
# ---------------------------------------------------------------------------


def _apply(spec, *extra):
    return runner.invoke(
        app,
        [
            "recipe",
            "apply-spec",
            "prep1",
            json.dumps(spec),
            "--project",
            "PROJ1",
            *extra,
        ],
    )


def test_apply_spec_mixed_ops_and_raw(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    spec = [
        {"op": "formula", "column": "total", "expr": "price*qty"},
        {"op": "rename", "mappings": {"old": "new"}},
        {"op": "delete-columns", "columns": ["tmp", "scratch"]},
        {
            "type": "FillEmptyWithValue",
            "params": {"appliesTo": "SINGLE_COLUMN", "columns": ["age"], "value": "0"},
        },
    ]
    result = _apply(spec)
    assert result.exit_code == 0, result.output
    steps = settings.obj_payload["steps"]
    assert len(steps) == 4
    assert steps[0]["type"] == "CreateColumnWithGREL"
    assert steps[0]["params"] == {"expression": "price*qty", "column": "total"}
    assert steps[1]["type"] == "ColumnRenamer"
    assert steps[1]["params"]["renamings"] == [{"from": "old", "to": "new"}]
    assert steps[2]["type"] == "ColumnsSelector"
    assert steps[2]["params"]["keep"] is False
    assert steps[3]["type"] == "FillEmptyWithValue"
    settings.save.assert_called_once()


def test_apply_spec_appends_to_existing(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Existing", "params": {}}],
    )
    result = _apply([{"op": "delete-columns", "columns": ["x"]}])
    assert result.exit_code == 0, result.output
    steps = settings.obj_payload["steps"]
    assert len(steps) == 2
    assert steps[0]["type"] == "Existing"
    assert steps[1]["type"] == "ColumnsSelector"


def test_apply_spec_replace_clears_existing(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(
        patch_client,
        steps=[{"metaType": "PROCESSOR", "type": "Existing", "params": {}}],
    )
    result = _apply([{"op": "delete-columns", "columns": ["x"]}], "--replace")
    assert result.exit_code == 0, result.output
    steps = settings.obj_payload["steps"]
    assert len(steps) == 1
    assert steps[0]["type"] == "ColumnsSelector"
    assert "replaced existing" in result.output


def test_apply_spec_name_and_disabled(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    spec = [
        {
            "op": "formula",
            "column": "c",
            "expr": "1",
            "name": "set one",
            "disabled": True,
        }
    ]
    result = _apply(spec)
    assert result.exit_code == 0, result.output
    step = settings.obj_payload["steps"][0]
    assert step["name"] == "set one"
    assert step["disabled"] is True


def test_apply_spec_equivalence_with_shortcuts(patch_client):
    """An op entry must produce the identical step the add-* shortcut emits —
    pins the shared builders so the two surfaces can't drift."""
    # add-formula
    _p, _r, s1 = _setup_prepare_mock(patch_client)
    runner.invoke(
        app,
        [
            "recipe",
            "add-formula",
            "prep1",
            "--expr",
            "upper(city)",
            "--column",
            "cu",
            "--project",
            "PROJ1",
        ],
    )
    shortcut_step = s1.obj_payload["steps"][0]

    _p, _r, s2 = _setup_prepare_mock(patch_client)
    _apply([{"op": "formula", "column": "cu", "expr": "upper(city)"}])
    spec_step = s2.obj_payload["steps"][0]
    assert spec_step == shortcut_step


def test_apply_spec_unknown_op_rejected_with_index(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = _apply(
        [{"op": "formula", "column": "c", "expr": "1"}, {"op": "bogus", "x": 1}]
    )
    assert result.exit_code != 0
    assert "[1]" in result.output
    assert "bogus" in result.output
    settings.save.assert_not_called()


def test_apply_spec_missing_required_key_rejected(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = _apply([{"op": "formula", "column": "c"}])  # no expr
    assert result.exit_code != 0
    assert "[0]" in result.output
    assert "expr" in result.output
    settings.save.assert_not_called()


def test_apply_spec_raw_step_runs_normalization(patch_client):
    """The raw escape routes through _normalize_raw_step — a string DateParser
    outType is normalized to the object form, same as add-step."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    spec = [
        {
            "type": "DateParser",
            "params": {
                "appliesTo": "SINGLE_COLUMN",
                "columns": ["ts"],
                "outCol": "parsed",
                "outType": "dateonly",
            },
        }
    ]
    result = _apply(spec)
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["steps"][0]["params"]["outType"] == {
        "name": "out",
        "type": "dateonly",
    }


def test_apply_spec_raw_step_wrong_processor_rejected(patch_client):
    """The raw escape enforces _validate_processor_type — a known-wrong type
    aborts the whole batch before saving."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = _apply([{"type": "FilterOnFormula", "params": {}}])
    assert result.exit_code != 0
    assert settings.obj_payload["steps"] == []
    settings.save.assert_not_called()


def test_apply_spec_not_an_array_rejected(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = _apply({"op": "formula", "column": "c", "expr": "1"})
    assert result.exit_code != 0
    assert "array" in result.output.lower()
    settings.save.assert_not_called()


def test_apply_spec_empty_array_rejected(patch_client):
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
    result = _apply([])
    assert result.exit_code != 0
    assert "empty" in result.output.lower()


def test_apply_spec_wrong_recipe_type(patch_client):
    """Non-prepare recipe gives prescriptive error, nothing saved."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "apply-spec",
            "recipe1",
            json.dumps([{"op": "delete-columns", "columns": ["x"]}]),
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not 'prepare'" in result.output
