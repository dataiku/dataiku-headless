"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

from tests.commands.recipe.helpers import app, runner
from tests.helpers import strip_ansi as _strip_ansi

# ── Visual recipe: create-stack ───────────────────────────────────────


def test_recipe_create_stack_basic(patch_client):
    """Basic stack recipe creation with 2 inputs, no origin column."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created stack recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("vstack", "merge")
    builder = proj.new_recipe.return_value
    assert builder.with_input.call_count == 2
    builder.with_existing_output.assert_called_once_with("all")
    builder.build.assert_called_once()


def test_recipe_create_stack_requires_two_inputs(patch_client):
    """Stack needs >= 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "at least 2" in result.output


def test_recipe_create_stack_with_origin_column(patch_client):
    """--origin-column calls settings.add_origin_column with empty label map."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "customers",
            "-i",
            "prospects",
            "--output-ds",
            "people",
            "--origin-column",
            "source",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.add_origin_column.assert_called_once_with("source", {})
    settings.save.assert_called()
    assert "Origin column: source" in result.output


def test_recipe_create_stack_with_origin_labels(patch_client):
    """--origin-label INDEX:VALUE builds the dataset_origin_mapping dict."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "customers",
            "-i",
            "prospects",
            "--output-ds",
            "people",
            "--origin-column",
            "source",
            "--origin-label",
            "0:active",
            "--origin-label",
            "1:lead",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.add_origin_column.assert_called_once_with(
        "source", {0: "active", 1: "lead"}
    )


def test_recipe_create_stack_origin_label_without_column_errors(patch_client):
    """--origin-label without --origin-column is a prescriptive error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--origin-label",
            "0:foo",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--origin-label requires --origin-column" in result.output


def test_recipe_create_stack_origin_label_bad_format(patch_client):
    """--origin-label without ':' separator is rejected."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--origin-column",
            "src",
            "--origin-label",
            "no_colon",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --origin-label" in result.output


def test_recipe_create_stack_origin_label_index_out_of_range(patch_client):
    """--origin-label index beyond inputs count is rejected with guidance."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--origin-column",
            "src",
            "--origin-label",
            "5:foo",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "out of range" in result.output


def test_recipe_create_stack_mode_intersect(patch_client):
    """--mode INTERSECT calls set_intersection_input_schema_mode."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "INTERSECT",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.set_intersection_input_schema_mode.assert_called_once()
    settings.save.assert_called()


def test_recipe_create_stack_mode_from_dataset(patch_client):
    """--mode FROM_DATASET:NAME calls set_from_dataset_input_schema_mode."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "FROM_DATASET:a",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.set_from_dataset_input_schema_mode.assert_called_once_with("a")


def test_recipe_create_stack_mode_from_dataset_must_be_input(patch_client):
    """FROM_DATASET must reference one of the input dataset names."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "FROM_DATASET:missing",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "not an input" in result.output


def test_recipe_create_stack_mode_invalid(patch_client):
    """Unknown --mode value is rejected with guidance."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "bogus",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --mode" in result.output


def test_recipe_create_stack_mode_union_rejects_suffix(patch_client):
    """UNION and INTERSECT don't accept FROM_DATASET-style suffixes."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "UNION:a",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Only FROM_DATASET / FROM_INDEX accept" in result.output


def test_recipe_create_stack_mode_intersect_rejects_suffix(patch_client):
    """INTERSECT doesn't accept a dataset suffix."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "INTERSECT:a",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Only FROM_DATASET / FROM_INDEX accept" in result.output


def test_recipe_create_stack_mode_remap(patch_client):
    """--mode REMAP sets payload mode + selectedColumns + per-input columnsMatch."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"virtualInputs": [{"index": 0}, {"index": 1}]}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "orders",
            "-i",
            "sales",
            "--output-ds",
            "all",
            "--mode",
            "REMAP",
            "--columns",
            "id,amount,date",
            "--columns-match",
            "0:order_id,total,order_date",
            "--columns-match",
            "1:sale_id,price,sold_at",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["mode"] == "REMAP"
    assert settings.obj_payload["selectedColumns"] == ["id", "amount", "date"]
    vi = settings.obj_payload["virtualInputs"]
    assert vi[0]["columnsMatch"] == ["order_id", "total", "order_date"]
    assert vi[1]["columnsMatch"] == ["sale_id", "price", "sold_at"]
    settings.save.assert_called()


def test_recipe_create_stack_remap_requires_columns(patch_client):
    """REMAP without --columns fails with prescriptive error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "REMAP",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "REMAP requires --columns" in result.output


def test_recipe_create_stack_remap_columns_match_length_must_equal_columns(
    patch_client,
):
    """--columns-match length must equal --columns length."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--mode",
            "REMAP",
            "--columns",
            "id,amount,date",
            "--columns-match",
            "0:x,y",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--columns-match 0: got 2 source columns" in result.output


def test_recipe_create_stack_columns_match_rejected_outside_remap(patch_client):
    """--columns-match outside REMAP mode is rejected."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--columns-match",
            "0:x,y",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--columns-match is only valid with --mode REMAP" in result.output


def test_recipe_create_stack_columns_projection_in_union(patch_client):
    """--columns alone (no REMAP) switches to CUSTOM mode + selectedColumns (#232)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {
        "virtualInputs": [{"index": 0}, {"index": 1}],
        "mode": "UNION",
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--columns",
            "id,amount",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    # DSS ignores selectedColumns in UNION mode; the projection only takes
    # effect in CUSTOM column-selection mode.
    assert settings.obj_payload["mode"] == "CUSTOM"
    assert settings.obj_payload["selectedColumns"] == ["id", "amount"]


def test_recipe_create_stack_input_filter_and_post_filter(patch_client):
    """--input-filter and --post-filter set preFilter on virtualInput and top-level postFilter."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {
        "virtualInputs": [{"index": 0}, {"index": 1}],
        "mode": "UNION",
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-stack",
            "merge",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "all",
            "--input-filter",
            '0:status=="active"',
            "--post-filter",
            "amount > 0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    pre = settings.obj_payload["virtualInputs"][0]["preFilter"]
    assert pre["enabled"] is True
    # DSS reads the top-level ``expression`` when ``uiData.mode == "CUSTOM"``;
    # placing it inside uiData silently disables the filter (see
    # dataiku/references/visual-conditions.md § Formula Mode).
    assert pre["expression"] == 'status=="active"'
    assert pre["uiData"]["mode"] == "CUSTOM"
    post = settings.obj_payload["postFilter"]
    assert post["enabled"] is True
    assert post["expression"] == "amount > 0"
    assert post["uiData"]["mode"] == "CUSTOM"


# ── Visual recipe: create-split ──────────────────────────────────────


def test_recipe_create_split_values_mode(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "route",
            "-i",
            "orders",
            "--output-ds",
            "active",
            "--output-ds",
            "lapsed",
            "--mode",
            "VALUES",
            "--column",
            "status",
            "--value-split",
            "active=0",
            "--value-split",
            "lapsed=1",
            "--default-output",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = settings.obj_payload
    assert payload["mode"] == "VALUES"
    assert payload["column"] == "status"
    assert payload["valueSplits"] == [
        {"outputIndex": 0, "value": "active"},
        {"outputIndex": 1, "value": "lapsed"},
    ]
    assert payload["defaultOutputIndex"] == 1


def test_recipe_create_split_random_mode(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "tt",
            "-i",
            "rows",
            "--output-ds",
            "train",
            "--output-ds",
            "test",
            "--mode",
            "RANDOM",
            "--random-share",
            "0:70",
            "--random-share",
            "1:30",
            "--seed",
            "42",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = settings.obj_payload
    assert payload["mode"] == "RANDOM"
    assert payload["seed"] == 42
    assert payload["randomSplits"] == [
        {"outputIndex": 0, "share": 70.0},
        {"outputIndex": 1, "share": 30.0},
    ]


def test_recipe_create_split_filter_mode(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "tag",
            "-i",
            "rows",
            "--output-ds",
            "vip",
            "--output-ds",
            "rest",
            "--mode",
            "FILTER",
            "--filter-split",
            "spend>1000=0",
            "--default-output",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = settings.obj_payload
    # dataikuapi writes "FILTERS" (plural) into payload; CLI keeps user-facing --mode FILTER
    assert payload["mode"] == "FILTERS"
    filt = payload["filterSplits"][0]["filter"]
    # DSS evaluates the TOP-LEVEL `expression` field when uiData.mode == "CUSTOM".
    # Placing the GREL only inside uiData makes DSS match all rows (silent no-op).
    assert filt["expression"] == "spend>1000"
    assert filt["uiData"]["mode"] == "CUSTOM"
    assert filt["enabled"] is True
    assert payload["filterSplits"][0]["outputIndex"] == 0


def test_recipe_create_split_range_mode(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "bin",
            "-i",
            "rows",
            "--output-ds",
            "low",
            "--output-ds",
            "high",
            "--mode",
            "RANGE",
            "--column",
            "price",
            "--range-split",
            "..100=0",
            "--range-split",
            "100..=1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    splits = settings.obj_payload["rangeSplits"]
    assert splits[0] == {
        "outputIndex": 0,
        "include_min": True,
        "include_max": False,
        "max": "100",
    }
    assert splits[1] == {
        "outputIndex": 1,
        "include_min": True,
        "include_max": False,
        "min": "100",
    }


def test_recipe_create_split_requires_two_outputs(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "x",
            "-i",
            "rows",
            "--output-ds",
            "only",
            "--mode",
            "VALUES",
            "--column",
            "c",
            "--value-split",
            "v=0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "at least 2 output datasets" in result.output


def test_recipe_create_split_values_requires_column(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "x",
            "-i",
            "rows",
            "--output-ds",
            "a",
            "--output-ds",
            "b",
            "--mode",
            "VALUES",
            "--value-split",
            "v=0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "VALUES requires --column" in result.output


def test_recipe_create_split_invalid_mode(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "x",
            "-i",
            "rows",
            "--output-ds",
            "a",
            "--output-ds",
            "b",
            "--mode",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


# ── create-topn --bottom / --n mutual exclusivity ─────────────────────


def test_recipe_create_topn_bottom_and_n_mutually_exclusive(patch_client):
    """Passing both --n and --bottom is rejected (documented as exclusive)."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "worst",
            "-i",
            "sales",
            "--output-ds",
            "out",
            "--n",
            "5",
            "--bottom",
            "3",
            "--sort-col",
            "revenue",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_recipe_create_topn_bottom_alone_ok(patch_client):
    """--bottom without --n still works (writes lastRows/firstRows)."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "worst",
            "-i",
            "sales",
            "--output-ds",
            "out",
            "--bottom",
            "3",
            "--sort-col",
            "revenue",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["lastRows"] == 3
    assert settings.obj_payload["firstRows"] == 0


# ── --engine flag (top-level payload.engineType, separate from engineParams) ──


def test_recipe_create_group_engine_sql(patch_client):
    """--engine SQL writes payload.engineType=SQL for Snowflake/Postgres pushdown."""
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
            "sales",
            "--output-ds",
            "agg",
            "-k",
            "store",
            "--engine",
            "SQL",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload.get("engineType") == "SQL"


def test_recipe_create_pivot_engine_spark(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "p",
            "-i",
            "sales",
            "--output-ds",
            "wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--engine",
            "SPARK_SQL",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload.get("engineType") == "SPARK_SQL"


def test_recipe_create_split_engine(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-split",
            "s",
            "-i",
            "rows",
            "--output-ds",
            "a",
            "--output-ds",
            "b",
            "--mode",
            "RANDOM",
            "--random-share",
            "0:50",
            "--random-share",
            "1:50",
            "--engine",
            "SQL",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload.get("engineType") == "SQL"


def test_recipe_create_window_engine_invalid(patch_client):
    """Unknown --engine value is rejected at parse time by the click.Choice."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w",
            "-i",
            "data",
            "--output-ds",
            "ranked",
            "--engine",
            "DOOM",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_join_engine(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [
        {
            "table1": 0,
            "table2": 1,
            "conditionsMode": "AND",
            "type": "LEFT",
            "outerJoinOnTheLeft": True,
            "on": [],
        }
    ]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--engine",
            "SQL",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload.get("engineType") == "SQL"


# ── Join advanced match modes ────────────────────────────────────────


def test_recipe_create_join_case_insensitive_normalize_text(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "name",
            "--case-insensitive",
            "--normalize-text",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    cond = settings.raw_joins[0]["on"][0]
    assert cond["caseInsensitive"] is True
    assert cond["normalizeText"] is True


def test_recipe_create_join_inequality_keys(patch_client):
    """--join-key accepts inequality operators → typed GTE/LTE/GT/LT/NE
    conditions (the rolling-N range self-join pattern, flags-only)."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "INNER", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "self_roll",
            "-i",
            "seq_ds",
            "-i",
            "seq_ds",
            "--output-ds",
            "rolled",
            "-j",
            "INNER",
            "--join-key",
            "seq<=seq",
            "--join-key",
            "win_end>=seq",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    conds = settings.raw_joins[0]["on"]
    assert [c["type"] for c in conds] == ["LTE", "GTE"]
    assert conds[0]["column1"]["name"] == "seq"
    assert conds[1]["column1"]["name"] == "win_end"
    assert conds[1]["column2"]["name"] == "seq"


def test_recipe_create_join_equality_key_still_eq(patch_client):
    """'left=right' and bare 'col' specs still emit EQ conditions."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "order_id=id",
            "--join-key",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    conds = settings.raw_joins[0]["on"]
    assert [c["type"] for c in conds] == ["EQ", "EQ"]
    assert conds[0]["column1"]["name"] == "order_id"
    assert conds[0]["column2"]["name"] == "id"


def test_recipe_create_join_inequality_key_missing_side_errors(patch_client):
    """An operator with an empty side dies at parse time, before any create."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "seq>=",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "both sides" in result.output


def test_recipe_create_join_modifiers_with_inequality_only_keys_error(patch_client):
    """EQ-condition modifiers refuse when only inequality keys are given."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "seq>=start",
            "--case-insensitive",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "no EQ join key" in result.output


def test_recipe_create_join_max_distance_max_matches(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "name",
            "--max-distance",
            "2",
            "--max-matches",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    cond = settings.raw_joins[0]["on"][0]
    assert cond["maxDistance"] == 2
    assert cond["maxMatches"] == 5


def test_recipe_create_join_date_window(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--date-window",
            "-7:7:DAY",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    cond = settings.raw_joins[0]["on"][0]
    assert cond["windowFrom"] == -7
    assert cond["windowTo"] == 7
    assert cond["dateDiffUnit"] == "DAY"


def test_recipe_create_join_date_window_default_unit(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--date-window",
            "0:30",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    cond = settings.raw_joins[0]["on"][0]
    assert cond["windowFrom"] == 0
    assert cond["windowTo"] == 30
    assert cond["dateDiffUnit"] == "DAY"


def test_recipe_create_join_date_window_invalid_format(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--date-window",
            "abc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "FROM:TO" in result.output


def test_recipe_create_join_date_window_invalid_unit(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--date-window",
            "0:7:WIBBLE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "WIBBLE" in result.output


def test_recipe_create_join_date_window_without_join_key_errors(patch_client):
    """--date-window with no --join-key has no EQ condition to mutate, so it
    must error prescriptively instead of silently dropping the modifier."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "orders",
            "-i",
            "returns",
            "--output-ds",
            "m",
            "--date-window",
            "-7:7:DAY",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    # Rich line-wraps the message, so collapse whitespace before substring checks.
    flat = " ".join(_strip_ansi(result.output).split())
    assert "no EQ join key was set" in flat
    assert "--join-key" in flat
    # The misleading "Match mode" line must NOT be printed.
    assert "Match mode" not in flat


def test_recipe_create_join_case_insensitive_without_join_key_errors(patch_client):
    """--case-insensitive without --join-key errors (no EQ condition to apply to)."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--case-insensitive",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    flat = " ".join(_strip_ansi(result.output).split())
    assert "no EQ join key was set" in flat


def test_recipe_create_join_lowercase_join_type(patch_client):
    """case_sensitive=False: lowercase --join-type left is accepted."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-type",
            "left",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    # Resolved to the canonical uppercase member value.
    assert "Created LEFT join recipe" in result.output
    assert settings.raw_joins[0]["type"] == "LEFT"


def test_recipe_create_join_outer_join_on_right(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [
        {
            "table1": 0,
            "table2": 1,
            "type": "LEFT",
            "outerJoinOnTheLeft": True,
            "on": [],
        }
    ]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--outer-join-on-right",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.raw_joins[0]["outerJoinOnTheLeft"] is False


def test_recipe_create_join_right_limit_keep_largest(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--right-limit-max-matches",
            "1",
            "--right-limit-decision-column",
            "record_date",
            "--right-limit-keep",
            "KEEP_LARGEST",
            "--right-limit-strict",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    rl = settings.raw_joins[0]["rightLimit"]
    assert rl["enabled"] is True
    assert rl["maxMatches"] == 1
    assert rl["type"] == "KEEP_LARGEST"
    assert rl["decisionColumn"] == {"name": "record_date", "table": 1}
    assert rl["strict"] is True


def test_recipe_create_join_right_limit_largest_requires_decision_column(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--right-limit-keep",
            "KEEP_LARGEST",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--right-limit-decision-column" in result.output


def test_recipe_create_join_right_limit_keep_first_no_decision_column(patch_client):
    """KEEP_FIRST does NOT require a decision column."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    settings.raw_joins = [{"table1": 0, "table2": 1, "type": "LEFT", "on": []}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--right-limit-keep",
            "KEEP_FIRST",
            "--right-limit-max-matches",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    rl = settings.raw_joins[0]["rightLimit"]
    assert rl["type"] == "KEEP_FIRST"
    assert rl["maxMatches"] == 1
    assert "decisionColumn" not in rl


# ── New recipe verbs (eda_univariate, sql_script, generate_features, llm-classify)
