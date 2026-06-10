"""Join-style visual recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from dku_cli.enums import (
    ConditionsMode,
    EngineType,
    FuzzyMethod,
    GeoDistanceUnit,
    GeoJoinType,
    GeoOperator,
    JoinType,
    RightLimitKeep,
)

from ._common import *

# ---------------------------------------------------------------------------
# Visual recipe creation commands (prefer these over Python)
# ---------------------------------------------------------------------------


@app.command("create-join")
def create_join(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets (repeat for multiple: -i ds1 -i ds2)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    join_key: list[str] = typer.Option(
        None,
        "--join-key",
        "-k",
        help=(
            "Join key: 'col' (same both sides) or 'left=right'. Repeatable. "
            "For multi-input joins (3+ datasets), prefix with join index: '1:col' targets the 2nd join pair. "
            "Unprefixed keys target join 0 (first pair)."
        ),
    ),
    join_type: JoinType = typer.Option(
        JoinType.LEFT,
        "--join-type",
        "-j",
        case_sensitive=False,
        help=(
            "Join type: LEFT, INNER, RIGHT, FULL, CROSS, LEFT_ANTI, RIGHT_ANTI, "
            "ADVANCED. LEFT_ANTI = left rows with NO match in right ('candidates "
            "minus positives' pattern). RIGHT_ANTI = symmetric. FULL = outer join. "
            "ADVANCED = expression-based ON clause via --advanced-condition. "
            "Applied to all join pairs. Default: LEFT."
        ),
    ),
    auto_cast: bool = typer.Option(
        False,
        "--auto-cast",
        help=(
            "Set enableAutoCastInJoinConditions=true so DSS auto-casts "
            "join keys with mismatched types (e.g. string vs bigint)."
        ),
    ),
    cols: list[str] | None = typer.Option(
        None,
        "--cols",
        help=(
            "Per-input column projection: 'INDEX:c1,c2,c3' — only the listed "
            "columns from input INDEX flow through. Sets that virtualInput's "
            "outputColumnsSelectionMode=MANUAL + selectedColumns. Repeatable. "
            "Replaces a downstream Prepare add-delete-columns."
        ),
    ),
    engine: EngineType | None = typer.Option(
        None,
        "--engine",
        case_sensitive=False,
        help=(
            "payload.engineType: DSS (default), SQL, SPARK_SQL, IMPALA, HIVE. "
            "Top-level field, separate from engineParams.<engine>.executionEngine. "
            "Set SQL for Snowflake/Postgres pushdown."
        ),
    ),
    case_insensitive: bool = typer.Option(
        False,
        "--case-insensitive",
        help="Set caseInsensitive=true on every EQ join condition (compares 'Foo' == 'foo').",
    ),
    normalize_text: bool = typer.Option(
        False,
        "--normalize-text",
        help="Set normalizeText=true on every EQ condition (lowercases + trims before compare). Implies case-insensitive.",
    ),
    max_matches: int | None = typer.Option(
        None,
        "--max-matches",
        help=(
            "maxMatches per join condition. Limits fan-out: cap the number of right rows joined per left row. "
            "Default 1 in DSS payload, 0 disables the cap."
        ),
    ),
    max_distance: int | None = typer.Option(
        None,
        "--max-distance",
        help=(
            "Levenshtein maxDistance on EQ conditions — fuzzy match without leaving create-join "
            "(e.g. 1 = at most one edit). Set on each EQ condition's payload."
        ),
    ),
    date_window: str | None = typer.Option(
        None,
        "--date-window",
        help=(
            "Date-tolerance match. Format: 'FROM:TO[:UNIT]' (UNIT default DAY). "
            "Example: '-7:7:DAY' joins rows whose date columns differ by ≤ 7 days. "
            "Maps to windowFrom/windowTo/dateDiffUnit on every EQ condition. "
            "Replaces the Cross+Filter / Python pattern for SAS PROC SQL date-band joins."
        ),
    ),
    outer_join_on_left: bool | None = typer.Option(
        None,
        "--outer-join-on-left/--outer-join-on-right",
        help=(
            "Override outerJoinOnTheLeft on every join pair. By default LEFT joins keep left, "
            "RIGHT joins keep right. Use --outer-join-on-right to flip a LEFT join's preserve side."
        ),
    ),
    right_limit_max_matches: int | None = typer.Option(
        None,
        "--right-limit-max-matches",
        help=(
            "Enable rightLimit on every join pair, keeping at most N right matches per left row. "
            "Pair with --right-limit-keep / --right-limit-decision-column for "
            "'keep first/last/largest match' semantics on regular EQ joins."
        ),
    ),
    right_limit_decision_column: str | None = typer.Option(
        None,
        "--right-limit-decision-column",
        help=(
            "Column on the right side of the join used as the rightLimit tiebreaker. "
            "Required for KEEP_LARGEST / KEEP_SMALLEST. "
            "Example: --right-limit-decision-column record_date with --right-limit-keep KEEP_LARGEST."
        ),
    ),
    right_limit_keep: RightLimitKeep | None = typer.Option(
        None,
        "--right-limit-keep",
        case_sensitive=False,
        help="rightLimit.type: KEEP_LARGEST | KEEP_SMALLEST | KEEP_FIRST | KEEP_LAST. Default in DSS: KEEP_LARGEST.",
    ),
    right_limit_strict: bool = typer.Option(
        False,
        "--right-limit-strict",
        help="rightLimit.strict=true — drop right rows whose decisionColumn value is NULL.",
    ),
    strict_eq: bool = typer.Option(
        False,
        "--strict-eq",
        help=(
            "Set strict=true on every EQ condition. Without this, NULL=NULL "
            "matches (DSS default — surprising for SQL agents). With "
            "--strict-eq, only non-null values match — matches SQL semantics "
            "where NULL=NULL is unknown."
        ),
    ),
    conditions_mode: ConditionsMode | None = typer.Option(
        None,
        "--conditions-mode",
        case_sensitive=False,
        help=(
            "Inter-condition combinator: AND (default — all ON conditions "
            "must match) or OR (any matches — equivalent to "
            "LEFT JOIN ... ON (a.x=b.x OR a.y=b.y), the SAS PROC SQL "
            "alternation pattern, replaces a 2-Joins+Stack workaround). "
            "Sets joins[].conditionsMode."
        ),
    ),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help=(
            "Create the output as a managed dataset on this connection "
            "(e.g. a Snowflake connection for in-database execution). "
            "Without it the output lands on the default managed "
            "(filesystem) connection."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Join recipe. NEVER use Python for joins — use this instead.

    Supports 2+ input datasets in a SINGLE recipe — prefer this over
    cascading join recipes. Pass all datasets with -i: -i ds1 -i ds2 -i ds3.

    --join-key is REQUIRED in practice. Auto-detection on shared column
    names is NOT implemented — running create-join without --join-key (and
    without --join-type CROSS) leaves the join with empty conditions, which
    DSS executes as a CROSS join. The CLI now warns when this happens.
    Format: 'col' (same both sides) or 'left=right'. For multi-input joins
    use --join-key col (join 0, first pair) and --join-key 1:col (join 1,
    second pair). CROSS joins need no keys — pass --join-type CROSS.

    Advanced match modes (apply to every EQ condition on every pair):
      --case-insensitive / --normalize-text     fuzzy text matching
      --max-distance N                           Levenshtein fuzzy EQ (1 edit = N=1)
      --date-window -7:7:DAY                     date-tolerance band match
      --max-matches N                            cap right matches per left row

    rightLimit (deduplicate to first/best match) — works on EQ joins, not just spatial:
      --right-limit-max-matches 1 \\
      --right-limit-decision-column record_date \\
      --right-limit-keep KEEP_LARGEST [--right-limit-strict]
    """
    project_key = resolve_project(project)
    engine_upper = _enum_value(engine)
    jt = join_type.value
    if len(inputs) < 2:
        exit_with_error(
            "Join recipes need at least 2 input datasets.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-join NAME -i ds1 -i ds2 --output-ds out -P PROJ"
            ],
        )

    # Validate --date-window FROM:TO[:UNIT]
    parsed_date_window: tuple[int, int, str] | None = None
    if date_window:
        parts = date_window.split(":")
        if len(parts) not in (2, 3):
            exit_with_error(
                f"Invalid --date-window '{date_window}'. Expected 'FROM:TO[:UNIT]'.",
                code="invalid_argument",
                details=[
                    "Example: --date-window -7:7:DAY (rows whose dates differ by ≤ 7 days)"
                ],
            )
        try:
            wf, wt = int(parts[0]), int(parts[1])
        except ValueError:
            exit_with_error(
                f"--date-window '{date_window}': FROM and TO must be integers.",
                code="invalid_argument",
            )
        unit = parts[2].upper() if len(parts) == 3 else "DAY"
        _VALID_DATE_UNITS = {
            "YEAR",
            "QUARTER",
            "MONTH",
            "WEEK",
            "DAY",
            "HOUR",
            "MINUTE",
            "SECOND",
            "MILLISECOND",
        }
        if unit not in _VALID_DATE_UNITS:
            exit_with_error(
                f"--date-window unit '{unit}' is not valid.",
                code="invalid_argument",
                details=[f"Valid units: {', '.join(sorted(_VALID_DATE_UNITS))}"],
            )
        parsed_date_window = (wf, wt, unit)

    # Pre-flight: per-condition match modifiers need an EQ join condition to
    # apply to. Refuse BEFORE creating the recipe/output dataset, so a guard
    # failure does not leave an orphan auto-created --output-ds in the flow
    # (the post-create check below remains as a backstop for key specs that
    # produce no EQ conditions).
    _modifier_flags = (
        case_insensitive
        or normalize_text
        or max_matches is not None
        or max_distance is not None
        or parsed_date_window is not None
        or strict_eq
    )
    if _modifier_flags and (not join_key or (join_type and join_type.value == "CROSS")):
        exit_with_error(
            "--case-insensitive / --normalize-text / --strict-eq / "
            "--max-distance / --max-matches / --date-window need an EQ "
            "join condition to apply to, but no join key was set.",
            code="invalid_argument",
            details=[
                "Pass --join-key COL (e.g. --join-key id) so the modifiers have",
                "a condition to attach to. For multi-input joins, prefix with",
                "the join index: --join-key 1:col.",
            ],
        )

    # Validate --right-limit-keep
    rl_keep_upper: str | None = None
    if right_limit_keep:
        rl_keep_upper = right_limit_keep.value

    # rightLimit cross-checks: KEEP_LARGEST/SMALLEST need a decisionColumn.
    right_limit_enabled = (
        right_limit_max_matches is not None
        or right_limit_decision_column is not None
        or right_limit_keep is not None
        or right_limit_strict
    )
    if right_limit_enabled:
        if (
            rl_keep_upper in {"KEEP_LARGEST", "KEEP_SMALLEST"}
            and not right_limit_decision_column
        ):
            exit_with_error(
                f"--right-limit-keep {rl_keep_upper} requires --right-limit-decision-column.",
                code="invalid_argument",
                details=[
                    "KEEP_LARGEST / KEEP_SMALLEST need a column to compare. "
                    "Use --right-limit-decision-column COL (the right-side tiebreaker column)."
                ],
            )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("join", recipe_name)
        for ds in inputs:
            builder.with_input(ds)
        _wire_single_output(client, proj, builder, output_ds, project_key, connection)
        builder.build()

        recipe_obj = proj.get_recipe(recipe_name)
        join_settings = recipe_obj.get_settings()
        joins = join_settings.raw_joins

        # DSS's builder may pre-create a single default join pair when there are
        # 2+ inputs, leaving `joins` at length 1 regardless of input count.
        # Extend to exactly N-1 join pairs so --join-key 1:col, 2:col, ... all
        # resolve to a valid target. Each join fans out from table 0 (the main
        # table) to table i+1 (each subsequent input).
        # Only extend when raw_joins is a real list (not a test MagicMock).
        if isinstance(joins, list):
            target_pairs = max(0, len(inputs) - 1)
            existing_pairs = len(joins)
            for i in range(existing_pairs, target_pairs):
                joins.append(
                    {
                        "table1": 0,
                        "table2": i + 1,
                        "conditionsMode": "AND",
                        "type": jt,
                        "outerJoinOnTheLeft": True,
                        "on": [],
                    }
                )

        # Set join type on all existing join pairs
        for j in joins:
            j["type"] = jt

        # Configure join keys if provided (skip for CROSS joins)
        if join_key and jt != "CROSS":
            import re

            from dataikuapi.dss.recipe import JoinRecipeSettings

            # Parse indexed key specs: "col", "left=right", "1:col", "1:left=right"
            keys_by_idx: dict[int, list[tuple[str, str]]] = {}
            for key_spec in join_key:
                idx = 0
                spec = key_spec
                m = re.match(r"^(\d+):", key_spec)
                if m:
                    idx = int(m.group(1))
                    spec = key_spec[m.end() :]
                if "=" in spec:
                    col1, col2 = spec.split("=", 1)
                else:
                    col1 = col2 = spec
                keys_by_idx.setdefault(idx, []).append((col1.strip(), col2.strip()))

            for idx, key_pairs in keys_by_idx.items():
                if idx >= len(joins):
                    exit_with_error(
                        f"Join index {idx} out of range — recipe has {len(joins)} join pair(s) (0-indexed).",
                        code="invalid_argument",
                        details=[
                            f"With {len(inputs)} inputs, valid join indices are 0..{len(joins) - 1}",
                        ],
                    )
                target_join = joins[idx]
                for col1, col2 in key_pairs:
                    JoinRecipeSettings.add_condition_to_join(
                        target_join,
                        type="EQ",
                        column1=col1,
                        column2=col2,
                    )

            info(f"Join keys: {', '.join(join_key)}")
        elif join_key and jt == "CROSS":
            warn("CROSS join ignores --join-key (no conditions needed)")

        # Multi-input (3+) guard: extra join pairs are appended with on:[] and
        # only receive conditions when keys are index-prefixed (e.g. '2:col').
        # Any non-CROSS pair left with no condition becomes a silent cartesian
        # join, so warn LOUDLY (keep creating — the UI can configure later).
        if jt != "CROSS" and len(inputs) > 2 and isinstance(joins, list):
            empty_pairs = [
                j.get("table2", n + 1) for n, j in enumerate(joins) if not j.get("on")
            ]
            if empty_pairs:
                named = ", ".join(
                    inputs[t] if 0 <= t < len(inputs) else f"input {t}"
                    for t in empty_pairs
                )
                warn(
                    f"No join condition for: {named} — these would join as a "
                    f"CARTESIAN (cross) product for a {jt} join. "
                    "Prefix keys with the join index, e.g. "
                    f"-k {empty_pairs[0]}:customer_id, to add a condition "
                    "for each extra input (or configure them later in the UI)."
                )

        # --auto-cast: enable enableAutoCastInJoinConditions on the payload
        if auto_cast:
            join_settings.obj_payload["enableAutoCastInJoinConditions"] = True
            info("Auto-cast in join conditions: enabled")

        # --conditions-mode AND/OR overrides every join pair's combinator.
        cm_upper: str | None = None
        if conditions_mode is not None:
            cm_upper = conditions_mode.value
            if isinstance(joins, list):
                for j in joins:
                    j["conditionsMode"] = cm_upper
                info(f"Conditions mode: {cm_upper}")

        # Apply per-condition advanced match modes across all joins.
        any_condition_extra = (
            case_insensitive
            or normalize_text
            or max_matches is not None
            or max_distance is not None
            or parsed_date_window is not None
            or strict_eq
        )
        if any_condition_extra and isinstance(joins, list):
            # These modifiers mutate existing EQ conditions. Without --join-key
            # the join pairs carry no conditions, so the modifiers would be
            # silently dropped while we still print "Match mode: ...". Refuse.
            eq_conditions = [
                cond
                for j in joins
                for cond in j.get("on", [])
                if cond.get("type") == "EQ"
            ]
            if not eq_conditions:
                exit_with_error(
                    "--case-insensitive / --normalize-text / --strict-eq / "
                    "--max-distance / --max-matches / --date-window need an EQ "
                    "join condition to apply to, but no join key was set.",
                    code="invalid_argument",
                    details=[
                        "Pass --join-key COL (e.g. --join-key id) so there is a "
                        "condition to modify.",
                        "For multi-input joins, prefix with the join index: "
                        "--join-key 1:col.",
                    ],
                )
            for j in joins:
                for cond in j.get("on", []):
                    if cond.get("type") != "EQ":
                        continue
                    if case_insensitive or normalize_text:
                        cond["caseInsensitive"] = True
                    if normalize_text:
                        cond["normalizeText"] = True
                    if strict_eq:
                        cond["strict"] = True
                    if max_matches is not None:
                        cond["maxMatches"] = max_matches
                    if max_distance is not None:
                        cond["maxDistance"] = max_distance
                    if parsed_date_window is not None:
                        wf, wt, unit = parsed_date_window
                        cond["windowFrom"] = wf
                        cond["windowTo"] = wt
                        cond["dateDiffUnit"] = unit
            modes = []
            if case_insensitive or normalize_text:
                modes.append("case-insensitive")
            if normalize_text:
                modes.append("normalize-text")
            if strict_eq:
                modes.append("strict-eq")
            if max_distance is not None:
                modes.append(f"levenshtein≤{max_distance}")
            if parsed_date_window is not None:
                modes.append(
                    f"date-window {parsed_date_window[0]}:{parsed_date_window[1]}:{parsed_date_window[2]}"
                )
            if max_matches is not None:
                modes.append(f"maxMatches={max_matches}")
            info("Match mode: " + ", ".join(modes))

        # --outer-join-on-left override on every join pair.
        if outer_join_on_left is not None and isinstance(joins, list):
            for j in joins:
                j["outerJoinOnTheLeft"] = bool(outer_join_on_left)
            info(f"outerJoinOnTheLeft: {bool(outer_join_on_left)}")

        # rightLimit block: applies to every join pair uniformly.
        if right_limit_enabled and isinstance(joins, list):
            for j in joins:
                rl = j.setdefault("rightLimit", {})
                rl["enabled"] = True
                if right_limit_max_matches is not None:
                    rl["maxMatches"] = right_limit_max_matches
                if rl_keep_upper is not None:
                    rl["type"] = rl_keep_upper
                if right_limit_decision_column is not None:
                    rl["decisionColumn"] = {
                        "name": right_limit_decision_column,
                        "table": j.get("table2", 1),
                    }
                if right_limit_strict:
                    rl["strict"] = True
            details = []
            if right_limit_max_matches is not None:
                details.append(f"maxMatches={right_limit_max_matches}")
            if rl_keep_upper:
                details.append(rl_keep_upper)
            if right_limit_decision_column:
                details.append(f"by={right_limit_decision_column}")
            if right_limit_strict:
                details.append("strict")
            info("rightLimit: " + ", ".join(details))

        _apply_engine_type(join_settings.obj_payload, engine_upper)
        if engine_upper:
            info(f"Engine: {engine_upper}")

        # --cols INDEX:a,b,c: per-input MANUAL column projection
        if cols:
            virtual_inputs = join_settings.obj_payload.get("virtualInputs", [])
            for entry in cols:
                if ":" not in entry:
                    exit_with_error(
                        f"Invalid --cols '{entry}'. Expected 'INDEX:c1,c2,c3'.",
                        code="invalid_argument",
                    )
                idx_str, cols_str = entry.split(":", 1)
                try:
                    idx = int(idx_str)
                except ValueError:
                    exit_with_error(
                        f"Invalid input index in --cols '{entry}'.",
                        code="invalid_argument",
                    )
                if idx < 0 or idx >= len(inputs):
                    exit_with_error(
                        f"--cols index {idx} out of range (0..{len(inputs) - 1}).",
                        code="invalid_argument",
                    )
                col_list = [c.strip() for c in cols_str.split(",") if c.strip()]
                # Pad virtualInputs if needed (some setups create them lazily).
                while len(virtual_inputs) <= idx:
                    virtual_inputs.append({"index": len(virtual_inputs)})
                vi = virtual_inputs[idx]
                vi["outputColumnsSelectionMode"] = "MANUAL"
                vi["selectedColumns"] = col_list
                info(f"Cols input {idx}: {', '.join(col_list)}")

        join_settings.save()
        _auto_apply_schema(proj, recipe_name)

        # Silent CROSS-join trap: DSS does NOT auto-detect join keys on shared
        # column names. If the user didn't pass --join-key (and isn't asking
        # for a CROSS join), every pair lands with on:[] and the join executes
        # as a Cartesian product. Emit a loud warning so agents catch this
        # before running the recipe (a 51B-row CROSS-join surprise is the
        # canonical failure mode here).
        if jt != "CROSS" and isinstance(joins, list):
            empty_pairs = [idx for idx, j in enumerate(joins) if not j.get("on")]
            if empty_pairs:
                pairs_label = (
                    "pair " + str(empty_pairs[0])
                    if len(empty_pairs) == 1
                    else "pairs " + ", ".join(str(i) for i in empty_pairs)
                )
                warn(
                    f"Join recipe '{recipe_name}' has empty conditions on {pairs_label}. "
                    f"DSS will execute this as a CROSS join — every left row joined to every right row."
                )
                warn(
                    "Auto-detection on shared column names is NOT implemented. "
                    "Re-run with --join-key COL (or --join-key N:COL for non-first pair), "
                    "OR pass --join-type CROSS to confirm Cartesian intent."
                )

        success(f"Created {jt} join recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# Geo join builds from the `on` condition, which uses different vocabulary than
# the join-level geoOperator/geoUnit fields (confirmed against the DSS geo-join UI).
_GEO_OP_TO_CONDITION = {
    "WITHIN_DISTANCE": "DWITHIN",
    "BEYOND_DISTANCE": "BEYOND",
    "INTERSECTS": "INTERSECTS",
    "CONTAINS": "CONTAINS",
}
_GEO_UNIT_TO_DSS = {
    "meter": "METER",
    "km": "KILOMETER",
    "foot": "FOOT",
    "yard": "YARD",
    "mile": "MILE",
    "nautical_mile": "NAUTICAL_MILE",
}


def _first_geo_column(proj, dataset_name: str) -> str | None:
    """First geopoint/geometry column in a dataset's schema, or None."""
    try:
        columns = proj.get_dataset(dataset_name).get_schema().get("columns", [])
    except Exception:
        return None
    for col in columns:
        if col.get("type") in ("geopoint", "geometry"):
            return col.get("name")
    return None


@app.command("create-geojoin")
def create_geojoin(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets (exactly 2: -i left_ds -i right_ds)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    geo_column: list[str] | None = typer.Option(
        None,
        "--geo-column",
        "-g",
        help=(
            "Geo columns from each dataset (repeat 2x: -g left_geo -g right_geo). "
            "Omit to let DSS auto-detect from geopoint/geometry columns."
        ),
    ),
    operator: GeoOperator = typer.Option(
        GeoOperator.WITHIN_DISTANCE,
        "--operator",
        "--op",
        case_sensitive=False,
        help="Geo operator: WITHIN_DISTANCE, BEYOND_DISTANCE, INTERSECTS, CONTAINS",
    ),
    distance: float = typer.Option(
        1000,
        "--distance",
        "-d",
        help="Distance threshold (only for WITHIN_DISTANCE / BEYOND_DISTANCE)",
    ),
    distance_unit: GeoDistanceUnit = typer.Option(
        GeoDistanceUnit.meter,
        "--distance-unit",
        "-u",
        case_sensitive=False,
        help="Distance unit: meter, km, foot, yard, mile, nautical_mile",
    ),
    join_type: GeoJoinType = typer.Option(
        GeoJoinType.LEFT,
        "--join-type",
        "-j",
        case_sensitive=False,
        help="Join type: LEFT (default, keep all left rows), INNER, RIGHT, FULL.",
    ),
    max_matches: int | None = typer.Option(
        None,
        "--max-matches",
        help=(
            "Limit the right-side matches per left row (e.g. 1 to keep one "
            "best match per left row instead of fanning-out)."
        ),
    ),
    right_limit_strategy: RightLimitKeep | None = typer.Option(
        None,
        "--right-limit-strategy",
        case_sensitive=False,
        help=(
            "When --max-matches is set, how to pick the surviving matches: "
            "KEEP_LARGEST (default if unset), KEEP_SMALLEST, KEEP_FIRST, KEEP_LAST."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Geo Join recipe. NEVER use Python haversine — use this instead.

    Joins two datasets using geospatial matching. Both datasets must have
    a geopoint or geometry column (use add-geopoint to create one first).

    Operators:
      WITHIN_DISTANCE  — rows within --distance of each other (default)
      BEYOND_DISTANCE  — rows farther than --distance
      INTERSECTS       — geometries that overlap (no distance needed)
      CONTAINS         — left geometry contains right geometry

    Example: dku recipe create-geojoin geo_step -i stores -i customers \\
      --output-ds nearby --operator WITHIN_DISTANCE --distance 5000 -u meter -P PROJ
    """
    project_key = resolve_project(project)
    op = operator.value
    du = distance_unit.value
    if len(inputs) != 2:
        exit_with_error(
            f"Geo join requires exactly 2 input datasets, got {len(inputs)}.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-geojoin NAME -i left_ds -i right_ds --output-ds out -P PROJ"
            ],
        )
    if geo_column and len(geo_column) != 2:
        exit_with_error(
            f"--geo-column must be specified exactly twice (left and right), got {len(geo_column)}.",
            code="invalid_argument",
            details=[
                "Use: -g left_geo_col -g right_geo_col",
                "Or omit --geo-column to let DSS auto-detect from geopoint/geometry columns.",
            ],
        )
    if op in ("INTERSECTS", "CONTAINS") and distance != 1000:
        warn(f"{op} ignores --distance (no distance threshold needed)")

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)

        # GeoJoinRecipeCreator exists in dataikuapi but is not wired into
        # DSSProject.new_recipe(). Instantiate directly.
        from dku_cli.commands import recipe as recipe_module

        builder = recipe_module.GeoJoinRecipeCreator(recipe_name, proj)
        for ds in inputs:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure geo join conditions in payload
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        # Geo join stores its config in the joins array, similar to regular join.
        # Each join entry has geoJoin fields for spatial matching.
        joins = payload.get("joins", [])
        if not joins:
            joins = [{"table1": 0, "table2": 1, "on": []}]
            payload["joins"] = joins

        geo_join = joins[0]
        geo_join["geoJoin"] = True
        geo_join["geoOperator"] = op
        if op in ("WITHIN_DISTANCE", "BEYOND_DISTANCE"):
            geo_join["geoDistance"] = distance
            geo_join["geoUnit"] = du

        # Resolve the geo columns: explicit --geo-column, else the first
        # geopoint/geometry column in each input's schema. An EXPLICIT column
        # that doesn't exist is a hard error (a typo would otherwise create a
        # recipe that exits 0 but can never build); auto-detect failure stays
        # a warning since the user can still wire columns in the UI.
        if geo_column:
            geo1, geo2 = geo_column[0], geo_column[1]
            for ds_name, col in ((inputs[0], geo1), (inputs[1], geo2)):
                try:
                    cols = proj.get_dataset(ds_name).get_schema().get("columns", [])
                except Exception:
                    continue  # unreadable schema — let DSS validate at build
                names = [c.get("name") for c in cols]
                if col not in names:
                    geo_names = [
                        c.get("name")
                        for c in cols
                        if c.get("type") in ("geopoint", "geometry")
                    ]
                    exit_with_error(
                        f"--geo-column '{col}' does not exist in dataset '{ds_name}'.",
                        code="bad_column",
                        details=[
                            (
                                f"Geo columns in {ds_name}: {', '.join(geo_names)}"
                                if geo_names
                                else f"{ds_name} has NO geopoint/geometry column — "
                                "type one first: dku dataset set-schema ..."
                            ),
                            f"All columns: {', '.join(n for n in names if n)}",
                        ],
                    )
        else:
            geo1 = _first_geo_column(proj, inputs[0])
            geo2 = _first_geo_column(proj, inputs[1])

        if geo1 and geo2:
            geo_join["geoColumn1"] = geo1
            geo_join["geoColumn2"] = geo2
            # DSS BUILDS from joins[0].on, not the join-level geo fields above.
            # The condition uses its own vocabulary (DWITHIN/BEYOND + threshold +
            # uppercase unit) — without it the recipe is creatable but won't build.
            condition = {
                "column1": {"name": geo1, "table": 0},
                "column2": {"name": geo2, "table": 1},
                "type": _GEO_OP_TO_CONDITION[op],
            }
            if op in ("WITHIN_DISTANCE", "BEYOND_DISTANCE"):
                condition["threshold"] = distance
                condition["unit"] = _GEO_UNIT_TO_DSS[du]
            geo_join["on"] = [condition]
        else:
            warn(
                "Could not determine geo columns (no geopoint/geometry column "
                "found in inputs). Pass --geo-column LEFT_GEO --geo-column RIGHT_GEO. "
                "The recipe was created but will not build without a geo condition."
            )

        jt = join_type.value
        geo_join["type"] = jt

        if max_matches is not None:
            strategy = (
                right_limit_strategy.value
                if right_limit_strategy is not None
                else "KEEP_LARGEST"
            )
            geo_join["rightLimit"] = {
                "enabled": True,
                "maxMatches": max_matches,
                "type": strategy,
            }
        elif right_limit_strategy:
            warn("--right-limit-strategy ignored without --max-matches.")

        settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created geo join recipe '{recipe_name}' ({op}) in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-fuzzy-join")
def create_fuzzy_join(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    inputs: list[str] = typer.Option(
        ...,
        "--input",
        "-i",
        "--input-ds",
        help="Input datasets (exactly 2: -i left_ds -i right_ds)",
    ),
    output_ds: str = typer.Option(
        ..., "--output-ds", "--output-dataset", help="Output dataset name"
    ),
    fuzzy_key: list[str] | None = typer.Option(
        None,
        "--fuzzy-key",
        "-f",
        help="Fuzzy match column: 'col' (same both sides) or 'left=right'. Repeatable.",
    ),
    join_key: list[str] | None = typer.Option(
        None,
        "--join-key",
        "-k",
        help="Exact-match key: 'col' (same both sides) or 'left=right'. Repeatable.",
    ),
    max_distance: int = typer.Option(
        1,
        "--max-distance",
        help="Maximum edit distance for fuzzy matching (default: 1)",
    ),
    method: FuzzyMethod = typer.Option(
        FuzzyMethod.LEVENSHTEIN,
        "--method",
        "-m",
        case_sensitive=False,
        help="Fuzzy method: LEVENSHTEIN, JARO_WINKLER, NORMALIZED_LEVENSHTEIN",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a Fuzzy Join recipe for approximate string matching.

    Joins two datasets using approximate (fuzzy) matching on text columns.
    Use for name deduplication, address matching, or linking messy text data.

    Example: dku recipe create-fuzzy-join fuzzy_step -i ds1 -i ds2 \\
      --output-ds matched --fuzzy-key name --max-distance 2 -P PROJ
    """
    project_key = resolve_project(project)
    m = method.value
    if len(inputs) != 2:
        exit_with_error(
            f"Fuzzy join requires exactly 2 input datasets, got {len(inputs)}.",
            code="invalid_argument",
            details=[
                "Use: dku recipe create-fuzzy-join NAME -i left_ds -i right_ds --output-ds out -P PROJ"
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _ensure_output_dataset(client, proj, output_ds, project_key)

        # FuzzyJoinRecipeCreator exists in dataikuapi but is not wired into
        # DSSProject.new_recipe(). Instantiate directly.
        from dku_cli.commands import recipe as recipe_module

        builder = recipe_module.FuzzyJoinRecipeCreator(recipe_name, proj)
        for ds in inputs:
            builder.with_input(ds)
        builder.with_existing_output(output_ds)
        builder.build()

        # Configure fuzzy join conditions in payload
        recipe_obj = proj.get_recipe(recipe_name)
        settings = recipe_obj.get_settings()
        payload = _get_recipe_payload(settings)

        joins = payload.get("joins", [])
        if not joins:
            joins = [{"table1": 0, "table2": 1, "on": []}]
            payload["joins"] = joins

        fj = joins[0]
        fj["fuzzyJoinMethod"] = m
        fj["fuzzyJoinMaxDistance"] = max_distance

        # Configure fuzzy key conditions
        if fuzzy_key:
            conditions = fj.setdefault("on", [])
            for key_spec in fuzzy_key:
                if "=" in key_spec:
                    col1, col2 = key_spec.split("=", 1)
                else:
                    col1 = col2 = key_spec
                conditions.append(
                    {
                        "column1": {"name": col1.strip(), "table": 0},
                        "column2": {"name": col2.strip(), "table": 1},
                        "type": "FUZZY",
                    }
                )

        # Configure exact-match key conditions
        if join_key:
            conditions = fj.setdefault("on", [])
            for key_spec in join_key:
                if "=" in key_spec:
                    col1, col2 = key_spec.split("=", 1)
                else:
                    col1 = col2 = key_spec
                conditions.append(
                    {
                        "column1": {"name": col1.strip(), "table": 0},
                        "column2": {"name": col2.strip(), "table": 1},
                        "type": "EQ",
                    }
                )

        settings.save()
        _auto_apply_schema(proj, recipe_name)
        success(f"Created fuzzy join recipe '{recipe_name}' ({m}) in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
