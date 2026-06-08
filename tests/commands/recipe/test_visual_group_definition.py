"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

import json
from tests.commands.recipe.helpers import app, runner
from tests.commands.recipe.helpers import setup_prepare_mock as _setup_prepare_mock


# ── set-definition --payload flag ─────────────────────────────────────


def test_recipe_set_definition_payload(patch_client):
    """--payload writes to obj_payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    new_payload = json.dumps({"topN": 5, "orders": [{"column": "price", "desc": True}]})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            new_payload,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated payload" in result.output
    settings.save.assert_called()


def test_recipe_set_definition_no_flag(patch_client):
    """Missing both --definition and --payload gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Provide either" in result.output


def test_recipe_set_definition_both_flags(patch_client):
    """Both --definition and --payload is an error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            '{"type": "python"}',
            "--payload",
            '{"topN": 5}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Cannot use both" in result.output


def test_recipe_set_definition_deep_merge(patch_client):
    """--deep-merge recursively merges nested payload objects."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {
        "topN": 5,
        "postFilter": {"enabled": False, "distinct": True},
        "keys": ["customer_id"],
    }

    # Deep merge should update postFilter.enabled without losing postFilter.distinct
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            '{"postFilter": {"enabled": true}}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "deep-merged" in result.output
    payload = settings.obj_payload
    assert payload["postFilter"]["enabled"] is True
    assert payload["postFilter"]["distinct"] is True  # preserved
    assert payload["topN"] == 5  # preserved
    assert payload["keys"] == ["customer_id"]  # preserved
    settings.save.assert_called()


def test_recipe_set_definition_deep_merge_replaces_non_dict(patch_client):
    """--deep-merge replaces non-dict values in patch."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"topN": 5, "keys": ["old_key"]}

    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--payload",
            '{"topN": 10, "keys": ["new_key"]}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    payload = settings.obj_payload
    assert payload["topN"] == 10
    assert payload["keys"] == ["new_key"]


def test_recipe_set_definition_deep_merge_without_payload(patch_client):
    """--deep-merge without --payload is an error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            '{"type": "python"}',
            "--deep-merge",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--deep-merge can only be used with --payload" in result.output


# ── Prepare step: add-fold ─────────────────────────────────────────────


def test_recipe_add_fold_by_name(patch_client):
    """Fold by explicit column names."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--columns",
            "jan,feb,mar",
            "--key-column",
            "month",
            "--value-column",
            "sales",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "MultiColumnFold" in result.output
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "MultiColumnFold"
    assert step["params"]["columns"] == ["jan", "feb", "mar"]
    assert step["params"]["foldNameColumn"] == "month"
    assert step["params"]["foldValueColumn"] == "sales"
    assert step["params"]["foldRemoveFoldedColumns"] is True


def test_recipe_add_fold_by_pattern(patch_client):
    """Fold by regex pattern."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--pattern",
            ".*-25",
            "--key-column",
            "month",
            "--value-column",
            "value",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "MultiColumnByPrefixFold" in result.output
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "MultiColumnByPrefixFold"
    assert step["params"]["columnNamePattern"] == ".*-25"
    assert step["params"]["columnNameColumn"] == "month"
    assert step["params"]["columnContentColumn"] == "value"
    assert step["params"]["foldRemoveFoldedColumns"] is True


def test_recipe_add_fold_requires_columns_or_pattern(patch_client):
    """Error when neither --columns nor --pattern given."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--key-column",
            "month",
            "--value-column",
            "sales",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Specify --columns or --pattern" in result.output


def test_recipe_add_fold_both_columns_and_pattern_error(patch_client):
    """Error when both --columns and --pattern given."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-fold",
            "prep1",
            "--columns",
            "jan,feb",
            "--pattern",
            ".*-25",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not both" in result.output


# ── Visual recipe: create-group with --agg ────────────────────────────


def test_recipe_create_group(patch_client):
    """Basic group recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("grouping", "my_group")
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")


def test_recipe_create_group_no_global_count(patch_client):
    """--no-global-count disables the DSS default per-group count column."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "tight_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum",
            "--no-global-count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.set_global_count_enabled.assert_called_once_with(False)
    settings.save.assert_called()


def test_recipe_create_group_with_agg(patch_client):
    """--agg configures column aggregations after build."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum,avg",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.set_column_aggregations.assert_called_once_with(
        "amount",
        sum=True,
        avg=True,
        min=False,
        max=False,
        count=False,
        count_distinct=False,
        concat=False,
        stddev=False,
    )
    settings.save.assert_called()


def test_recipe_create_group_multiple_agg(patch_client):
    """Multiple --agg flags configure different columns."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum,avg",
            "--agg",
            "order_id:count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.set_column_aggregations.call_count == 2


def test_recipe_create_group_prunes_empty_values(patch_client):
    """The dataikuapi grouping builder seeds payload.values[] with one
    entry per input column (all aggregation flags False). The CLI must
    prune entries with no aggregation flags set so the recipe's
    Aggregate tab in the UI shows only columns that are actually
    aggregated — not 14 dead rows on a recipe with one --agg.

    Verified on Challenge_032 (sum_dist Group recipe): a single
    `--agg dist_miles:sum` left 14 empty values[] entries cluttering
    the UI; pruning leaves exactly the one aggregated column."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    flags_off = {
        "sum": False,
        "avg": False,
        "min": False,
        "max": False,
        "count": False,
        "countDistinct": False,
        "concat": False,
        "concatDistinct": False,
        "stddev": False,
        "first": False,
        "last": False,
        "firstLastNotNull": False,
        "sum2": False,
        "median": False,
    }
    # Mimic the dataikuapi builder seed: an entry per input column,
    # all flags off. Then the CLI's `cs[flag] = True` writes the
    # truthy flag into the matching entry — simulate that on `amount`.
    amount_entry = {"column": "amount", **flags_off, "sum": True}
    settings.obj_payload = {
        "keys": [{"column": "region"}],
        "values": [
            {"column": "region", **flags_off},
            {"column": "store_id", **flags_off},
            amount_entry,
            {"column": "discount", **flags_off},
        ],
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "g",
            "-i",
            "sales",
            "--output-ds",
            "out",
            "-k",
            "region",
            "--agg",
            "amount:sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    final_values = settings.obj_payload["values"]
    assert len(final_values) == 1, (
        f"Expected only the aggregated column to remain, got {len(final_values)}: "
        f"{[v['column'] for v in final_values]}"
    )
    assert final_values[0]["column"] == "amount"
    assert final_values[0]["sum"] is True


def test_recipe_create_group_pre_filter_uses_canonical_shape(patch_client):
    """`--pre-filter` GREL must end up at the top-level ``expression`` field with
    ``uiData.mode == "CUSTOM"``. Putting the expression only inside ``uiData``
    makes DSS evaluate the empty ``conditions[]`` array and silently match all
    rows (filter becomes a no-op). Verified empirically on AYX011 — the buggy
    shape returned all groups including the empty-key bucket; the canonical
    shape correctly excludes it."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"keys": [{"column": "region"}]}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "filtered_group",
            "-i",
            "sales",
            "--output-ds",
            "out",
            "-k",
            "region",
            "--pre-filter",
            'region != ""',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    pre = settings.obj_payload["preFilter"]
    assert pre["enabled"] is True
    assert pre["expression"] == 'region != ""'
    assert pre["uiData"]["mode"] == "CUSTOM"
    # conditions[] must be present (even empty) so DSS doesn't choke on the
    # visual-mode path.
    assert pre["uiData"]["conditions"] == []


def test_recipe_create_group_no_key_clears_default_keys(patch_client):
    """Without -k, the dataikuapi builder leaves a `[{}]` placeholder in
    payload.keys that crashes DSS at run time. The CLI must reset keys to []
    to express the global-aggregate use case (one output row)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"keys": [{}]}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "global_agg",
            "-i",
            "sales",
            "--output-ds",
            "totals",
            "--agg",
            "amount:sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["keys"] == []
    settings.save.assert_called()


def test_recipe_create_group_invalid_agg_format(patch_client):
    """--agg without colon gives clear error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "--agg",
            "amount_sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --agg format" in result.output


def test_recipe_create_group_invalid_agg_function(patch_client):
    """--agg with unknown function gives clear error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "--agg",
            "amount:median",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown aggregation" in result.output


def test_recipe_create_group_no_agg_backward_compat(patch_client):
    """Without --agg, group recipe uses default COUNT behavior."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output


def test_recipe_create_group_multi_key(patch_client):
    """Multiple -k flags add all grouping keys."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "-k",
            "category",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")
    settings.add_grouping_key.assert_called_once_with("category")
    settings.save.assert_called()


def test_recipe_create_group_three_keys(patch_client):
    """Three -k flags: first to builder, remaining via settings."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "-k",
            "category",
            "-k",
            "year",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")
    assert settings.add_grouping_key.call_count == 2
    settings.add_grouping_key.assert_any_call("category")
    settings.add_grouping_key.assert_any_call("year")


def test_recipe_create_group_multi_key_with_agg(patch_client):
    """Multi-key plus aggregation in single settings call."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "-k",
            "category",
            "--agg",
            "amount:sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.add_grouping_key.assert_called_once_with("category")
    settings.set_column_aggregations.assert_called_once()
    settings.save.assert_called()


# ── Auto apply-schema ─────────────────────────────────────────────────


def test_visual_recipe_auto_applies_schema(patch_client):
    """Visual recipe creation auto-applies schema updates."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    updates.apply.assert_called_once()


def test_auto_apply_schema_failure_warns_not_crashes(patch_client):
    """Schema auto-apply failure emits warning, doesn't crash."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    recipe_mock.compute_schema_updates.side_effect = Exception("schema error")

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "deduped",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created distinct recipe" in result.output


def test_recipe_create_distinct_defaults_to_all_input_columns(patch_client):
    """Without --on, create-distinct populates keys with every input column.

    Prevents the silent bug where DSS defaults to keys=[first_col] +
    selectAllColumns=false, which projects the output to a single column.
    """
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [
            {"name": "customer_id", "type": "string"},
            {"name": "order_date", "type": "date"},
            {"name": "amount", "type": "double"},
        ]
    }
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "dedup",
            "-i",
            "orders",
            "--output-ds",
            "unique_orders",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["keys"] == [
        {"column": "customer_id"},
        {"column": "order_date"},
        {"column": "amount"},
    ]
    assert settings.obj_payload["selectAllColumns"] is True
    settings.save.assert_called()


def test_recipe_create_distinct_with_explicit_on_flag(patch_client):
    """--on col1 --on col2 sets only the specified keys (skips schema lookup)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "dedup",
            "-i",
            "orders",
            "--output-ds",
            "unique_per_customer",
            "--on",
            "customer_id",
            "--on",
            "order_date",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["keys"] == [
        {"column": "customer_id"},
        {"column": "order_date"},
    ]
    # A subset via --on must NOT select all columns; otherwise DSS dedups on the
    # full row and the keys are ignored.
    assert settings.obj_payload["selectAllColumns"] is False


# ── Dynamic connection discovery ──────────────────────────────────────


def test_ensure_output_finds_managed_connection(patch_client):
    """Uses first connection with allowManagedDatasets=True."""
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_definition.side_effect = Exception(
        "NotFoundException"
    )

    patch_client.list_connections.return_value = {
        "my_sql_conn": {"type": "PostgreSQL", "allowManagedDatasets": False},
        "s3_managed": {"type": "S3", "allowManagedDatasets": True},
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "new_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("s3_managed")


def test_ensure_output_falls_back_on_permission_error(patch_client):
    """Falls back to filesystem_managed when list_connections fails (403)."""
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_definition.side_effect = Exception(
        "NotFoundException"
    )
    patch_client.list_connections.side_effect = Exception("403 Forbidden")

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "new_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_managed")


# ---------------------------------------------------------------------------
