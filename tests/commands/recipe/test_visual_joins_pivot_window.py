"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

from tests.commands.recipe.helpers import app, runner
from tests.helpers import strip_ansi as _strip_ansi

# ── Visual recipe: create-join ────────────────────────────────────────


def test_recipe_create_join(patch_client):
    """Basic join recipe creation with 2 inputs."""
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
            "joined_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created LEFT join recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("join", "my_join")
    builder = proj.new_recipe.return_value
    assert builder.with_input.call_count == 2
    builder.with_existing_output.assert_called_once_with("joined_data")
    builder.build.assert_called_once()


def test_recipe_create_join_requires_two_inputs(patch_client):
    """Join needs >= 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
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


def test_recipe_create_join_with_join_key(patch_client):
    """--join-key adds EQ condition to first join."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

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
            "--join-key",
            "customer_id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(join_dict["on"]) == 1
    assert join_dict["on"][0]["column1"]["name"] == "customer_id"
    assert join_dict["on"][0]["column2"]["name"] == "customer_id"
    assert join_dict["on"][0]["type"] == "EQ"
    settings.save.assert_called()


def test_recipe_create_join_with_different_column_names(patch_client):
    """--join-key col1=col2 maps different column names."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

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
            "--join-key",
            "order_cust_id=id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert join_dict["on"][0]["column1"]["name"] == "order_cust_id"
    assert join_dict["on"][0]["column2"]["name"] == "id"


def test_recipe_create_join_multiple_keys(patch_client):
    """Multiple --join-key flags add multiple conditions."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

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
            "--join-key",
            "customer_id",
            "--join-key",
            "region=region_code",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(join_dict["on"]) == 2
    assert join_dict["on"][0]["column1"]["name"] == "customer_id"
    assert join_dict["on"][1]["column1"]["name"] == "region"
    assert join_dict["on"][1]["column2"]["name"] == "region_code"


def test_recipe_create_join_no_key_backward_compat(patch_client):
    """Without --join-key, join recipe is created with default behavior."""
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
    assert "Created LEFT join recipe" in result.output
    # get_settings should NOT be called for join key configuration
    proj = patch_client.get_project("PROJ1")
    # builder.build is called, but no post-build settings modification
    proj.new_recipe.return_value.build.assert_called_once()


# ── Visual recipe: create-join --join-type and indexed keys ────────────


def _setup_join_mock(patch_client, num_joins=1):
    """Configure mock for join recipe tests with real dicts for raw_joins."""
    proj = patch_client.get_project("PROJ1")
    recipe_obj = proj.get_recipe.return_value
    settings = recipe_obj.get_settings.return_value
    mock_joins = [
        {"type": "LEFT", "on": [], "table1": 0, "table2": i + 1}
        for i in range(num_joins)
    ]
    type(settings).raw_joins = property(lambda self: mock_joins)
    return proj, settings, mock_joins


def test_recipe_create_join_with_join_type_inner(patch_client):
    """--join-type INNER sets type on all join pairs."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client)
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
            "--join-type",
            "INNER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created INNER join recipe" in result.output
    assert mock_joins[0]["type"] == "INNER"


def test_recipe_create_join_cross_no_keys(patch_client):
    """CROSS join skips key configuration."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_cross",
            "-i",
            "records",
            "-i",
            "months",
            "--output-ds",
            "expanded",
            "--join-type",
            "CROSS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created CROSS join recipe" in result.output
    assert mock_joins[0]["type"] == "CROSS"


def test_recipe_create_join_cross_ignores_keys(patch_client):
    """CROSS join warns when --join-key is provided."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_cross",
            "-i",
            "records",
            "-i",
            "months",
            "--output-ds",
            "expanded",
            "--join-type",
            "CROSS",
            "--join-key",
            "id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "CROSS join ignores" in result.output


def test_recipe_create_join_invalid_type_error(patch_client):
    """Invalid join type raises error (click.Choice rejects at parse time)."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "out",
            "--join-type",
            "FULL_OUTER",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_join_multi_input_indexed_keys(patch_client):
    """Indexed --join-key targets specific join pairs."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client, num_joins=2)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "multi_join",
            "-i",
            "main",
            "-i",
            "lookup_a",
            "-i",
            "lookup_b",
            "--output-ds",
            "enriched",
            "--join-key",
            "entity=company",
            "--join-key",
            "1:region=region_name",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Join 0 should have entity=company condition
    assert len(mock_joins[0]["on"]) >= 1
    assert mock_joins[0]["on"][0]["column1"]["name"] == "entity"
    # Join 1 should have region=region_name condition
    assert len(mock_joins[1]["on"]) >= 1
    assert mock_joins[1]["on"][0]["column1"]["name"] == "region"


def test_recipe_create_join_five_inputs_creates_four_join_pairs(patch_client):
    """With 5 inputs, the CLI extends raw_joins to 4 pairs (DSS's builder
    pre-creates only 1 pair, so we must fill the rest)."""
    # Simulate DSS's builder pre-creating a single default join pair for 2+ inputs.
    _proj, _settings, mock_joins = _setup_join_mock(patch_client, num_joins=1)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "five_way",
            "-i",
            "main",
            "-i",
            "dim_a",
            "-i",
            "dim_b",
            "-i",
            "dim_c",
            "-i",
            "dim_d",
            "--output-ds",
            "fully_enriched",
            "--join-key",
            "k0=a_key",
            "--join-key",
            "1:k1=b_key",
            "--join-key",
            "2:k2=c_key",
            "--join-key",
            "3:k3=d_key",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    # 5 inputs → 4 join pairs
    assert len(mock_joins) == 4
    # Each pair fans out from table 0 to tables 1..4
    for i, j in enumerate(mock_joins):
        assert j["table1"] == 0
        assert j["table2"] == i + 1
    # All four keys should be wired (not just the first)
    assert mock_joins[0]["on"][0]["column1"]["name"] == "k0"
    assert mock_joins[1]["on"][0]["column1"]["name"] == "k1"
    assert mock_joins[2]["on"][0]["column1"]["name"] == "k2"
    assert mock_joins[3]["on"][0]["column1"]["name"] == "k3"


def test_recipe_create_join_multi_input_unprefixed_key_warns_cartesian(patch_client):
    """3+ inputs with an unprefixed key leaves extra pairs conditionless. The
    CLI must warn LOUDLY (naming the inputs) and tell the agent how to fix it,
    while still creating the recipe."""
    _proj, _settings, mock_joins = _setup_join_mock(patch_client, num_joins=2)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "multi_join",
            "-i",
            "main",
            "-i",
            "lookup_a",
            "-i",
            "lookup_b",
            "--output-ds",
            "enriched",
            "--join-type",
            "INNER",
            "--join-key",
            "id",  # unprefixed → only join 0
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    # Join 0 got the condition; join 1 (lookup_b) is conditionless.
    assert len(mock_joins[0]["on"]) == 1
    assert mock_joins[1]["on"] == []
    # Warning must name the input that got no condition and how to fix it.
    flat = " ".join(_strip_ansi(result.output).split())
    assert "lookup_b" in flat
    assert "CARTESIAN" in flat or "cross" in flat
    assert "2:" in flat


def test_recipe_create_join_multi_input_all_keyed_no_warning(patch_client):
    """When every extra pair is index-prefixed, no cartesian warning fires."""
    _proj, _settings, _mock_joins = _setup_join_mock(patch_client, num_joins=2)
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "multi_join",
            "-i",
            "main",
            "-i",
            "lookup_a",
            "-i",
            "lookup_b",
            "--output-ds",
            "enriched",
            "--join-key",
            "entity=company",
            "--join-key",
            "1:region=region_name",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "CARTESIAN" not in _strip_ansi(result.output)


def test_recipe_create_join_pipeline_flags(patch_client):
    """--pre-filter / --computed-col / --post-filter wire the 4-stage pipeline
    into the join payload (shapes verified against live DSS 2026-06-10)."""
    _proj, settings, _mock_joins = _setup_join_mock(patch_client)
    settings.obj_payload = {"virtualInputs": [{"index": 0}, {"index": 1}]}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "rates",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--pre-filter",
            '0:status == "A"',
            "--computed-col",
            "weighted=amount * rate:double",
            "--computed-col",
            "1:rate_pct=rate * 100:double",
            "--post-filter",
            "amount > 15",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = settings.obj_payload
    # Per-input preFilter: canonical CUSTOM shape (top-level expression).
    pf = payload["virtualInputs"][0]["preFilter"]
    assert pf["enabled"] is True
    assert pf["expression"] == 'status == "A"'
    assert pf["uiData"]["mode"] == "CUSTOM"
    # Pre-join computed column on input 1.
    assert payload["virtualInputs"][1]["computedColumns"] == [
        {"mode": "GREL", "name": "rate_pct", "expr": "rate * 100", "type": "double"}
    ]
    # Post-join computed column (cross-input) at payload level.
    assert payload["computedColumns"] == [
        {"mode": "GREL", "name": "weighted", "expr": "amount * rate", "type": "double"}
    ]
    # postFilter on the joined output.
    assert payload["postFilter"]["expression"] == "amount > 15"
    settings.save.assert_called()


def test_recipe_create_join_pre_filter_requires_index(patch_client):
    """--pre-filter without the 'INDEX:' prefix is refused with the format."""
    _proj, settings, _mock_joins = _setup_join_mock(patch_client)
    settings.obj_payload = {"virtualInputs": [{"index": 0}, {"index": 1}]}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "rates",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--pre-filter",
            'status == "A"',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    flat = " ".join(_strip_ansi(result.output).split())
    assert "INDEX:GREL_EXPR" in flat


def test_recipe_create_join_pre_filter_index_out_of_range(patch_client):
    """--pre-filter with an out-of-range index names the valid inputs."""
    _proj, settings, _mock_joins = _setup_join_mock(patch_client)
    settings.obj_payload = {"virtualInputs": [{"index": 0}, {"index": 1}]}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "rates",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--pre-filter",
            "5:amount > 0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    flat = " ".join(_strip_ansi(result.output).split())
    assert "out of range" in flat
    assert "0=orders" in flat


def test_recipe_create_join_computed_col_index_out_of_range(patch_client):
    """An indexed --computed-col beyond the input list is refused."""
    _proj, settings, _mock_joins = _setup_join_mock(patch_client)
    settings.obj_payload = {"virtualInputs": [{"index": 0}, {"index": 1}]}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "rates",
            "--output-ds",
            "joined",
            "--join-key",
            "id",
            "--computed-col",
            "7:flag=amount > 0:boolean",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "out of range" in " ".join(_strip_ansi(result.output).split())


def test_join_modifier_guard_fires_before_output_creation(patch_client):
    """A per-condition match modifier (--date-window) with NO --join-key is
    refused PRE-FLIGHT — before the recipe is built or the output dataset is
    created. A guard failure must not leave an orphan auto-created --output-ds
    in the flow."""
    proj = patch_client.get_project("PROJ1")
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
            "--date-window",
            "-7:7:DAY",
            # NO --join-key
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    flat = " ".join(_strip_ansi(result.output).split())
    # Prescriptive message: tells the agent it needs a join key.
    assert "no EQ join key was set" in flat
    assert "--join-key" in flat
    # Pre-flight: neither the recipe nor the output dataset was created.
    proj.new_recipe.assert_not_called()
    proj.new_managed_dataset.assert_not_called()


# ── Visual recipe: create-pivot ────────────────────────────────────────


def test_recipe_create_pivot_basic(patch_client):
    """Basic pivot recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "long_data",
            "--output-ds",
            "wide_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created pivot recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("pivot", "my_pivot")


def test_recipe_create_pivot_with_keys(patch_client):
    """Pivot with row/column/value configuration."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created pivot recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    recipe_obj = proj.get_recipe("my_pivot")
    settings = recipe_obj.get_settings()
    settings.save.assert_called()


# ── Visual recipe: create-sampling ─────────────────────────────────────


def test_recipe_create_sampling_basic(patch_client):
    """Basic sampling recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sampling",
            "sample_1k",
            "-i",
            "big_data",
            "--output-ds",
            "sample",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created sampling recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("sampling", "sample_1k")


def test_recipe_create_sampling_with_method_and_size(patch_client):
    """Sampling with method and size configuration."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sampling",
            "sample_head",
            "-i",
            "data",
            "--output-ds",
            "head_sample",
            "--method",
            "HEAD_SEQUENTIAL",
            "--size",
            "500",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "HEAD_SEQUENTIAL" in result.output
    proj = patch_client.get_project("PROJ1")
    recipe_obj = proj.get_recipe("sample_head")
    settings = recipe_obj.get_settings()
    settings.save.assert_called()


def test_recipe_create_sampling_full_with_filter(patch_client):
    """--method FULL + --filter-condition writes uiData.expression onto the payload."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    raw_def = {"params": {}}
    settings.get_recipe_raw_definition.return_value = raw_def
    settings.obj_payload = {}
    settings.payload = "{}"

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sampling",
            "fil",
            "-i",
            "rows",
            "--output-ds",
            "active",
            "--method",
            "FULL",
            "--filter-condition",
            'status=="active"',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw_def["params"]["selection"]["samplingMethod"] == "FULL"
    assert settings.obj_payload["uiData"]["expression"] == 'status=="active"'


def test_recipe_create_sampling_invalid_method(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sampling",
            "x",
            "-i",
            "a",
            "--output-ds",
            "b",
            "--method",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


# ── Visual recipe: create-prepare shortcut ──────────────────────────


def test_recipe_create_prepare_basic(patch_client):
    """create-prepare auto-creates output dataset and builds a shaker recipe."""
    proj = patch_client.get_project("PROJ1")
    # Force the auto-create path: output dataset doesn't exist yet.
    proj.get_dataset.return_value.get_definition.side_effect = Exception("Not found")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-prepare",
            "clean_step",
            "-i",
            "raw",
            "--output-ds",
            "cleaned",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created prepare recipe" in result.output
    # Internal type must be `shaker`, not `prepare` — `dataikuapi` rejects `prepare`.
    proj.new_recipe.assert_called_with("shaker", "clean_step")


# ── Visual recipe: create-sort with --sort-col ────────────────────────


def test_recipe_create_sort_with_sort_col(patch_client):
    """--sort-col configures sort column."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sort",
            "my_sort",
            "-i",
            "data",
            "--output-ds",
            "sorted",
            "--sort-col",
            "price",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "sort" in result.output.lower() or "Created" in result.output


def test_recipe_create_sort_desc(patch_client):
    """--sort-col col:desc sorts descending."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sort",
            "my_sort",
            "-i",
            "data",
            "--output-ds",
            "sorted",
            "--sort-col",
            "price:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# ── Visual recipe: create-topn with configuration ─────────────────────


def test_recipe_create_topn_basic(patch_client):
    """Basic topn creation with default N=10."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "my_topn",
            "-i",
            "data",
            "--output-ds",
            "top_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "top 10" in result.output
    assert settings.obj_payload["topN"] == 10
    settings.save.assert_called()


def test_recipe_create_topn_with_rank_by(patch_client):
    """--rank-by sets orders in payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "top5",
            "-i",
            "sales",
            "--output-ds",
            "top5_sales",
            "--n",
            "5",
            "--rank-by",
            "revenue:desc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "top 5" in result.output
    assert settings.obj_payload["topN"] == 5
    assert settings.obj_payload["orders"] == [{"column": "revenue", "desc": True}]


def test_recipe_create_topn_with_partition(patch_client):
    """--partition-key sets partitioningColumns for top N per group."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "top3_per_cat",
            "-i",
            "products",
            "--output-ds",
            "top_products",
            "--n",
            "3",
            "--rank-by",
            "price:desc",
            "--partition-key",
            "category",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["topN"] == 3
    assert settings.obj_payload["firstRows"] == 3
    assert settings.obj_payload["orders"] == [{"column": "price", "desc": True}]
    assert settings.obj_payload["keys"] == ["category"]


def test_recipe_create_topn_with_flags(patch_client):
    """--sort-col and --n configure topn recipe."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-topn",
            "my_topn",
            "-i",
            "data",
            "--output-ds",
            "top10",
            "--sort-col",
            "revenue:desc",
            "--n",
            "10",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.obj_payload["topN"] == 10
    assert settings.obj_payload["orders"] == [{"column": "revenue", "desc": True}]


# ── Visual recipe: create-pivot with --agg-type ──────────────────────


def test_recipe_create_pivot_with_agg_type(patch_client):
    """--agg-type sets valueFunctions in payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    pivots = settings.obj_payload["pivots"]
    assert pivots[0]["keyColumns"] == ["month"]
    # DSS pivot valueColumns are GroupingValue objects — aggregation is a
    # BOOLEAN flag (`sum`, `avg`, ...), NOT a `function` string. Writing
    # `function: "SUM"` is silently accepted but produces no sum columns.
    vc = pivots[0]["valueColumns"][0]
    assert vc["column"] == "revenue"
    assert vc["type"] == "double"
    assert vc["sum"] is True
    assert vc["avg"] is False
    assert vc["count"] is False
    # UI-normalized modality defaults — without these DSS crashes with
    # "Unexpected value limit on modality collection" at runtime
    assert pivots[0]["valueLimit"] == "TOP_N"
    assert pivots[0]["topnLimit"] == 20
    assert settings.obj_payload["explicitIdentifiers"] == ["product"]


def test_recipe_create_pivot_custom_value_limit(patch_client):
    """--value-limit NO_LIMIT and --topn-limit override the UI defaults."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--value-limit",
            "NO_LIMIT",
            "--topn-limit",
            "50",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    pivots = settings.obj_payload["pivots"]
    assert pivots[0]["valueLimit"] == "NO_LIMIT"
    assert pivots[0]["topnLimit"] == 50


def test_recipe_create_pivot_min_occ_limit(patch_client):
    """--value-limit AT_LEAST_N_OCC + --min-occ-limit configures the occurrence filter."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--value-limit",
            "AT_LEAST_N_OCC",
            "--min-occ-limit",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    pivots = settings.obj_payload["pivots"]
    assert pivots[0]["valueLimit"] == "AT_LEAST_N_OCC"
    assert pivots[0]["minOccLimit"] == 5


def test_recipe_create_pivot_invalid_value_limit(patch_client):
    """--value-limit with unknown value gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--value-limit",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_pivot_explicit_values(patch_client):
    """--value-limit EXPLICIT + --explicit-values whitelists modalities and stores them as nested arrays."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--value-limit",
            "EXPLICIT",
            "--explicit-values",
            "2024",
            "--explicit-values",
            "2025",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    pivots = settings.obj_payload["pivots"]
    assert pivots[0]["valueLimit"] == "EXPLICIT"
    # DSS stores explicitValues as an array of single-element arrays
    assert pivots[0]["explicitValues"] == [["2024"], ["2025"]]


def test_recipe_create_pivot_explicit_requires_values(patch_client):
    """--value-limit EXPLICIT without --explicit-values must error before write."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--value-limit",
            "EXPLICIT",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "EXPLICIT requires" in result.output


def test_recipe_create_pivot_explicit_values_without_explicit_mode(patch_client):
    """--explicit-values without --value-limit EXPLICIT must error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--explicit-values",
            "2024",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--explicit-values requires --value-limit EXPLICIT" in result.output


def test_recipe_create_pivot_no_global_count(patch_client):
    """--no-global-count should flip pivots[0].globalCount to False."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    # Start the mocked payload as a dict so the CLI's .setdefault() works
    settings.obj_payload = {}

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--row-key",
            "product",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--no-global-count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["pivots"][0]["globalCount"] is False


def test_recipe_create_pivot_invalid_agg_type(patch_client):
    """--agg-type with unknown type gives error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "my_pivot",
            "-i",
            "sales",
            "--output-ds",
            "sales_wide",
            "--agg-type",
            "MEDIAN",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_pivot_other_column_last(patch_client):
    """--other-column writes payload.otherColumns[]."""
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
            "sensors",
            "--output-ds",
            "out",
            "--row-key",
            "sensor_id",
            "--column-key",
            "metric",
            "--value-column",
            "value",
            "--agg-type",
            "AVG",
            "--other-column",
            "equipment_id:LAST:timestamp",
            "--other-column",
            "model:LAST:timestamp",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    others = settings.obj_payload["otherColumns"]
    assert len(others) == 2
    assert others[0]["column"] == "equipment_id"
    assert others[0]["last"] is True
    assert others[0]["orderColumn"] == "timestamp"


def test_recipe_create_pivot_other_column_last_requires_order(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-pivot",
            "p",
            "-i",
            "sensors",
            "--output-ds",
            "out",
            "--column-key",
            "metric",
            "--value-column",
            "value",
            "--other-column",
            "equipment_id:LAST",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "ORDER_COL" in result.output


def test_recipe_create_pivot_modality_slugification_and_no_sort(patch_client):
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
            "out",
            "--column-key",
            "month",
            "--value-column",
            "revenue",
            "--agg-type",
            "SUM",
            "--modality-slugification",
            "SOFT_SLUGIFY",
            "--no-sort-modalities",
            "--identifier-mode",
            "AUTO",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.obj_payload["modalitySlugification"] == "SOFT_SLUGIFY"
    assert settings.obj_payload["sortModalities"] is False
    assert settings.obj_payload["identifierColumnsSelection"] == "AUTO"


# ── Window recipe: --compute flag ─────────────────────────────────────


def test_recipe_create_window_with_compute_rank(patch_client):
    """--compute rowNumber::rn sets top-level boolean in payload AND warns that
    the custom output name won't be honored (DSS has no payload field for it)."""
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
            "date",
            "--compute",
            "rowNumber::rn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # rowNumber is a top-level boolean in DSS Window payload
    assert settings.obj_payload["rowNumber"] is True
    # User asked for `rn` but DSS will name it `rownumber` — warn loudly
    assert "does not support custom output column names" in result.output
    assert "→ column 'rownumber'" in result.output


def test_recipe_create_window_no_warning_when_name_matches_dss(patch_client):
    """When the user's custom name matches what DSS will produce, no warning."""
    # patch_client fixture seeds the recipe mock; we only need to invoke the CLI.
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-window",
            "w2",
            "-i",
            "data",
            "--output-ds",
            "out",
            "--partition-key",
            "cat",
            "--order-key",
            "id",
            # Explicit name that matches DSS's generated name
            "--compute",
            "rowNumber::rownumber",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "does not support custom output column names" not in result.output


def test_recipe_create_window_with_compute_lag(patch_client):
    """--compute lag:col:output enables lag on the column in values[]."""
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
            "date",
            "--compute",
            "lag:price:price_lag1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # lag is a per-column boolean in values[] array
    values = settings.obj_payload["values"]
    price_entry = next(v for v in values if v["column"] == "price")
    assert price_entry["lag"] is True


def test_recipe_create_window_multiple_computes(patch_client):
    """Multiple --compute flags: top-level + per-column."""
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
            "ts",
            "--compute",
            "rowNumber::rn",
            "--compute",
            "sum:amount:cumulative_amount",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # rowNumber as top-level boolean
    assert settings.obj_payload["rowNumber"] is True
    # sum as per-column flag in values[]
    values = settings.obj_payload["values"]
    amount_entry = next(v for v in values if v["column"] == "amount")
    assert amount_entry["sum"] is True


def test_recipe_create_window_invalid_compute_type(patch_client):
    """--compute with unknown type gives error."""
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
            "--compute",
            "median:price:price_med",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown window computation type" in result.output


def test_recipe_create_window_compute_missing_column(patch_client):
    """--compute sum without source column gives error."""
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
            "--compute",
            "sum::cumsum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "requires a source column" in result.output


def test_recipe_create_window_lag_diff(patch_client):
    """--compute lagDiff enables lagDiff on the column in values[]."""
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
            "stock",
            "--order-key",
            "date",
            "--compute",
            "lagDiff:price:price_lagDiff",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    values = settings.obj_payload["values"]
    price_entry = next(v for v in values if v["column"] == "price")
    assert price_entry["lagDiff"] is True


def test_recipe_create_window_lag_date_unit(patch_client):
    """--lag-date-unit MONTH writes dateDiffUnit on entries with lag flagged."""
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
            "data",
            "--output-ds",
            "out",
            "--partition-key",
            "stock",
            "--order-key",
            "date",
            "--compute",
            "lag:date:date_lag",
            "--lag-date-unit",
            "MONTH",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    values = settings.obj_payload["values"]
    date_entry = next(v for v in values if v["column"] == "date")
    assert date_entry["dateDiffUnit"] == "MONTH"


def test_recipe_create_window_lag_date_unit_invalid(patch_client):
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
            "--lag-date-unit",
            "DECADE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_join_invalid_pair_index_fails_before_create(patch_client):
    """An out-of-range -k pair index aborts BEFORE the recipe is created —
    a half-configured join would otherwise run 'successfully' to 0 rows."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "bad_join",
            "-i",
            "orders",
            "-i",
            "returns",
            "-i",
            "managers",
            "--output-ds",
            "out",
            "-k",
            "Order ID",
            "-k",
            "2:Region",  # 3 inputs → pairs 0..1; 2 is the input-index mistake
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Join index 2 out of range" in result.output
    assert "join-PAIR index" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_not_called()
