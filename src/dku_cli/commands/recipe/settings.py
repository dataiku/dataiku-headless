"""Recipe code, definition, and settings commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *


@app.command("set-code")
def set_code(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    code: str = typer.Option(
        ..., "--code", "-c", help="Code: literal string, @file.py, or '-' for stdin"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the code payload of a code recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )

        if code == "-":
            code_text = sys.stdin.read()
        elif code.startswith("@"):
            code_text = Path(code[1:]).read_text()
        else:
            code_text = code

        settings = recipe.get_settings()
        settings.set_payload(code_text)
        settings.save()
        success(f"Updated code for recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-code")
def get_code(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the code payload of a code recipe.

    Only works on code recipes (python, sql, r, shell, etc.). For visual
    recipes (prepare, join, group, etc.) use 'dku recipe get-settings' to
    inspect the recipe definition.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        if not _is_text_payload_recipe(settings):
            rtype = settings.get_recipe_raw_definition().get("type", "")
            exit_with_error(
                f"Recipe '{recipe_name}' is type '{rtype}', which has no code payload.",
                code="wrong_recipe_type",
                status=2,
                details=[
                    "get-code only works on code recipes (python, sql, r, shell, etc.).",
                    f"Inspect visual recipes with: dku recipe get-settings {recipe_name} -P {project_key}",
                ],
            )
        payload = settings.get_payload()
        if output == "json":
            render_raw({"code": payload}, output_format="json")
        else:
            print(payload)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Recipe definition JSON — updates raw_definition (connection, I/O). String, @file.json, or '-' for stdin.",
    ),
    payload_json: str | None = typer.Option(
        None,
        "--payload",
        help="Recipe payload JSON — updates obj_payload (visual recipe config: aggregations, computations, etc.). String, @file.json, or '-' for stdin.",
    ),
    deep_merge: bool = typer.Option(
        False,
        "--deep-merge",
        help="Recursively merge nested payload objects instead of replacing top-level keys. Use with --payload to patch deep config without losing sibling fields.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the definition or payload of a recipe from JSON.

    Use --definition to update recipe-level settings (I/O mappings, connection info).
    Use --payload to update the visual recipe configuration (aggregations, window
    computations, join keys, filter conditions, etc.). These are mutually exclusive.

    Default --payload merge is shallow (top-level keys replaced). Use --deep-merge
    for recursive merge of nested objects — patch one field without losing siblings.

    Examples:
      dku recipe set-definition my_topn --payload '{"topN": 5}' -P PROJ
      dku recipe set-definition my_join --payload '{"postFilter": {"enabled": true}}' --deep-merge -P PROJ
      dku recipe set-definition my_recipe -d @recipe_def.json -P PROJ
    """
    if not definition and not payload_json:
        exit_with_error(
            "Provide either --definition or --payload.",
            code="invalid_argument",
            details=[
                "--definition: updates raw recipe definition (connection, I/O mappings)",
                "--payload: updates obj_payload (visual recipe config: aggregations, computations)",
            ],
        )
    if definition and payload_json:
        exit_with_error(
            "Cannot use both --definition and --payload. Provide one.",
            code="invalid_argument",
        )
    if deep_merge and not payload_json:
        exit_with_error(
            "--deep-merge can only be used with --payload.",
            code="invalid_argument",
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        if definition:
            new_def = read_json_input(definition)
            raw = settings.get_recipe_raw_definition()
            raw.update(new_def)
            target = "definition"
        else:
            new_payload = read_json_input(payload_json)
            current = _get_recipe_payload(settings)
            if deep_merge:
                merged = _deep_merge_dict(current, new_payload)
                current.clear()
                current.update(merged)
            else:
                current.update(new_payload)
            target = "payload"
        settings.save()
        success(
            f"Updated {target} for recipe '{recipe_name}'"
            + (" (deep-merged)" if deep_merge else "")
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-settings")
def get_settings_cmd(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get full recipe settings as JSON (includes visual recipe payload).

    Unlike 'get' which shows a summary, this returns the complete settings
    including the payload — visual recipe configuration like sort orders,
    join keys, filter conditions, aggregations, etc.

    Output contract for `payload`:
      - Visual recipes (join, group, window, prepare, ...): always a parsed
        JSON object (dict). Safe to navigate with `jq '.payload.virtualInputs'`
        without an extra `fromjson` step.
      - Text-payload recipes (python, r, sql_query, sql_script, pyspark,
        sparkr, spark_scala, shell, cpython): always a string (the raw script
        body).
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()
        # Build complete settings dict: definition + parsed payload
        full = dict(raw_def)
        # Text-payload recipes (python / r / sql_query / ...) store the recipe
        # body as a raw string — `settings.obj_payload` tries `json.loads` on
        # it and raises ValueError. Detect those and read `_str_payload`
        # directly, same pattern as `recipe get-definition`.
        if _is_text_payload_recipe(settings):
            full["payload"] = _get_text_payload(settings)
        else:
            full["payload"] = _normalize_visual_payload(settings)
        render_raw(full, output_format=output)
    except Exception as e:
        handle_api_error(e)


def _normalize_visual_payload(settings) -> dict:
    """Return the visual recipe payload as a parsed dict, regardless of how
    dataikuapi stored it.

    Some visual recipe types store the payload as a JSON-encoded string in
    `raw_params['payload']`; others surface it as a dict on `obj_payload`.
    Empty payloads come back as None / "" / {}. Always returns a dict so
    callers don't have to second-guess the shape.
    """
    # First: try obj_payload (parsed dict for most visual types)
    try:
        payload = settings.obj_payload
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str) and payload.strip():
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
    except (AttributeError, TypeError, ValueError):
        pass
    # Fallback: raw_params['payload'] may be a JSON string or a dict
    raw_params = getattr(settings, "raw_params", None)
    if isinstance(raw_params, dict):
        raw_payload = raw_params.get("payload")
        if isinstance(raw_payload, dict):
            return raw_payload
        if isinstance(raw_payload, str) and raw_payload.strip():
            try:
                parsed = json.loads(raw_payload)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
    # No payload found — return empty dict so consumers can rely on the type
    return {}


@app.command("set-settings")
def set_settings_cmd(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    settings_json: str = typer.Option(
        ...,
        "--settings",
        "-s",
        help="Settings JSON (string, @file.json, or '-' for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set full recipe settings from JSON (supports visual recipe payload).

    Accepts a JSON object. Keys at root level update the recipe definition.
    The 'payload' key (if present) updates the visual recipe configuration
    (sort orders, join keys, filter conditions, aggregations, etc.).

    Payload update is a SHALLOW merge: top-level payload keys are replaced,
    not deep-merged. Use 'get-settings' first to read, modify, then 'set-settings'
    to preserve existing nested configuration.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        new_settings = read_json_input(settings_json)

        # Update definition (everything except payload)
        raw = settings.get_recipe_raw_definition()
        for k, v in new_settings.items():
            if k != "payload":
                raw[k] = v

        # Update payload (visual recipe config) — shallow merge at top level
        if "payload" in new_settings:
            new_payload = new_settings["payload"]
            if not isinstance(new_payload, dict):
                exit_with_error(
                    "Recipe payload must be a JSON object, not a "
                    f"{type(new_payload).__name__}.",
                    code="payload_type",
                    details=[
                        "`get-settings -o json` already returns `payload` as a "
                        "parsed object — do NOT re-stringify it with "
                        "`json.dumps(payload)` before sending to `set-settings`.",
                        "",
                        "Fix: keep `payload` as a nested dict in your input "
                        "JSON. Example with jq:",
                        "  dku recipe get-settings R -P PROJ -o json \\\\",
                        "    | jq '.payload.engineType = \"SQL\"' \\\\",
                        "    | dku recipe set-settings R -P PROJ -s -",
                    ],
                    status=2,
                )
            # Some recipe types hard-pin fields server-side (the value silently
            # reverts after save with no error). Detect the common case
            # (`nlp_agent_evaluation.outputColumnName`) up-front so the user
            # doesn't waste 30 min wondering why their custom metric still
            # sees `llm_raw_response` after `set-settings`.
            recipe_type = (raw.get("type") or "").lower()
            if (
                recipe_type == "nlp_agent_evaluation"
                and "outputColumnName" in new_payload
            ):
                exit_with_error(
                    "Cannot change `outputColumnName` on a `nlp_agent_evaluation` recipe.",
                    code="immutable_field",
                    details=[
                        "DSS hard-pins this field to `llm_raw_response` and silently",
                        "reverts edits at save time — your update would appear to",
                        "succeed but the value would not persist.",
                        "",
                        "Heads up: the column it produces is a JSON envelope —",
                        '  `{"ok": true, "text": "..."}` — not plain text. Custom',
                        "metrics that regex the output must first unwrap the `text`",
                        'field via `json.loads(raw).get("text")`.',
                        "",
                        "If you really need a different column name, use",
                        "`nlp_llm_evaluation` instead and configure `outputColumnName`",
                        "via `dku recipe create-llm-eval ... --output-col`.",
                    ],
                    status=2,
                )

            payload = _get_recipe_payload(settings)
            payload.update(new_payload)

        settings.save()
        success(f"Updated settings for recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-input")
def add_input(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Argument(
        help="Dataset, managed folder, or saved model reference (name or ID)"
    ),
    role: str | None = typer.Option(
        None,
        "--role",
        help="Input role. Defaults to 'main' for datasets/folders, 'model' for saved models",
    ),
    input_type: str | None = typer.Option(
        None,
        "--type",
        help="Input type: DATASET | MANAGED_FOLDER | SAVED_MODEL. Auto-detected if omitted.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an input to a recipe.

    The REF can be a dataset name, managed folder (name or ID), or saved model
    (ID or name). When --type is omitted, the CLI probes the project and
    resolves automatically, erroring on ambiguity. Folder/model names are
    resolved to IDs before being written — DSS stores those refs as IDs.

    For saved models, --role defaults to 'model' (what scoring recipes expect).

    For visual recipes that use payload.virtualInputs[] (join, stack, pivot,
    window, distinct, ...), this also appends a matching virtualInputs entry
    so the new input is visible to the payload. Without the sync, the recipe
    errors 'Input index: N out of range' when any downstream payload edit
    references the new input.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kind, resolved_ref = resolve_recipe_input_ref(proj, ref, input_type)
        if role is None:
            role = "model" if kind == "SAVED_MODEL" else "main"
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
        settings = recipe.get_settings()
        settings.add_input(role, resolved_ref)

        # Visual recipes store a parallel view of inputs in payload.virtualInputs.
        # settings.add_input() only touches the top-level inputs dict, so we
        # need to patch the payload explicitly when the recipe is visual.
        if role == "main" and kind == "DATASET":
            try:
                payload = settings.obj_payload
            except (AttributeError, TypeError, ValueError):
                payload = None
            if isinstance(payload, dict) and "virtualInputs" in payload:
                vi = payload.setdefault("virtualInputs", [])
                existing_indices = {v.get("index") for v in vi}
                # Compute new index = len(inputs.main.items) - 1 after add_input
                main_items = (
                    settings.get_recipe_raw_definition()
                    .get("inputs", {})
                    .get("main", {})
                    .get("items", [])
                )
                new_index = len(main_items) - 1
                if new_index not in existing_indices:
                    vi.append({"index": new_index})

        settings.save()
        label = {
            "DATASET": "dataset",
            "MANAGED_FOLDER": "folder",
            "SAVED_MODEL": "saved model",
        }[kind]
        success(
            f"Added {label} '{resolved_ref}' (role={role}) to recipe '{recipe_name}'"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("add-output")
def add_output(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Argument(help="Dataset reference to add as output"),
    role: str = typer.Option("main", "--role", help="Output role"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an output dataset to a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        settings.add_output(role, ref)
        settings.save()
        success(f"Added output '{ref}' to recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("replace-input")
def replace_input(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    old_ref: str = typer.Argument(help="Existing input dataset reference to swap out"),
    new_ref: str = typer.Argument(help="New dataset reference"),
    role: str = typer.Option(
        "main",
        "--role",
        help="Input role (default: main).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Swap an input dataset reference on a recipe.

    Updates inputs[role].items[i].ref where i matches OLD_REF, leaving roles
    and ordering otherwise intact. Use to retarget a recipe at a different
    upstream dataset (e.g. when you've recreated the source) without
    rewriting the whole settings dict via set-definition.

    Cross-project refs use the PROJECT.DATASET form.

    Example:
        dku recipe replace-input compute_features old_orders new_orders -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = _get_recipe_or_exit(proj, recipe_name, project_key)
        settings = recipe.get_settings()
        raw = settings.get_recipe_raw_definition()
        inputs = raw.get("inputs") or {}
        role_obj = inputs.get(role)
        if not role_obj:
            exit_with_error(
                f"Recipe '{recipe_name}' has no input role '{role}'.",
                code="not_found",
                details=[
                    f"Available roles: {', '.join(sorted(inputs.keys())) or '(none)'}.",
                    f"List inputs: dku recipe get-definition {recipe_name} -P {project_key} | jq .inputs",
                ],
            )
        items = role_obj.get("items") or []
        replaced = False
        for item in items:
            if item.get("ref") == old_ref:
                item["ref"] = new_ref
                replaced = True
        if not replaced:
            existing = ", ".join(it.get("ref", "?") for it in items) or "(empty)"
            exit_with_error(
                f"Recipe '{recipe_name}' role '{role}' has no input '{old_ref}'.",
                code="not_found",
                details=[f"Existing refs in role '{role}': {existing}"],
            )

        # Visual recipes mirror the inputs in payload.virtualInputs[].dataset.
        # When the dataset reference is stored there too, keep them in sync.
        try:
            payload = settings.obj_payload
        except (AttributeError, TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            for vi in payload.get("virtualInputs") or []:
                if isinstance(vi, dict) and vi.get("dataset") == old_ref:
                    vi["dataset"] = new_ref

        settings.save()
        success(
            f"Replaced input '{old_ref}' → '{new_ref}' on recipe '{recipe_name}' (role={role})"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
