"""Prepare recipe step commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *
from dku_cli.enums import GeoDistanceUnitMiles, ReorderMode

# ---------------------------------------------------------------------------
# Prepare recipe step commands
# ---------------------------------------------------------------------------


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
        params = step.get("params") or {}
        stype = step.get("type", "")
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
    return known


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
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        _recipe, settings = _get_prepare_settings(proj, recipe_name, project_key)
        steps = _ensure_steps_array(settings)

        parsed_params = read_json_input(params)

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
                    wrong_cols[0]
                    if isinstance(wrong_cols, list) and wrong_cols
                    else "COL"
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
            if (
                applies_to == "SINGLE_COLUMN"
                and isinstance(cols, list)
                and len(cols) > 1
            ):
                warn(
                    f"'{step_type}' has appliesTo='SINGLE_COLUMN' but lists "
                    f"{len(cols)} columns — DSS silently applies it to only "
                    f"'{cols[0]}' (the rest are ignored, no error). "
                    "Use appliesTo='COLUMNS' to apply to all listed columns."
                )

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
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-formula")
def add_formula(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Prepare recipe name"),
    expr: str = typer.Option(
        ...,
        "--expr",
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
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "CreateColumnWithGREL",
        {
            "expression": expr,
            "column": column,
        },
        at=at,
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
        help='Bulk renames as JSON: \'{"old1":"new1","old2":"new2"}\' or @file.json',
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
        parsed = read_json_input(mappings)
        if not isinstance(parsed, dict):
            exit_with_error(
                '--mappings must be a JSON object: \'{"old":"new"}\'',
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
    sources = [r["from"] for r in renamings if r.get("from")]
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "ColumnRenamer",
        {"renamings": renamings},
        validate_cols=[("--from", sources)],
        at=at,
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
        help="GREL formula for expression-based filtering (e.g. 'price > 100')",
    ),
    action: str = typer.Option(
        "KEEP_ROW",
        "--action",
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
    action_upper = action.upper()
    if action_upper not in {"KEEP_ROW", "REMOVE_ROW"}:
        exit_with_error(
            f"Invalid --action '{action}'. The FilterOnCustomFormula / FilterOnValue "
            "processors this command emits support only KEEP_ROW or REMOVE_ROW.",
            details=[
                "To clear cells use a Prepare clear/fill step; to write a boolean "
                "flag column use a FlagOn* processor (not yet exposed as a flag).",
            ],
        )
    if formula:
        _warn_grel_date_units(formula)
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "FilterOnCustomFormula",
            {
                "expression": formula,
                "action": action_upper,
            },
            at=at,
        )
    elif column and values:
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "FilterOnValue",
            {
                "appliesTo": "SINGLE_COLUMN",
                "columns": [column],
                "values": [v.strip() for v in values.split(",")],
                "action": action_upper,
                "matchingMode": "FULL_STRING",
                "normalizationMode": "EXACT",
                "booleanMode": "AND",
            },
            validate_cols=[("--column", [column])],
            at=at,
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

    params: dict
    if len(cols) == 1:
        params = {
            "appliesTo": "SINGLE_COLUMN",
            "columns": cols,
            "value": value,
        }
    else:
        params = {
            "appliesTo": "COLUMNS",
            "columns": cols,
            "value": value,
        }

    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "FillEmptyWithValue",
        params,
        validate_cols=[("--column", cols)],
        at=at,
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
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "ColumnsSelector",
        {
            "appliesTo": "COLUMNS",
            "columns": cols_list,
            "keep": False,
        },
        validate_cols=[("--columns", cols_list)],
        at=at,
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

    applies_to = "SINGLE_COLUMN" if len(cols) == 1 else "COLUMNS"
    params: dict = {
        "appliesTo": applies_to,
        "columns": cols,
        "reorderAction": mode_upper,
    }
    if anchor:
        params["referenceColumn"] = anchor

    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "ColumnReorder",
        params,
        at=at,
    )


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
    at: int | None = typer.Option(
        None, "--at", help="Insert at this index (0-based). Default: append to end."
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a find-and-replace step on a column."""
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "FindReplace",
        {
            "appliesTo": "SINGLE_COLUMN",
            "columns": [column],
            "output": "",
            "mapping": [{"from": find, "to": replace}],
            "matching": matching.upper(),
            "normalization": "EXACT",
        },
        at=at,
    )


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
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "MultiColumnFold",
            {
                "columns": col_list,
                "foldNameColumn": key_column,
                "foldValueColumn": value_column,
                "foldRemoveFoldedColumns": True,
            },
            at=at,
        )
    else:
        _add_prepare_step(
            ctx,
            recipe_name,
            project,
            "MultiColumnByPrefixFold",
            {
                "columnNamePattern": pattern,
                "columnNameColumn": key_column,
                "columnContentColumn": value_column,
                "foldRemoveFoldedColumns": True,
            },
            at=at,
        )


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
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "GeoPointCreator",
        {
            "lat_column": lat_column,
            "lon_column": lon_column,
            "out_column": output_column,
        },
        at=at,
    )


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
    _add_prepare_step(
        ctx,
        recipe_name,
        project,
        "GeoDistanceProcessor",
        {
            "input1": from_column,
            "input2": to_column,
            "output": output_column,
            "outputUnit": unit.value,
            "compareTo": "COLUMN",
        },
        at=at,
    )
