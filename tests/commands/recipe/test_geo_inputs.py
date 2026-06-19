"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.commands.recipe.helpers import app, runner
from tests.commands.recipe.helpers import setup_prepare_mock as _setup_prepare_mock
from tests.helpers import strip_ansi as _strip_ansi

# Geo Join recipe tests
# ---------------------------------------------------------------------------


def _setup_geojoin_mock(patch_client):
    """Configure mock for geo join recipe tests, patching the direct creator."""
    from unittest.mock import patch

    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"joins": [{"table1": 0, "table2": 1, "on": []}]}
    settings._obj_payload = settings.obj_payload

    # Explicit --geo-column validation reads the input schema. By default make
    # it unreadable so the CLI's "let DSS validate at build" path is taken —
    # tests that pass explicit geo columns are not asserting on schema
    # contents. Tests that exercise the bad-column error override this.
    proj.get_dataset.return_value.get_schema.side_effect = Exception(
        "schema unavailable"
    )

    builder = MagicMock()
    builder.with_input.return_value = builder
    builder.with_existing_output.return_value = builder
    builder.build.return_value = recipe_mock

    patcher = patch(
        "dku_cli.commands.recipe.GeoJoinRecipeCreator", return_value=builder
    )
    mock_cls = patcher.start()
    return proj, builder, settings, mock_cls, patcher


def test_recipe_create_geojoin(patch_client):
    """Basic geo join recipe creation with 2 inputs."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "stores",
                "-i",
                "customers",
                "--output-ds",
                "nearby",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        assert "Created geo join recipe" in result.output
        mock_cls.assert_called_once_with("my_geojoin", proj)
        assert builder.with_input.call_count == 2
        builder.with_existing_output.assert_called_once_with("nearby")
        builder.build.assert_called_once()
    finally:
        patcher.stop()


def test_recipe_create_geojoin_requires_exactly_two_inputs(patch_client):
    """Geo join needs exactly 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly 2" in result.output


def test_recipe_create_geojoin_rejects_three_inputs(patch_client):
    """Geo join rejects 3 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "-i",
            "ds3",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly 2" in result.output


def test_recipe_create_geojoin_invalid_operator(patch_client):
    """Invalid geo operator gives prescriptive error (click.Choice parse-time)."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--operator",
            "INVALID",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_geojoin_invalid_distance_unit(patch_client):
    """Invalid distance unit gives prescriptive error (click.Choice parse-time)."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--distance-unit",
            "parsec",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_geojoin_with_operator(patch_client):
    """--operator INTERSECTS writes an INTERSECTS condition into joins[0].on."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    # DSS BUILDS from joins[0].on, so auto-detect must find a geo column to
    # write the condition: give each input a geopoint column.
    proj.get_dataset.return_value.get_schema.side_effect = None
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [{"name": "the_geom", "type": "geopoint"}]
    }
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--operator",
                "INTERSECTS",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        assert "INTERSECTS" in result.output
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["type"] == "INTERSECTS"
        # INTERSECTS is not a distance operator — no threshold/unit.
        assert "threshold" not in cond
        assert "unit" not in cond
    finally:
        patcher.stop()


def test_recipe_create_geojoin_with_distance(patch_client):
    """--distance and --distance-unit configure the DWITHIN condition threshold."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    # Auto-detect a geo column so the build-time condition is written.
    proj.get_dataset.return_value.get_schema.side_effect = None
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [{"name": "the_geom", "type": "geopoint"}]
    }
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--distance",
                "5000",
                "--distance-unit",
                "km",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["type"] == "DWITHIN"  # WITHIN_DISTANCE → DWITHIN
        assert cond["threshold"] == 5000.0
        assert cond["unit"] == "KILOMETER"  # km → KILOMETER
    finally:
        patcher.stop()


def test_recipe_create_geojoin_uppercase_distance_unit(patch_client):
    """case_sensitive=False: uppercase --distance-unit KM resolves to the
    lowercase-canonical 'km' member (GeoDistanceUnit's values are lowercase)."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--distance",
                "5000",
                "--distance-unit",
                "KM",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0, result.output
        geo_join = settings.obj_payload["joins"][0]
        assert geo_join["geoUnit"] == "km"
    finally:
        patcher.stop()


def test_recipe_create_geojoin_with_geo_columns(patch_client):
    """--geo-column specifies left and right geo columns."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "-g",
                "location_left",
                "-g",
                "location_right",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["column1"] == {"name": "location_left", "table": 0}
        assert cond["column2"] == {"name": "location_right", "table": 1}
    finally:
        patcher.stop()


def test_recipe_create_geojoin_writes_on_condition(patch_client):
    """The geo join must write joins[0].on so DSS can BUILD it.

    Without an `on` condition the recipe is creatable but unbuildable — the
    DSS engine reads the spatial predicate from joins[0].on (DWITHIN + threshold
    + uppercase unit), NOT the join-level geoOperator/geoUnit fields.
    """
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "stores",
                "-i",
                "customers",
                "--output-ds",
                "nearby",
                "-g",
                "store_loc",
                "-g",
                "cust_loc",
                "--operator",
                "WITHIN_DISTANCE",
                "--distance",
                "5000",
                "--distance-unit",
                "meter",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0, result.output
        geo_join = settings.obj_payload["joins"][0]
        assert len(geo_join["on"]) == 1
        cond = geo_join["on"][0]
        assert cond["type"] == "DWITHIN"
        assert cond["column1"] == {"name": "store_loc", "table": 0}
        assert cond["column2"] == {"name": "cust_loc", "table": 1}
        assert cond["threshold"] == 5000.0
        assert cond["unit"] == "METER"
    finally:
        patcher.stop()


def test_recipe_create_geojoin_beyond_distance_on_condition(patch_client):
    """BEYOND_DISTANCE maps to the BEYOND condition type with km→KILOMETER unit."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "-g",
                "a",
                "-g",
                "b",
                "--operator",
                "BEYOND_DISTANCE",
                "--distance",
                "10",
                "--distance-unit",
                "km",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0, result.output
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["type"] == "BEYOND"
        assert cond["threshold"] == 10.0
        assert cond["unit"] == "KILOMETER"
    finally:
        patcher.stop()


def test_recipe_create_geojoin_intersects_on_condition_no_threshold(patch_client):
    """INTERSECTS writes an INTERSECTS condition with no threshold/unit."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "-g",
                "a",
                "-g",
                "b",
                "--operator",
                "INTERSECTS",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0, result.output
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["type"] == "INTERSECTS"
        assert "threshold" not in cond
        assert "unit" not in cond
    finally:
        patcher.stop()


def test_recipe_create_geojoin_warns_when_no_geo_column(patch_client):
    """No --geo-column and no detectable geo column → warn, no on condition."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        # Auto-detect returns None for MagicMock schemas, so no condition is written.
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0, result.output
        geo_join = settings.obj_payload["joins"][0]
        assert geo_join["on"] == []
        assert "Could not determine geo columns" in result.output
    finally:
        patcher.stop()


def test_recipe_create_geojoin_explicit_bad_column_errors(patch_client):
    """An EXPLICIT --geo-column that doesn't exist in the dataset schema is a
    hard error (code bad_column), naming the available geo columns. A typo
    would otherwise create a recipe that exits 0 but can never build.

    Auto-detect failure stays a warning — covered by
    test_recipe_create_geojoin_warns_when_no_geo_column."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        # Schema has a geo column, but NOT the explicitly-named one.
        # Clear the helper's "unreadable schema" default so validation runs.
        proj.get_dataset.return_value.get_schema.side_effect = None
        proj.get_dataset.return_value.get_schema.return_value = {
            "columns": [
                {"name": "id", "type": "string"},
                {"name": "real_geo", "type": "geopoint"},
            ]
        }
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "stores",
                "-i",
                "customers",
                "--output-ds",
                "nearby",
                "-g",
                "typo_geo_col",
                "-g",
                "real_geo",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code != 0
        stripped = _strip_ansi(result.output)
        assert "does not exist" in stripped
        # Available geo columns are named so the agent can fix the typo.
        assert "real_geo" in stripped
        # The recipe must NOT be created: no settings save, no success line.
        settings.save.assert_not_called()
        assert "Created geo join recipe" not in stripped
    finally:
        patcher.stop()


def test_recipe_create_geojoin_geo_columns_requires_two(patch_client):
    """--geo-column must be specified exactly twice."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-geojoin",
            "my_geojoin",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "-g",
            "only_one",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly twice" in result.output


def test_recipe_create_geojoin_auto_applies_schema(patch_client):
    """Schema auto-propagation happens after creation."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        recipe_mock = proj.get_recipe.return_value
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "my_geojoin",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        # _auto_apply_schema calls compute_schema_updates().apply()
        recipe_mock.compute_schema_updates.assert_called()
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Fuzzy Join recipe tests
# ---------------------------------------------------------------------------


def _setup_fuzzyjoin_mock(patch_client):
    """Configure mock for fuzzy join recipe tests, patching the direct creator."""
    from unittest.mock import patch

    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.obj_payload = {"joins": [{"table1": 0, "table2": 1, "on": []}]}
    settings._obj_payload = settings.obj_payload

    builder = MagicMock()
    builder.with_input.return_value = builder
    builder.with_existing_output.return_value = builder
    builder.build.return_value = recipe_mock

    patcher = patch(
        "dku_cli.commands.recipe.FuzzyJoinRecipeCreator", return_value=builder
    )
    mock_cls = patcher.start()
    return proj, builder, settings, mock_cls, patcher


def test_recipe_create_fuzzy_join(patch_client):
    """Basic fuzzy join recipe creation."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "matched",
                "--fuzzy-key",
                "name",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        assert "Created fuzzy join recipe" in result.output
        mock_cls.assert_called_once_with("my_fuzzy", proj)
        assert builder.with_input.call_count == 2
        builder.with_existing_output.assert_called_once_with("matched")
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_condition_shape(patch_client):
    """Conditions carry type=FUZZY + fuzzyMatchDesc; no ignored join-level keys.

    Live-verified on DSS 14.6: join-level fuzzyJoinMethod/fuzzyJoinMaxDistance
    are persisted but ignored (recipe silently does exact matching), and a
    condition without type=FUZZY is dropped (silent cross join).
    """
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "matched",
                "--fuzzy-key",
                "name=ref_name",
                "--max-distance",
                "2",
                "--join-key",
                "country",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        join = settings.obj_payload["joins"][0]
        assert "fuzzyJoinMethod" not in join
        assert "fuzzyJoinMaxDistance" not in join
        assert join["conditionsMode"] == "AND"
        fuzzy_cond, exact_cond = join["on"]
        assert fuzzy_cond == {
            "column1": {"name": "name", "table": 0},
            "column2": {"name": "ref_name", "table": 1},
            "type": "FUZZY",
            "fuzzyMatchDesc": {"distanceType": "LEVENSHTEIN", "threshold": 2},
        }
        assert exact_cond["fuzzyMatchDesc"] == {
            "distanceType": "EXACT",
            "threshold": 0,
        }
        assert exact_cond["column1"]["name"] == "country"
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_requires_a_key(patch_client):
    """No --fuzzy-key and no --join-key = empty conditions = silent cross join."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-fuzzy-join",
            "my_fuzzy",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "--fuzzy-key or --join-key" in result.output
    assert "cross-join" in result.output


def test_recipe_create_fuzzy_join_requires_two_inputs(patch_client):
    """Fuzzy join needs exactly 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-fuzzy-join",
            "my_fuzzy",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "exactly 2" in result.output


def test_recipe_create_fuzzy_join_invalid_method(patch_client):
    """Invalid fuzzy method gives prescriptive error (click.Choice parse-time)."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-fuzzy-join",
            "my_fuzzy",
            "-i",
            "ds1",
            "-i",
            "ds2",
            "--output-ds",
            "out",
            "--method",
            "SOUNDEX",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_create_fuzzy_join_with_fuzzy_key(patch_client):
    """--fuzzy-key adds FUZZY condition to join."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--fuzzy-key",
                "name",
                "--max-distance",
                "3",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        fj = settings.obj_payload["joins"][0]
        assert len(fj["on"]) == 1
        assert fj["on"][0]["type"] == "FUZZY"
        assert fj["on"][0]["fuzzyMatchDesc"] == {
            "distanceType": "LEVENSHTEIN",
            "threshold": 3,
        }
        assert fj["on"][0]["column1"]["name"] == "name"
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_with_exact_and_fuzzy_keys(patch_client):
    """Both --join-key (exact) and --fuzzy-key can be combined."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--join-key",
                "city",
                "--fuzzy-key",
                "name",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        fj = settings.obj_payload["joins"][0]
        conditions = fj["on"]
        assert len(conditions) == 2
        # Every condition is type=FUZZY; exact keys use distanceType=EXACT.
        assert all(c["type"] == "FUZZY" for c in conditions)
        by_distance = {c["fuzzyMatchDesc"]["distanceType"]: c for c in conditions}
        assert by_distance["LEVENSHTEIN"]["column1"]["name"] == "name"
        assert by_distance["EXACT"]["column1"]["name"] == "city"
        assert by_distance["EXACT"]["fuzzyMatchDesc"]["threshold"] == 0
    finally:
        patcher.stop()


def test_recipe_create_fuzzy_join_left_right_key(patch_client):
    """Fuzzy key with left=right syntax."""
    proj, builder, settings, mock_cls, patcher = _setup_fuzzyjoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-fuzzy-join",
                "my_fuzzy",
                "-i",
                "ds1",
                "-i",
                "ds2",
                "--output-ds",
                "out",
                "--fuzzy-key",
                "first_name=fname",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        cond = settings.obj_payload["joins"][0]["on"][0]
        assert cond["column1"]["name"] == "first_name"
        assert cond["column2"]["name"] == "fname"
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Geo prepare shortcut tests
# ---------------------------------------------------------------------------


def test_recipe_add_geopoint(patch_client):
    """add-geopoint creates GeoPointCreator step."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geopoint",
            "prep1",
            "--lat-column",
            "latitude",
            "--lon-column",
            "longitude",
            "--output-column",
            "location",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "GeoPointCreator"
    assert step["params"]["lat_column"] == "latitude"
    assert step["params"]["lon_column"] == "longitude"
    assert step["params"]["out_column"] == "location"
    settings.save.assert_called_once()


def test_recipe_add_geopoint_default_column(patch_client):
    """Default output column is 'geopoint'."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geopoint",
            "prep1",
            "--lat-column",
            "lat",
            "--lon-column",
            "lon",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["out_column"] == "geopoint"


def test_recipe_add_geodistance(patch_client):
    """add-geodistance creates GeoDistanceProcessor step.

    GeoDistanceProcessor's actual params are `input1`, `input2`, `output`
    (NOT `*_column` suffixes — that was a longstanding CLI bug that
    silently produced an "Empty column name" apply-schema error).
    Also requires `compareTo="COLUMN"` and an explicit `outputUnit`
    (MILES or KILOMETERS — defaults to MILES).
    """
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from-column",
            "origin",
            "--to-column",
            "destination",
            "--output-column",
            "dist_mi",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "GeoDistanceProcessor"
    assert step["params"]["input1"] == "origin"
    assert step["params"]["input2"] == "destination"
    assert step["params"]["output"] == "dist_mi"
    assert step["params"]["outputUnit"] == "MILES"
    assert step["params"]["compareTo"] == "COLUMN"
    settings.save.assert_called_once()


def test_recipe_add_geodistance_default_output(patch_client):
    """Default output column is 'geo_distance'."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from-column",
            "origin",
            "--to-column",
            "destination",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["output"] == "geo_distance"


def test_recipe_add_geodistance_kilometers(patch_client):
    """--unit KILOMETERS sets outputUnit accordingly."""
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from-column",
            "a",
            "--to-column",
            "b",
            "--unit",
            "KILOMETERS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["params"]["outputUnit"] == "KILOMETERS"


def test_recipe_add_geodistance_invalid_unit(patch_client):
    """Bad --unit value exits non-zero (click.Choice rejects at parse time)."""
    _proj, _recipe, _settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-geodistance",
            "prep1",
            "--from-column",
            "a",
            "--to-column",
            "b",
            "--unit",
            "FURLONGS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in _strip_ansi(result.output)


def test_recipe_add_input_folder_by_name_resolves_to_id(patch_client):
    """Folder name → folder ID resolution on add-input."""
    proj = patch_client.get_project("PROJ1")
    # Ensure "Data Folder" is not a dataset — auto-detect should pick folder
    ds_mock = MagicMock()
    ds_mock.get_definition.side_effect = Exception("NotFoundException")
    default_ds = proj.get_dataset.return_value

    def get_dataset(ref):
        if ref == "Data Folder":
            return ds_mock
        return default_ds

    proj.get_dataset.side_effect = get_dataset

    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "Data Folder",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "folder 'folder1'" in result.output
    recipe = proj.get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("main", "folder1")


def test_recipe_add_input_saved_model_defaults_role_model(patch_client):
    """Saved model name → model ID, role defaults to 'model'."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "My Model",
            "--type",
            "SAVED_MODEL",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "saved model 'model1'" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("model", "model1")


def test_recipe_add_input_rejects_unknown_ref(patch_client):
    proj = patch_client.get_project("PROJ1")
    # Nothing in the project matches "does_not_exist_anywhere"
    ds_mock = MagicMock()
    ds_mock.get_definition.side_effect = Exception("NotFoundException")
    default_ds = proj.get_dataset.return_value

    def get_dataset(ref):
        if ref == "does_not_exist_anywhere":
            return ds_mock
        return default_ds

    proj.get_dataset.side_effect = get_dataset

    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "does_not_exist_anywhere",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 3
    assert "not a dataset, managed folder, or saved model" in result.output


def test_recipe_add_input_explicit_type_dataset(patch_client):
    """--type DATASET skips folder/model probing."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "extra_input",
            "--type",
            "DATASET",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output


def test_recipe_create_scoring_requires_model(patch_client):
    """clustering_scoring must be rejected when --model is omitted."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "score_it",
            "-t",
            "clustering_scoring",
            "-i",
            "input_ds",
            "--output-ds",
            "scored",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "requires a saved model" in result.output
    assert "--model" in result.output


def test_recipe_create_clustering_scoring_wires_model_before_build(patch_client):
    """Generic scoring path must wire the model via with_input_model BEFORE build.

    Building a *ScoringRecipeCreator without the model first throws a server-side
    IndexOutOfBoundsException — the post-mortem failure. Adding the model after
    build (the old behavior) cannot work because build() itself fails.
    """
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe("clustering_scoring", "score_it")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "score_it",
            "-t",
            "clustering_scoring",
            "-i",
            "input_ds",
            "--model",
            "sm1",
            "--output-ds",
            "scored",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    builder.with_input_model.assert_called_once()
    builder.build.assert_called_once()


def test_agent_tool_create_kb_resolves_name_to_id(patch_client):
    """--kb NAME must resolve to the KB id via list_knowledge_banks."""
    proj = patch_client.get_project("PROJ1")
    # Seed knowledge bank list so name→ID resolution works
    proj.list_knowledge_banks.return_value = [
        {"id": "kb_id_123", "name": "my_kb"},
    ]
    # Make get_knowledge_bank(name).get_settings() raise to force fallback
    kb_mock_by_name = MagicMock()
    kb_mock_by_name.get_settings.side_effect = Exception("NotFoundException")
    kb_mock_by_id = MagicMock()
    kb_mock_by_id.id = "kb_id_123"
    kb_mock_by_id.get_settings.return_value = MagicMock()

    def get_kb(ref):
        if ref == "kb_id_123":
            return kb_mock_by_id
        return kb_mock_by_name

    proj.get_knowledge_bank.side_effect = get_kb

    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "search_tool",
            "--type",
            "VectorStoreSearch",
            "--kb",
            "my_kb",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    builder = proj.new_agent_tool.return_value
    builder.with_knowledge_bank.assert_called_once_with("kb_id_123")


# ── NET-NEW (PR surface): create-geojoin CONTAINS writes an on[] condition ──


def test_recipe_create_geojoin_contains_condition(patch_client):
    """CONTAINS operator writes a CONTAINS MatchingCondition into on[] with the
    explicit -g geo columns (no distance/unit) — regression for the bug where
    on[] was left empty and the build failed with 'Empty join conditions'."""
    proj, builder, settings, mock_cls, patcher = _setup_geojoin_mock(patch_client)
    try:
        result = runner.invoke(
            app,
            [
                "recipe",
                "create-geojoin",
                "geo_match",
                "-i",
                "regions",
                "-i",
                "points",
                "--output-ds",
                "matched",
                "--operator",
                "CONTAINS",
                "-g",
                "region_poly",
                "-g",
                "pt",
                "--join-type",
                "INNER",
                "--project",
                "PROJ1",
            ],
        )
        assert result.exit_code == 0
        on = settings.obj_payload["joins"][0]["on"]
        assert len(on) == 1
        cond = on[0]
        assert cond["type"] == "CONTAINS"
        assert cond["column1"] == {"name": "region_poly", "table": 0}
        assert cond["column2"] == {"name": "pt", "table": 1}
        # CONTAINS is not a distance operator — no threshold/unit.
        assert "threshold" not in cond
        assert "unit" not in cond
        assert settings.obj_payload["joins"][0]["type"] == "INNER"
    finally:
        patcher.stop()
