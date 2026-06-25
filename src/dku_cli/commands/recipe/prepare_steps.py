"""Prepare recipe step commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *
from dku_cli.enums import FilterAction, GeoDistanceUnitMiles, ReorderMode

# ---------------------------------------------------------------------------
# Prepare recipe step commands
# ---------------------------------------------------------------------------

# Processor types agents repeatedly guess that DO NOT exist as stock
# processors. DSS accepts them at add time and fails only at RUN time with a
# misleading "Type X was available in a plugin that is not installed" — so
# reject them at add time with the real alternative.
_WRONG_PROCESSOR_TYPES: dict[str, str] = {
    "AddId": (
        "There is no row-id processor in Prepare. Pre-bake the id at "
        "extraction, or use a Window recipe: create-window ... --compute "
        "'rowNumber::row_id'."
    ),
    "Enumerator": (
        "There is no row-counter processor in Prepare. Use a Window recipe: "
        "create-window ... --compute 'rowNumber::row_id'."
    ),
    "FilterOnFormula": (
        "Use FilterOnCustomFormula "
        '(params: {"expression": ..., "action": "KEEP_ROW"}), '
        "or the add-filter-rows shortcut."
    ),
    "FoldColumnsByName": (
        "That is a plugin processor. Use the stock MultiColumnFold "
        "(or the add-fold shortcut)."
    ),
}

# Stock processors the CLI knows about (curated from
# references/prepare-processors.md + the types this CLI emits). DSS has more;
# an unknown type only triggers an advisory warning, never a block.
_KNOWN_STOCK_PROCESSORS: frozenset[str] = frozenset(
    {
        "ArraySortProcessor",
        "ArrayUnfold",
        "BinnerProcessor",
        "CityLevelReverseGeocoder",
        "Coalesce",
        "ColumnCopier",
        "ColumnRenamer",
        "ColumnReorder",
        "ColumnSplitter",
        "ColumnsConcat",
        "ColumnsSelector",
        "ComputeNTile",
        "CreateColumnWithGREL",
        "DateComponentsExtractor",
        "DateDifference",
        "DateFormatter",
        "DateIncrement",
        "DateParser",
        "DateTruncate",
        "EnrichWithBuildContextProcessor",
        "ExtractNumbers",
        "FillColumn",
        "FillEmptyWithValue",
        "FilterOnBadType",
        "FilterOnCustomFormula",
        "FilterOnDate",
        "FilterOnNumericalRange",
        "FilterOnValue",
        "FindReplace",
        "FlagOnBadType",
        "FlagOnCustomFormula",
        "FlagOnDate",
        "FlagOnNumericalRange",
        "FlagOnValue",
        "GeoDistanceProcessor",
        "GeoIPResolver",
        "GeoPointCreator",
        "GeometryInfoExtractor",
        "JSONFlattener",
        "MemoryEquiJoiner",
        "MergeLongTailValues",
        "MinMaxProcessor",
        "MultiColumnByPrefixFold",
        "MultiColumnFold",
        "NumericalFormatConverter",
        "PythonUDF",
        "RegexpExtractor",
        "RemoveRowsOnEmpty",
        "RoundProcessor",
        "StringTransformer",
        "TextSimplifierProcessor",
        "UNIXTimestampParser",
        "Unfold",
        "UpDownFiller",
        "VisualIfRule",
        "ZipCodeGeocoder",
    }
)


def _validate_processor_type(step_type: str) -> None:
    """Validate a processor type at add/replace time.

    DSS happily saves a step with a nonexistent type; the failure surfaces
    only at RUN time as a misleading "Type X was available in a plugin that
    is not installed" (no plugin is involved — the type just doesn't exist).
    Known-wrong guesses die here with the real alternative; unknown types get
    an advisory warning (the curated list is not exhaustive and plugin
    processors are legitimate).
    """
    if step_type in _WRONG_PROCESSOR_TYPES:
        exit_with_error(
            f"'{step_type}' is not a stock Prepare processor.",
            details=[
                _WRONG_PROCESSOR_TYPES[step_type],
                "",
                "DSS would save this step and fail only at run time with the",
                'misleading error "Type was available in a plugin that is not',
                'installed".',
            ],
        )
    if step_type not in _KNOWN_STOCK_PROCESSORS:
        warn(
            f"'{step_type}' is not in the CLI's known stock-processor list. "
            "If it is not from an installed plugin, the recipe will fail at "
            'RUN time with a misleading "plugin that is not installed" '
            "error. Check the dataiku skill's references/prepare-processors.md "
            "for valid types (ignore this if the build succeeds)."
        )


def _normalize_raw_step(step_type: str, parsed_params):
    """Validate + normalize a raw processor step's params in place.

    Shared by `add-step` and `apply-spec`'s raw (`type`+`params`) escape so the
    full guard set — inCol/outCol traps, param-key typos, GREL lint, DateParser
    outType normalization, SINGLE_COLUMN multi-column warning — lives in one
    place. May call `exit_with_error` (illegal shapes) or `warn` (silent
    footguns). Returns the possibly-mutated params.
    """
    # Catch the "Empty column name" trap: several date processors use
    # inCol/outCol, but agents often pass column/outputColumn from older
    # docs. DSS returns a misleading "Empty column name" error that makes
    # agents assume the processor doesn't exist.
    _INCOL_PROCESSORS = {
        "DateFormatter": ("format", "yyyy-MM-dd HH:mm:ss"),
        "DateTruncate": ("datePart", "MONTH"),
        "UNIXTimestampParser": ("milliseconds", False),
    }
    if step_type in _INCOL_PROCESSORS and isinstance(parsed_params, dict):
        # Two wrong shapes both yield DSS's "Empty column name":
        #   (a) column/outputColumn (from older docs), and
        #   (b) appliesTo + columns[] — the style that DateParser,
        #       DateComponentsExtractor, StringTransformer DO use, so
        #       agents copy it onto sibling date processors that don't.
        has_wrong = any(
            k in parsed_params
            for k in ("column", "outputColumn", "columns", "appliesTo")
        )
        has_right = "inCol" in parsed_params
        if has_wrong and not has_right:
            extra_key, extra_val = _INCOL_PROCESSORS[step_type]
            wrong_cols = parsed_params.get("columns")
            src_col = parsed_params.get("column") or (
                wrong_cols[0] if isinstance(wrong_cols, list) and wrong_cols else "COL"
            )
            example = {
                "inCol": src_col,
                "outCol": parsed_params.get("outputColumn", "NEW_COL"),
                extra_key: extra_val,
            }
            exit_with_error(
                f"Processor '{step_type}' expects 'inCol'/'outCol' (not 'column'/'outputColumn').",
                details=[
                    "DSS returns a misleading 'Empty column name' error when these field names are wrong.",
                    f"Correct params: {json.dumps(example)}",
                    "See: dataiku skill's references/prepare-processors.md",
                ],
            )

    # Catch param-key typos that DSS silently accepts (unknown keys are
    # ignored by the processor, leaving the step a no-op). The recipe
    # builds and runs "successfully", but the column appears in the
    # output schema as empty — surfaces only when real data arrives.
    _PARAM_KEY_TYPOS: dict[str, dict[str, str]] = {
        # add-formula --expr maps to params.expression; agents passing
        # raw --params often write "expr" instead of "expression".
        "CreateColumnWithGREL": {"expr": "expression"},
    }
    if step_type in _PARAM_KEY_TYPOS and isinstance(parsed_params, dict):
        for wrong, right in _PARAM_KEY_TYPOS[step_type].items():
            if wrong in parsed_params and right not in parsed_params:
                exit_with_error(
                    f"Processor '{step_type}' expects '{right}', got '{wrong}'.",
                    details=[
                        "DSS silently ignores unknown processor params — "
                        "the formula never executes but the recipe runs successfully "
                        "and the output schema gains an empty column.",
                        f"Fix: rename '{wrong}' to '{right}' in --params, or use the "
                        "shortcut 'add-formula --expr ... --column ...'.",
                    ],
                )

    if step_type == "CreateColumnWithGREL" and isinstance(parsed_params, dict):
        expr = parsed_params.get("expression")
        if isinstance(expr, str):
            _warn_grel_aliases(expr)
            _warn_grel_date_units(expr)

    # DateParser outType must be an OBJECT ({"name": "...", "type": "..."}).
    # The string shorthand ("dateonly") saves fine but the build fails with
    # 'Expected BEGIN_OBJECT but was STRING at path $.outType'. Several docs
    # suggested the string form, so agents hit this repeatedly — normalize
    # it client-side and warn rather than letting the build blow up later.
    if step_type == "DateParser" and isinstance(parsed_params.get("outType"), str):
        out_type_str = parsed_params["outType"]
        parsed_params["outType"] = {"name": "out", "type": out_type_str}
        warn(
            f"DateParser 'outType' must be an object, not the string "
            f"{out_type_str!r} (the build fails with 'Expected BEGIN_OBJECT "
            f"but was STRING'). Normalized to "
            f'{{"name": "out", "type": "{out_type_str}"}}.'
        )

    # Warn about DateParser without outCol (silently produces all nulls)
    if step_type == "DateParser" and "outCol" not in parsed_params:
        warn(
            "DateParser without 'outCol' silently produces all nulls. "
            "Add outCol to write to a new column."
        )

    # Warn when SINGLE_COLUMN is paired with a multi-column list. DSS
    # silently applies the step to only the FIRST listed column — e.g.
    # ColumnsSelector keep:true drops every listed column but the first,
    # with no error. COLUMNS is the multi-column mode.
    if isinstance(parsed_params, dict):
        applies_to = parsed_params.get("appliesTo")
        cols = parsed_params.get("columns")
        if applies_to == "SINGLE_COLUMN" and isinstance(cols, list) and len(cols) > 1:
            warn(
                f"'{step_type}' has appliesTo='SINGLE_COLUMN' but lists "
                f"{len(cols)} columns — DSS silently applies it to only "
                f"'{cols[0]}' (the rest are ignored, no error). "
                "Use appliesTo='COLUMNS' to apply to all listed columns."
            )

    return parsed_params


def _step_target(step: dict) -> str:
    """Extract a short 'target' summary from step params for table display."""
    params = step.get("params", {})
    # Try common param keys in priority order
    for key in ("expression", "column", "columns", "renamings"):
        val = params.get(key)
        if val is not None:
            s = str(val)
            return s[:40] + ("…" if len(s) > 40 else "")
    return ""


def _prepare_known_columns(proj, settings) -> set[str] | None:
    """Best-effort set of column names visible at this point in a prepare recipe.

    Returns None when validation should be skipped — no/multiple inputs, or the
    schema can't be read. False negatives are acceptable; the caller emits a
    warning, never blocks.
    """
    try:
        refs = settings.get_flat_input_refs()
        if len(refs) != 1:
            return None
        ref = refs[0]
        ds_name = ref.split(".", 1)[1] if "." in ref else ref
        sch = proj.get_dataset(ds_name).get_schema()
        cols = sch.get("columns", []) if isinstance(sch, dict) else []
        known: set[str] = {c["name"] for c in cols if c.get("name")}
    except Exception:
        return None

    # Replay prior prepare steps to track simple add/rename/delete effects.
    # Unknown step types fall through — we err on the side of "still known"
    # by not removing anything we can't reason about.
    payload = _get_recipe_payload(settings)
    for step in payload.get("steps", []):
        if step.get("disabled"):
            continue
        _replay_step_on_known(known, step.get("type", ""), step.get("params") or {})
    return known


def _replay_step_on_known(known: set[str], stype: str, params: dict) -> None:
    """Mutate `known` to reflect the simple add/rename/delete effect of one step.

    Shared by `_prepare_known_columns` (replaying saved steps) and `apply-spec`
    (evolving the column set across a batch so a step that references a column
    an earlier batch step created is not falsely flagged as unknown).
    """
    if stype == "ColumnRenamer":
        for r in params.get("renamings", []) or []:
            src = r.get("from")
            dst = r.get("to")
            if src in known:
                known.discard(src)
            if dst:
                known.add(dst)
    elif stype == "CreateColumnWithGREL":
        col = params.get("column")
        if col:
            known.add(col)
    elif stype == "FillEmptyWithValue":
        for c in params.get("columns") or []:
            known.add(c)
    elif stype == "ColumnsSelector" and params.get("keep") is False:
        for c in params.get("columns") or []:
            known.discard(c)


_GREL_DATE_UNITS = {
    "years",
    "months",
    "weeks",
    "days",
    "hours",
    "minutes",
    "seconds",
    "milliseconds",
    "dayOfWeek",
    "weekDay",
    "weekOfYear",
}


def _warn_grel_date_units(formula: str) -> None:
    """Warn when a GREL `diff(…)`, `inc(…)`, `datePart(…)`, or `trunc(…)`
    call uses a non-canonical unit literal (e.g. ``"year"`` instead of
    ``"years"``).

    DSS swallows bad unit strings — `inc(now(), -5, "year")` matches no rows
    instead of erroring — so a static regex catch saves a silent
    zero-rows-out build. Best-effort; never blocks.
    """
    import re

    # Match `<fn>(... , "unit")`. Lazy `.*?` lets the regex skip past nested
    # calls like `inc(now(), -5, "year")` to find the unit literal that
    # precedes the function's closing paren.
    pattern = re.compile(
        r'\b(diff|inc|datePart|trunc)\s*\(.*?,\s*"([A-Za-z]+)"\s*\)',
        re.DOTALL,
    )
    for fn, unit in pattern.findall(formula):
        if unit in _GREL_DATE_UNITS:
            continue
        # Suggest the plural form if a singular was passed
        suggestion = unit + "s" if unit + "s" in _GREL_DATE_UNITS else None
        hint = f' Did you mean "{suggestion}"?' if suggestion else ""
        warn(
            f'GREL `{fn}(…, "{unit}")` uses an unrecognized unit literal.{hint} '
            f"Valid units: {', '.join(sorted(_GREL_DATE_UNITS))}. "
            "DSS silently treats bad units as no-match, so a build with this "
            "step may produce 0 rows with no error."
        )


def _warn_grel_aliases(formula: str) -> None:
    """Warn on common non-GREL function names before DSS rejects the build."""
    import re

    aliases = {
        "toLong": "toNumber",
        "toInt": "toNumber",
        "toInteger": "toNumber",
    }
    found = []
    for wrong, right in aliases.items():
        if re.search(rf"\b{wrong}\s*\(", formula):
            found.append(f"{wrong}() -> {right}()")
    if found:
        warn(
            "Unknown GREL numeric cast name(s): "
            + ", ".join(found)
            + ". Dataiku GREL uses toNumber(value) for numeric casts."
        )


def _warn_expression_status_errors(recipe, recipe_name: str, project_key: str) -> None:
    """Best-effort post-save lint for steps that carry a GREL expression.

    Runs the same DSS status check as `recipe lint-formula` so a bad
    expression (e.g. `substr` — GREL only has `substring`) surfaces at
    submit time, not two commands later at apply-schema/build (where the
    usual recovery is an expensive delete-recreate of the whole recipe).
    Never blocks: the step is already saved, and status errors can also
    come from elsewhere in the recipe.
    """
    try:
        messages = recipe.get_status().get_status_messages()
        errors = [m for m in messages if m.get("severity") in ("ERROR", "FATAL")]
    except Exception:
        return
    if not errors:
        return
    warn(f"Step saved, but the recipe status check now reports {len(errors)} error(s):")
    for e in errors[:5]:
        warn(f"  [{e.get('code', '?')}] {e.get('title', '')}: {e.get('message', '')}")
    info(
        f"Fix the expression (edit or remove-step), then re-check: "
        f"dku recipe lint-formula {recipe_name} -P {project_key}"
    )


def _warn_unknown_columns(
    cols: list[str],
    known: set[str] | None,
    *,
    label: str,
    recipe_name: str,
) -> None:
    """Emit a non-blocking warning naming each `cols` value not in `known`.

    No-op when `known` is None (validation unavailable).
    """
    if known is None:
        return
    import difflib

    known_by_lower = {k.lower(): k for k in known}
    for col in cols:
        if not col or col in known:
            continue
        # Case-insensitive match takes precedence — the FREQUENCE_POINTS=0
        # bug was specifically NB_COMMANDES vs nb_commandes, which is too
        # far apart for difflib's default token-similarity scoring.
        suggestions: list[str] = []
        ci_match = known_by_lower.get(col.lower())
        if ci_match:
            suggestions.append(ci_match)
        for s in difflib.get_close_matches(col, known, n=3, cutoff=0.6):
            if s not in suggestions:
                suggestions.append(s)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        warn(
            f"{label} '{col}' not found in input schema of '{recipe_name}'.{hint} "
            "Column names are case-sensitive — this step may silently create a new "
            "column or no-op."
        )


@app.command("list-steps")
def list_steps(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List steps in a prepare recipe.

    Shows each step's index, processor type, name, disabled status, and target column/expression.
    Use --format json for full step parameters.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        if output == "json":
            render_raw(steps, output_format="json")
            return

        if not steps:
            info(
                f"No steps in recipe '{recipe_name}'. Add with: dku recipe add-step {recipe_name} --type <TYPE> --params '<JSON>' -P {project_key}"
            )
            return

        rows = []
        for i, step in enumerate(steps):
            rows.append(
                {
                    "index": str(i),
                    "type": step.get("type", ""),
                    "name": step.get("name", ""),
                    "disabled": str(step.get("disabled", False)),
                    "target": _step_target(step),
                }
            )
        render(
            rows,
            ["index", "type", "name", "disabled", "target"],
            output_format=output,
            title=f"Steps: {recipe_name}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-step")
def add_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    step_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Processor type (e.g. CreateColumnWithGREL, ColumnRenamer, FillEmptyWithValue, ColumnsSelector, FindReplace, FilterOnValue, RemoveRowsOnEmpty, StringTransformer, ColumnCopier, PythonUDF). ~95 types available.",
    ),
    params: str = typer.Option(
        ..., "--params", help="Step params: JSON string, @file.json, or '-' for stdin"
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    name: str | None = typer.Option(None, "--name", help="Optional step display name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a processor step to a prepare recipe (generic — any of ~95 processor types).

    For common operations, prefer named shortcuts: add-formula, add-rename,
    add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace.
    Use add-step for advanced or unusual processors.
    """
    project_key = resolve_project(project)
    _validate_processor_type(step_type)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        parsed_params = read_json_input(params)
        parsed_params = _normalize_raw_step(step_type, parsed_params)

        step_dict: dict = {
            "metaType": "PROCESSOR",
            "type": step_type,
            "params": parsed_params,
        }
        if name:
            step_dict["name"] = name

        if at is not None:
            if at < 0 or at > len(steps):
                exit_with_error(
                    f"--at {at} out of range. Valid: 0–{len(steps)}.",
                )
            steps.insert(at, step_dict)
            idx = at
        else:
            steps.append(step_dict)
            idx = len(steps) - 1

        settings.save()
        success(f"Added {step_type} step to '{recipe_name}' at index {idx}")
        if isinstance(parsed_params, dict) and "expression" in parsed_params:
            _warn_expression_status_errors(_recipe, recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-step")
def remove_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: list[int] = typer.Option(
        ...,
        "--index",
        help="Step index to remove (0-based, repeatable). Use 'list-steps' to see indices.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove one or more steps from a prepare recipe by index.

    When removing multiple steps, they are removed in descending order
    internally to avoid index shifting.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="recipe.remove_step",
        subject=f"step(s) {sorted(index)} from prepare recipe '{recipe_name}' in {project_key}",
        yes=yes,
        prompt=f"Remove step(s) {sorted(index)} from prepare recipe '{recipe_name}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        # Validate all indices before removing any
        for idx in index:
            _validate_step_index(steps, idx, recipe_name)

        # Remove in descending order to avoid shifting
        for idx in sorted(set(index), reverse=True):
            steps.pop(idx)

        settings.save()
        removed = ", ".join(str(i) for i in sorted(index))
        success(f"Removed step(s) [{removed}] from '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("replace-step")
def replace_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: int = typer.Option(
        ...,
        "--index",
        help="Step index to replace (0-based). Use 'list-steps' to see indices.",
    ),
    step_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Replacement processor type (e.g. CreateColumnWithGREL). Use with --params.",
    ),
    params: str | None = typer.Option(
        None,
        "--params",
        help="Replacement step params: JSON string, @file.json, or '-' for stdin. Pair with --type.",
    ),
    name: str | None = typer.Option(
        None, "--name", help="Optional step display name (used with --type)"
    ),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Full replacement step JSON: literal, @file.json, or '-' for stdin. Overrides --type/--params/--name.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Deprecated — replace-step is a JSON edit and is no longer guarded. Flag accepted but ignored.",
        hidden=True,
    ),
) -> None:
    """Replace one prepare-recipe step at the given index in a single operation.

    Equivalent to `remove-step --index N` then `add-step --at N` but atomic —
    no index drift between calls. Use this when iterating on a single
    processor's params without re-shuffling the rest of the pipeline.

    Treated as a WRITE (not DELETE) — replace-step rewrites the step JSON; it
    does not touch dataset data, so it is no more destructive than add-step.
    No --yes is required.

    Provide either --type + --params (and optionally --name), OR --definition
    with the full step JSON.

    Example:
      dku recipe replace-step my_prep --index 2 \\
        --type CreateColumnWithGREL \\
        --params '{"column":"price_log","expression":"log(price)"}' -P PROJ
    """
    del yes  # legacy flag — see docstring

    project_key = resolve_project(project)
    if step_type:
        _validate_processor_type(step_type)
    if not definition and not (step_type and params):
        exit_with_error(
            "Provide either --definition or both --type and --params.",
            details=[
                'Example: dku recipe replace-step my_prep --index 2 --type ColumnRenamer --params \'{"renamings":[{"from":"a","to":"b"}]}\' -P PROJ',
                "Example: dku recipe replace-step my_prep --index 2 --definition @step.json -P PROJ",
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        _validate_step_index(steps, index, recipe_name)

        if definition:
            new_step = read_json_input(definition)
            if not isinstance(new_step, dict):
                exit_with_error(
                    "--definition must be a JSON object describing one step.",
                )
            # Default the metaType so callers don't have to remember it
            new_step.setdefault("metaType", "PROCESSOR")
            display_type = new_step.get("type", "<unknown>")
        else:
            parsed_params = read_json_input(params)
            new_step = {
                "metaType": "PROCESSOR",
                "type": step_type,
                "params": parsed_params,
            }
            if name:
                new_step["name"] = name
            display_type = step_type

        steps[index] = new_step
        settings.save()
        success(
            f"Replaced step at index {index} in '{recipe_name}' with {display_type}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-step")
def get_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: int = typer.Option(..., "--index", help="Step index (0-based)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get full details of a single prepare recipe step.

    Returns the complete step JSON including all parameters.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        _validate_step_index(steps, index, recipe_name)
        render_raw(steps[index], output_format=output)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("disable-step")
def disable_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: list[int] = typer.Option(
        ..., "--index", help="Step index to disable (0-based, repeatable)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Disable steps in a prepare recipe (skipped during execution).

    Disabled steps remain in the recipe but are not executed when the recipe runs.
    Use 'enable-step' to re-enable. Useful for debugging data pipelines step-by-step.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        for idx in index:
            _validate_step_index(steps, idx, recipe_name)
            steps[idx]["disabled"] = True
        settings.save()
        indices = ", ".join(str(i) for i in index)
        success(f"Disabled step(s) [{indices}] in '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("enable-step")
def enable_step(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    index: list[int] = typer.Option(
        ..., "--index", help="Step index to enable (0-based, repeatable)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Enable previously disabled steps in a prepare recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        for idx in index:
            _validate_step_index(steps, idx, recipe_name)
            steps[idx]["disabled"] = False
        settings.save()
        indices = ", ".join(str(i) for i in index)
        success(f"Enabled step(s) [{indices}] in '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Prepare recipe step shortcuts (named wrappers for common processors)
# ---------------------------------------------------------------------------


def _add_prepare_step(
    ctx,
    recipe_name: str,
    project: str | None,
    step_type: str,
    params: dict,
    *,
    validate_cols: list[tuple[str, list[str]]] | None = None,
    at: int | None = None,
) -> None:
    """Shared logic for all named step shortcuts.

    `validate_cols` is a list of (label, columns) pairs; each column that
    isn't visible in the recipe's input schema (after replaying prior steps)
    gets a warning with "did you mean" suggestions. Best-effort — never
    blocks the save.

    `at` mirrors `add-step --at`: insert at a 0-based index instead of
    appending. Mid-pipeline inserts matter when a later step must run BEFORE
    an existing one (e.g. a fill-empty sentinel before a fold, or a formula
    before a select that drops its inputs).
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        if validate_cols:
            known = _prepare_known_columns(proj, settings)
            for label, cols in validate_cols:
                _warn_unknown_columns(cols, known, label=label, recipe_name=recipe_name)
        steps = _ensure_steps_array(settings)
        step_dict = {"metaType": "PROCESSOR", "type": step_type, "params": params}
        if at is not None:
            if at < 0 or at > len(steps):
                exit_with_error(
                    f"--at {at} out of range. Valid: 0–{len(steps)}.",
                )
            steps.insert(at, step_dict)
            idx = at
        else:
            steps.append(step_dict)
            idx = len(steps) - 1
        settings.save()
        success(f"Added {step_type} step to '{recipe_name}' (index {idx})")
        if "expression" in params:
            _warn_expression_status_errors(_recipe, recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# Pure param builders — single source of truth for each shortcut's step shape.
# Both the named `add-*` commands and `apply-spec`'s op DSL route through these,
# so a payload shape lives in exactly one place. Each returns
# (step_type, params, validate_cols) where validate_cols is a list of
# (label, columns) pairs fed to the input-schema column check.


def _formula_step(expr: str, column: str):
    _warn_grel_aliases(expr)
    _warn_grel_date_units(expr)
    return "CreateColumnWithGREL", {"expression": expr, "column": column}, []


def _rename_step(renamings: list[dict]):
    sources = [r["from"] for r in renamings if r.get("from")]
    return "ColumnRenamer", {"renamings": renamings}, [("--from", sources)]


def _filter_rows_step(*, column=None, values=None, formula=None, action="KEEP_ROW"):
    if formula:
        _warn_grel_date_units(formula)
        return "FilterOnCustomFormula", {"expression": formula, "action": action}, []
    return (
        "FilterOnValue",
        {
            "appliesTo": "SINGLE_COLUMN",
            "columns": [column],
            "values": values,
            "action": action,
            "matchingMode": "FULL_STRING",
            "normalizationMode": "EXACT",
            "booleanMode": "AND",
        },
        [("--column", [column])],
    )


def _fill_empty_step(cols: list[str], value: str):
    applies = "SINGLE_COLUMN" if len(cols) == 1 else "COLUMNS"
    return (
        "FillEmptyWithValue",
        {"appliesTo": applies, "columns": cols, "value": value},
        [("--column", cols)],
    )


def _delete_columns_step(cols: list[str]):
    return (
        "ColumnsSelector",
        {"appliesTo": "COLUMNS", "columns": cols, "keep": False},
        [("--columns", cols)],
    )


def _reorder_step(cols: list[str], mode: str, anchor: str | None = None):
    applies = "SINGLE_COLUMN" if len(cols) == 1 else "COLUMNS"
    params: dict = {"appliesTo": applies, "columns": cols, "reorderAction": mode}
    if anchor:
        params["referenceColumn"] = anchor
    return "ColumnReorder", params, []


def _find_replace_step(
    column: str, find: str, replace: str, matching="SUBSTRING", ignore_case=False
):
    return (
        "FindReplace",
        {
            "appliesTo": "SINGLE_COLUMN",
            "columns": [column],
            "output": "",
            "mapping": [{"from": find, "to": replace}],
            "matching": matching,
            "normalization": "LOWERCASE" if ignore_case else "EXACT",
        },
        [],
    )


def _fold_step(
    columns=None, pattern=None, key_column="fold_key", value_column="fold_value"
):
    if columns:
        return (
            "MultiColumnFold",
            {
                "columns": columns,
                "foldNameColumn": key_column,
                "foldValueColumn": value_column,
                "foldRemoveFoldedColumns": True,
            },
            [],
        )
    return (
        "MultiColumnByPrefixFold",
        {
            "columnNamePattern": pattern,
            "columnNameColumn": key_column,
            "columnContentColumn": value_column,
            "foldRemoveFoldedColumns": True,
        },
        [],
    )


def _geopoint_step(lat_column: str, lon_column: str, output_column="geopoint"):
    return (
        "GeoPointCreator",
        {
            "lat_column": lat_column,
            "lon_column": lon_column,
            "out_column": output_column,
        },
        [],
    )


def _geodistance_step(
    from_column: str, to_column: str, output_column="geo_distance", unit="MILES"
):
    return (
        "GeoDistanceProcessor",
        {
            "input1": from_column,
            "input2": to_column,
            "output": output_column,
            "outputUnit": unit,
            "compareTo": "COLUMN",
        },
        [],
    )


@app.command("add-formula")
def add_formula(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    expr: str = typer.Option(
        ...,
        "--expr",
        "--expression",
        "-e",
        help="GREL expression (e.g. 'upper(city)', 'price * 1.1', 'if(age>=18,\"adult\",\"minor\")')",
    ),
    column: str = typer.Option(
        ..., "--column", "-c", help="Output column name for the formula result"
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a formula step (GREL expression) to create or transform a column.

    Use instead of Python for computed columns, string transforms, and conditionals.
    Formula reference: skills/dataiku/references/formulas.md
    """
    step_type, params, vcols = _formula_step(expr, column)
    _add_prepare_step(
        ctx, recipe_name, project, step_type, params, validate_cols=vcols, at=at
    )


@app.command("add-rename")
def add_rename(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    rename_from: str = typer.Option(
        None, "--from", help="Column to rename (use with --to)"
    ),
    rename_to: str = typer.Option(
        None, "--to", help="New column name (use with --from)"
    ),
    mappings: str = typer.Option(
        None,
        "--mappings",
        help=(
            'Bulk renames: \'{"old1":"new1","old2":"new2"}\' (JSON or @file.json) '
            "or shorthand 'old1:new1,old2:new2' (no JSON needed; names must not "
            "contain ':' or ',')"
        ),
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a column rename step. Use --from/--to for single, --mappings for bulk.

    Use instead of df.rename() in Python.
    """
    if mappings and (rename_from or rename_to):
        exit_with_error(
            "Use --from/--to OR --mappings, not both.",
        )
    if mappings:
        # Accept the 'old:new,old2:new2' shorthand the CLI trains elsewhere
        # (--sort-col Total:desc, --agg col:sum). Agents guess it here too;
        # previously it died with a raw 'Invalid JSON ... Extra data'.
        stripped = mappings.strip()
        if not stripped.startswith(("{", "@", "-")):
            pairs = [p for p in stripped.split(",") if p.strip()]
            if pairs and all(p.count(":") == 1 for p in pairs):
                parsed = dict(
                    (k.strip(), v.strip()) for k, v in (p.split(":") for p in pairs)
                )
            else:
                exit_with_error(
                    f"Could not parse --mappings {mappings!r}.",
                    details=[
                        "Accepted forms:",
                        "  shorthand: --mappings 'old1:new1,old2:new2'",
                        '  JSON:      --mappings \'{"old1":"new1","old2":"new2"}\' (or @file.json)',
                        "For a single rename use --from OLD --to NEW.",
                        "Names containing ':' or ',' require the JSON form.",
                    ],
                )
        else:
            try:
                parsed = read_json_input(mappings)
            except Exception:
                exit_with_error(
                    f"--mappings is not valid JSON: {mappings!r}",
                    details=[
                        'Expected: \'{"old1":"new1","old2":"new2"}\' (or @file.json),',
                        "or the shorthand 'old1:new1,old2:new2'.",
                        "For a single rename use --from OLD --to NEW.",
                    ],
                )
        if not isinstance(parsed, dict):
            exit_with_error(
                '--mappings must be a JSON object: \'{"old":"new"}\' '
                "or shorthand 'old:new,old2:new2'",
            )
        renamings = [{"from": k, "to": v} for k, v in parsed.items()]
    elif rename_from and rename_to:
        renamings = [{"from": rename_from, "to": rename_to}]
    else:
        exit_with_error(
            "Provide --from and --to for a single rename, or --mappings for bulk.",
            details=[
                "Single: dku recipe add-rename RECIPE --from old_name --to new_name -P PROJ",
                'Bulk: dku recipe add-rename RECIPE --mappings \'{"old1":"new1","old2":"new2"}\' -P PROJ',
            ],
        )
    step_type, params, vcols = _rename_step(renamings)
    _add_prepare_step(
        ctx, recipe_name, project, step_type, params, validate_cols=vcols, at=at
    )


@app.command("add-filter-rows")
def add_filter_rows(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: str = typer.Option(
        None, "--column", "-c", help="Column to filter on (value-based)"
    ),
    values: str = typer.Option(
        None, "--values", help="Comma-separated values to match"
    ),
    formula: str = typer.Option(
        None,
        "--formula",
        "--expr",
        "--expression",
        help="GREL formula for expression-based filtering (e.g. 'price > 100')",
    ),
    action: FilterAction = typer.Option(
        FilterAction.KEEP_ROW,
        "--action",
        case_sensitive=False,
        help="KEEP_ROW (keep matching, default — matches create-filter) or REMOVE_ROW (drop matching)",
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a filter step to remove or keep rows matching conditions.

    Use --column + --values for value-based, or --formula for expression-based.
    Use instead of df[df.col > x] in Python.
    """
    if formula and (column or values):
        exit_with_error("Use --column/--values OR --formula, not both.")
    # --action is a click.Choice (FilterAction) — an invalid value dies at parse
    # time with the valid set shown, so no inline check is needed here.
    action_upper = action.upper()
    if formula:
        step_type, params, vcols = _filter_rows_step(
            formula=formula, action=action_upper
        )
        _add_prepare_step(
            ctx, recipe_name, project, step_type, params, validate_cols=vcols, at=at
        )
    elif column and values:
        step_type, params, vcols = _filter_rows_step(
            column=column,
            values=[v.strip() for v in values.split(",")],
            action=action_upper,
        )
        _add_prepare_step(
            ctx, recipe_name, project, step_type, params, validate_cols=vcols, at=at
        )
    else:
        exit_with_error(
            "Provide --column + --values, or --formula.",
            details=[
                "Value-based: dku recipe add-filter-rows RECIPE --column status --values 'active,pending' --action KEEP_ROW -P PROJ",
                "Formula: dku recipe add-filter-rows RECIPE --formula 'price > 100' --action REMOVE_ROW -P PROJ",
            ],
        )


@app.command("add-fill-empty")
def add_fill_empty(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: list[str] = typer.Option(
        None,
        "--column",
        "-c",
        help="Column to fill (repeatable: '-c HBO -c Netflix' produces ONE step covering both with the same --value).",
    ),
    columns: str = typer.Option(
        None,
        "--columns",
        help="Comma-separated columns (alternative to repeating --column). Same --value applied to all.",
    ),
    value: str = typer.Option(..., "--value", help="Value to fill empty cells with"),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a step that fills empty/null values in one or more columns with a fixed value.

    Use instead of df.fillna() in Python. For SAS-style 'if X=. then X=0' defaulting
    over many columns, pass --column repeatedly OR a single --columns CSV — both produce
    ONE step covering all columns with the same fill value.
    """
    cols: list[str] = list(column or [])
    if columns:
        cols.extend(c.strip() for c in columns.split(",") if c.strip())
    if not cols:
        exit_with_error(
            "Provide at least one column via --column (repeatable) or --columns CSV.",
        )

    step_type, params, vcols = _fill_empty_step(cols, value)
    _add_prepare_step(
        ctx, recipe_name, project, step_type, params, validate_cols=vcols, at=at
    )


@app.command("add-delete-columns")
def add_delete_columns(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    columns: str = typer.Option(
        ..., "--columns", help="Comma-separated column names to delete"
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a step to delete (drop) columns from the dataset.

    Use instead of df.drop(columns=[...]) in Python.
    """
    cols_list = [c.strip() for c in columns.split(",")]
    step_type, params, vcols = _delete_columns_step(cols_list)
    _add_prepare_step(
        ctx, recipe_name, project, step_type, params, validate_cols=vcols, at=at
    )


@app.command("add-reorder")
def add_reorder(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: list[str] = typer.Option(
        None,
        "--column",
        "-c",
        help="Column(s) to move. Repeatable for multi-column moves.",
    ),
    columns: str = typer.Option(
        None,
        "--columns",
        help="Comma-separated columns (alternative to repeating --column).",
    ),
    mode: ReorderMode = typer.Option(
        ...,
        "--mode",
        "-m",
        case_sensitive=False,
        help="Reorder mode: AT_THE_BEGINNING | AT_THE_END | BEFORE_COLUMN | AFTER_COLUMN.",
    ),
    anchor: str | None = typer.Option(
        None,
        "--anchor",
        "-a",
        help="Reference column for BEFORE_COLUMN / AFTER_COLUMN modes.",
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a ColumnReorder step (auto-fills `appliesTo`).

    Closes the recurring footgun: the generic `add-step --type ColumnReorder`
    omits `appliesTo`, which DSS silently accepts but renders as broken.
    Multi-column moves work correctly when `appliesTo: COLUMNS` is set.

    Examples:
      Move one column to the start:
        dku recipe add-reorder my_prep -c price --mode AT_THE_BEGINNING -P PROJ

      Move multiple columns before an anchor:
        dku recipe add-reorder my_prep -c a -c b --mode BEFORE_COLUMN \\
          --anchor c -P PROJ
    """
    mode_upper = mode.value
    if mode_upper in {"BEFORE_COLUMN", "AFTER_COLUMN"} and not anchor:
        exit_with_error(
            f"--mode {mode_upper} requires --anchor (the reference column).",
            details=[
                "AT_THE_BEGINNING / AT_THE_END do not need --anchor.",
                "BEFORE_COLUMN / AFTER_COLUMN do.",
            ],
        )

    cols: list[str] = list(column or [])
    if columns:
        cols.extend(c.strip() for c in columns.split(",") if c.strip())
    if not cols:
        exit_with_error(
            "Provide at least one column via --column (repeatable) or --columns CSV.",
        )

    step_type, params, _vcols = _reorder_step(cols, mode_upper, anchor)
    _add_prepare_step(ctx, recipe_name, project, step_type, params, at=at)


@app.command("add-find-replace")
def add_find_replace(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    column: str = typer.Option(..., "--column", "-c", help="Column to search in"),
    find: str = typer.Option(..., "--find", help="Value to find"),
    replace: str = typer.Option(..., "--replace", help="Replacement value"),
    matching: str = typer.Option(
        "SUBSTRING",
        "--matching",
        help="Match mode: SUBSTRING (default), FULL_STRING (exact cell match), or PATTERN (regex).",
    ),
    ignore_case: bool = typer.Option(
        False,
        "--ignore-case",
        "-i",
        help="Match case-insensitively (normalization: LOWERCASE — 'europe', "
        "'EUROPE' and 'Europe' all match --find 'Europe').",
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a find-and-replace step on a column."""
    step_type, params, _vcols = _find_replace_step(
        column, find, replace, matching.upper(), ignore_case
    )
    _add_prepare_step(ctx, recipe_name, project, step_type, params, at=at)


@app.command("add-fold")
def add_fold(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    columns: str = typer.Option(
        None,
        "--columns",
        help="Comma-separated column names to fold (wide→long). Mutually exclusive with --pattern.",
    ),
    pattern: str = typer.Option(
        None,
        "--pattern",
        help="Regex pattern matching column names to fold (e.g. '.*-25'). Mutually exclusive with --columns.",
    ),
    key_column: str = typer.Option(
        "fold_key", "--key-column", help="Output column for original column names"
    ),
    value_column: str = typer.Option(
        "fold_value", "--value-column", help="Output column for cell values"
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Fold (unpivot) multiple columns into key-value rows (wide→long).

    Use instead of pd.melt() or pd.wide_to_long() in Python.
    Specify columns explicitly with --columns, or match by regex with --pattern.

    Example: dku recipe add-fold prep1 --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ
    """
    if columns and pattern:
        exit_with_error(
            "Use --columns OR --pattern, not both.",
            details=["--columns: explicit list. --pattern: regex match."],
        )
    if not columns and not pattern:
        exit_with_error(
            "Specify --columns or --pattern to select columns to fold.",
            details=[
                'Example: dku recipe add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ',
                'Example: dku recipe add-fold RECIPE --pattern ".*-25" --key-column month --value-column sales -P PROJ',
            ],
        )
    if columns:
        col_list = [c.strip() for c in columns.split(",")]
        step_type, params, _vcols = _fold_step(
            columns=col_list, key_column=key_column, value_column=value_column
        )
    else:
        step_type, params, _vcols = _fold_step(
            pattern=pattern, key_column=key_column, value_column=value_column
        )
    _add_prepare_step(ctx, recipe_name, project, step_type, params, at=at)


@app.command("add-geopoint")
def add_geopoint(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    lat_column: str = typer.Option(
        ..., "--lat-column", "--lat", help="Latitude column name"
    ),
    lon_column: str = typer.Option(
        ..., "--lon-column", "--lon", help="Longitude column name"
    ),
    output_column: str = typer.Option(
        "geopoint", "--output-column", "-c", help="Output geopoint column name"
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a geopoint column from latitude/longitude columns.

    Use instead of manually formatting WKT in Python. Output is a WKT POINT
    in EPSG:4326 (WGS84) that can be used in geo join recipes and map charts.

    Example: dku recipe add-geopoint prep1 --lat-column lat --lon-column lon -P PROJ
    """
    step_type, params, _vcols = _geopoint_step(lat_column, lon_column, output_column)
    _add_prepare_step(ctx, recipe_name, project, step_type, params, at=at)


@app.command("add-geodistance")
def add_geodistance(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    from_column: str = typer.Option(
        ..., "--from-column", "--from", help="Source geopoint or geometry column"
    ),
    to_column: str = typer.Option(
        ..., "--to-column", "--to", help="Target geopoint or geometry column"
    ),
    output_column: str = typer.Option(
        "geo_distance", "--output-column", "-c", help="Output distance column name"
    ),
    unit: GeoDistanceUnitMiles = typer.Option(
        GeoDistanceUnitMiles.MILES,
        "--unit",
        "-u",
        case_sensitive=False,
        help="Output unit: MILES or KILOMETERS",
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Compute distance between two geopoint/geometry columns.

    Use instead of haversine calculations in Python. Both columns must be
    geopoint or geometry type (use add-geopoint first if needed).

    Example: dku recipe add-geodistance prep1 --from origin --to destination -P PROJ
    """
    # --unit is a GeoDistanceUnitMiles click.Choice: invalid values are rejected
    # at parse time, so no body-level validation is needed.
    step_type, params, _vcols = _geodistance_step(
        from_column, to_column, output_column, unit.value
    )
    _add_prepare_step(ctx, recipe_name, project, step_type, params, at=at)


# ---------------------------------------------------------------------------
# apply-spec — build a full multi-step prepare recipe from one declarative spec
# ---------------------------------------------------------------------------


def _spec_err(i: int, op: str, msg: str, details: list[str] | None = None) -> None:
    exit_with_error(f"Spec entry [{i}] (op '{op}'): {msg}", details=details)


def _spec_columns(val) -> list[str]:
    """Accept a CSV string or a JSON list; return a clean column-name list."""
    if isinstance(val, str):
        return [c.strip() for c in val.split(",") if c.strip()]
    if isinstance(val, list):
        return [str(c) for c in val]
    return []


def _resolve_spec_renamings(i: int, e: dict) -> list[dict]:
    mappings = e.get("mappings")
    if mappings is not None:
        if isinstance(mappings, dict):
            parsed = mappings
        elif isinstance(mappings, str):
            parsed = {}
            for p in (p.strip() for p in mappings.split(",")):
                if not p:
                    continue
                if p.count(":") != 1:
                    _spec_err(
                        i,
                        "rename",
                        f"could not parse 'mappings' shorthand {mappings!r}.",
                        [
                            'Object: {"mappings": {"old1":"new1","old2":"new2"}}',
                            'Shorthand: {"mappings": "old1:new1,old2:new2"}',
                            "Names containing ':' or ',' require the object form.",
                        ],
                    )
                k, v = p.split(":")
                parsed[k.strip()] = v.strip()
        else:
            _spec_err(
                i, "rename", "'mappings' must be an object or 'old:new,...' shorthand."
            )
        return [{"from": k, "to": v} for k, v in parsed.items()]
    rf, rt = e.get("from"), e.get("to")
    if rf and rt:
        return [{"from": rf, "to": rt}]
    _spec_err(
        i,
        "rename",
        "requires 'from'+'to' (single) or 'mappings' (bulk).",
        [
            '{"op":"rename","from":"old","to":"new"}',
            '{"op":"rename","mappings":{"old1":"new1","old2":"new2"}}',
        ],
    )


def _op_formula(i, e):
    expr = e.get("expr") or e.get("expression")
    column = e.get("column")
    if not expr or not column:
        _spec_err(
            i,
            "formula",
            "requires 'expr' (or 'expression') and 'column'.",
            ['{"op":"formula","column":"total","expr":"price*qty"}'],
        )
    return _formula_step(expr, column)


def _op_rename(i, e):
    return _rename_step(_resolve_spec_renamings(i, e))


def _op_filter_rows(i, e):
    formula = e.get("formula") or e.get("expr") or e.get("expression")
    column, values = e.get("column"), e.get("values")
    action = str(e.get("action", "KEEP_ROW")).upper()
    if action not in {"KEEP_ROW", "REMOVE_ROW"}:
        _spec_err(
            i, "filter-rows", f"invalid action '{action}'. Use KEEP_ROW or REMOVE_ROW."
        )
    if formula:
        return _filter_rows_step(formula=formula, action=action)
    if column and values is not None:
        return _filter_rows_step(
            column=column, values=_spec_columns(values), action=action
        )
    _spec_err(
        i,
        "filter-rows",
        "requires 'formula', or 'column' + 'values'.",
        [
            '{"op":"filter-rows","formula":"price > 100","action":"REMOVE_ROW"}',
            '{"op":"filter-rows","column":"status","values":["active","pending"]}',
        ],
    )


def _op_fill_empty(i, e):
    cols = _spec_columns(
        e.get("columns") if e.get("columns") is not None else e.get("column")
    )
    value = e.get("value")
    if not cols or value is None:
        _spec_err(
            i,
            "fill-empty",
            "requires 'column'/'columns' and 'value'.",
            ['{"op":"fill-empty","columns":["a","b"],"value":"0"}'],
        )
    return _fill_empty_step(cols, str(value))


def _op_delete_columns(i, e):
    cols = _spec_columns(
        e.get("columns") if e.get("columns") is not None else e.get("column")
    )
    if not cols:
        _spec_err(
            i,
            "delete-columns",
            "requires 'columns'.",
            ['{"op":"delete-columns","columns":["tmp","scratch"]}'],
        )
    return _delete_columns_step(cols)


def _op_reorder(i, e):
    cols = _spec_columns(
        e.get("columns") if e.get("columns") is not None else e.get("column")
    )
    mode = str(e.get("mode", "")).upper()
    anchor = e.get("anchor")
    if not cols:
        _spec_err(i, "reorder", "requires 'columns'.")
    valid = {m.value for m in ReorderMode}
    if mode not in valid:
        _spec_err(
            i, "reorder", f"invalid 'mode' {mode!r}. Valid: {', '.join(sorted(valid))}."
        )
    if mode in {"BEFORE_COLUMN", "AFTER_COLUMN"} and not anchor:
        _spec_err(i, "reorder", f"mode {mode} requires 'anchor' (reference column).")
    return _reorder_step(cols, mode, anchor)


def _op_find_replace(i, e):
    column, find, replace = e.get("column"), e.get("find"), e.get("replace")
    if not column or find is None or replace is None:
        _spec_err(
            i,
            "find-replace",
            "requires 'column', 'find', and 'replace'.",
            [
                '{"op":"find-replace","column":"cat","find":"Electronics","replace":"Tech"}'
            ],
        )
    matching = str(e.get("matching", "SUBSTRING")).upper()
    return _find_replace_step(
        column, find, replace, matching, bool(e.get("ignore_case", False))
    )


def _op_fold(i, e):
    columns, pattern = e.get("columns"), e.get("pattern")
    if columns and pattern:
        _spec_err(i, "fold", "use 'columns' OR 'pattern', not both.")
    if not columns and not pattern:
        _spec_err(
            i,
            "fold",
            "requires 'columns' or 'pattern'.",
            [
                '{"op":"fold","columns":["jan","feb"],"key_column":"month","value_column":"sales"}'
            ],
        )
    key_column = e.get("key_column", "fold_key")
    value_column = e.get("value_column", "fold_value")
    if columns:
        return _fold_step(
            columns=_spec_columns(columns),
            key_column=key_column,
            value_column=value_column,
        )
    return _fold_step(pattern=pattern, key_column=key_column, value_column=value_column)


def _op_geopoint(i, e):
    lat = e.get("lat_column") or e.get("lat")
    lon = e.get("lon_column") or e.get("lon")
    if not lat or not lon:
        _spec_err(
            i,
            "geopoint",
            "requires 'lat_column' and 'lon_column'.",
            ['{"op":"geopoint","lat_column":"lat","lon_column":"lon"}'],
        )
    return _geopoint_step(lat, lon, e.get("output_column", "geopoint"))


def _op_geodistance(i, e):
    fr = e.get("from_column") or e.get("from")
    to = e.get("to_column") or e.get("to")
    if not fr or not to:
        _spec_err(
            i,
            "geodistance",
            "requires 'from_column' and 'to_column'.",
            [
                '{"op":"geodistance","from_column":"origin","to_column":"dest","unit":"KILOMETERS"}'
            ],
        )
    unit = str(e.get("unit", "MILES")).upper()
    valid = {m.value for m in GeoDistanceUnitMiles}
    if unit not in valid:
        _spec_err(
            i,
            "geodistance",
            f"invalid 'unit' {unit!r}. Valid: {', '.join(sorted(valid))}.",
        )
    return _geodistance_step(fr, to, e.get("output_column", "geo_distance"), unit)


_SPEC_OPS = {
    "formula": _op_formula,
    "rename": _op_rename,
    "filter-rows": _op_filter_rows,
    "fill-empty": _op_fill_empty,
    "delete-columns": _op_delete_columns,
    "reorder": _op_reorder,
    "find-replace": _op_find_replace,
    "fold": _op_fold,
    "geopoint": _op_geopoint,
    "geodistance": _op_geodistance,
}


def _build_spec_entry(i: int, entry: dict):
    """Resolve one spec entry to (step_type, params, validate_cols, name, disabled)."""
    name = entry.get("name")
    disabled = bool(entry.get("disabled", False))
    op = entry.get("op")
    if op is not None:
        handler = _SPEC_OPS.get(op)
        if handler is None:
            _spec_err(
                i,
                str(op),
                f"unknown op '{op}'.",
                [
                    f"Valid ops: {', '.join(sorted(_SPEC_OPS))}.",
                    'Or a raw step: {"type": "<Processor>", "params": {...}}.',
                ],
            )
        step_type, params, vcols = handler(i, entry)
        return step_type, params, vcols, name, disabled
    # Raw escape: any of the ~95 processors with no op shortcut.
    step_type = entry.get("type")
    if not step_type:
        exit_with_error(
            f"Spec entry [{i}] needs an 'op' (DSL) or a 'type'+'params' (raw step).",
            details=[
                f"Valid ops: {', '.join(sorted(_SPEC_OPS))}.",
                'Raw: {"type": "DateParser", "params": {"inCol":"d","outCol":"d2",...}}',
            ],
        )
    _validate_processor_type(step_type)
    params = _normalize_raw_step(step_type, entry.get("params", {}))
    return step_type, params, [], name, disabled


def _spec_step_dict(i: int, entry, known: set[str] | None, recipe_name: str) -> dict:
    """Resolve one spec entry to a step dict, emitting column warnings and
    evolving `known` so a later step can reference an earlier batch step's
    output column without a false 'unknown column' warning."""
    if not isinstance(entry, dict):
        exit_with_error(
            f"Spec entry [{i}] must be a JSON object, got {type(entry).__name__}."
        )
    step_type, params, vcols, name, disabled = _build_spec_entry(i, entry)
    for label, cols in vcols:
        _warn_unknown_columns(
            cols, known, label=f"[{i}] {label}", recipe_name=recipe_name
        )
    step_dict: dict = {"metaType": "PROCESSOR", "type": step_type, "params": params}
    if name:
        step_dict["name"] = name
    if disabled:
        step_dict["disabled"] = True
    if known is not None and not disabled and isinstance(params, dict):
        _replay_step_on_known(known, step_type, params)
    return step_dict


@app.command("apply-spec")
def apply_spec(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    spec: str = typer.Argument(
        ...,
        help="Step spec: @file.json, '-' for stdin, or a literal JSON array.",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Clear existing steps first (idempotent rebuild). Default: append.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Build a full multi-step prepare recipe from one declarative spec.

    Replaces N separate add-* calls (each with its own --help lookup) with a
    single artifact. Each array entry is either an `op` mirroring an add-*
    shortcut (formula, rename, filter-rows, fill-empty, delete-columns,
    reorder, find-replace, fold, geopoint, geodistance) or a raw
    {"type","params"} step for any of the ~95 processors. Entries may carry an
    optional "name" and "disabled": true. Steps append by default; --replace
    clears existing steps first. The whole spec is validated before anything is
    saved — a bad entry aborts with its index, leaving the recipe untouched.
    """
    project_key = resolve_project(project)
    parsed = read_json_input(spec)
    if not isinstance(parsed, list):
        exit_with_error(
            "apply-spec expects a JSON array of step entries.",
            details=[
                'Example: [{"op":"formula","column":"total","expr":"price*qty"},'
                '{"op":"delete-columns","columns":["tmp"]}]',
                "Pass the spec as @file.json, '-' for stdin, or a literal array.",
            ],
        )
    if not parsed:
        exit_with_error("Spec array is empty — provide at least one step entry.")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)
        if replace:
            steps.clear()
        # Column visibility for warnings; evolves across the batch so a step
        # that references a column an earlier batch step created is not flagged.
        known = _prepare_known_columns(proj, settings)
        built = [
            _spec_step_dict(i, entry, known, recipe_name)
            for i, entry in enumerate(parsed)
        ]
        any_expression = any(
            isinstance(s["params"], dict) and "expression" in s["params"] for s in built
        )
        start = len(steps)
        steps.extend(built)
        settings.save()
        end = start + len(built) - 1
        success(
            f"Applied {len(built)} step(s) to '{recipe_name}' "
            f"({'replaced existing; ' if replace else ''}indices {start}–{end})"
        )
        if any_expression:
            _warn_expression_status_errors(_recipe, recipe_name, project_key)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
