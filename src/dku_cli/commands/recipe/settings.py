"""Recipe code, definition, and settings commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from dku_cli.enums import ContainerMode, EnvMode

from ._common import *


def _unwrap_recipe_definition_payload(new_def):
    """Strip get-definition / DSS-raw wrappers from --definition JSON.

    Without this, passing back the full output of ``dku recipe get-definition
    --format json`` (shape ``{"definition": {...}, "payload": {...}}``) or a raw DSS
    response (``{"definition": {...}, "$status": ...}``) silently writes the
    *wrapper keys* into ``raw_definition`` instead of the recipe fields —
    "Updated definition" reports success and nothing changes.
    """
    if not isinstance(new_def, dict):
        return new_def
    keys = set(new_def.keys())
    wrappers = {
        frozenset({"definition", "payload"}),
        frozenset({"definition", "$status"}),
    }
    if keys in wrappers and isinstance(new_def.get("definition"), dict):
        warn(
            "Unwrapping --definition: input had a get-definition wrapper "
            "({'definition': ..., '"
            + ("payload" if "payload" in keys else "$status")
            + "': ...}); using the inner 'definition' object."
        )
        return new_def["definition"]
    return new_def


@app.command("set-code")
def set_code(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    code: str | None = typer.Option(
        None,
        "--code",
        "-c",
        help="Code: literal string, @file.py, or '-' for stdin",
    ),
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a file containing the code (equivalent to --code @file).",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the code payload of a code recipe.

    Use --code for a literal string / ``@file`` / ``-`` (stdin), or --file
    for a plain file path (matches the ``curl -f``/``kubectl -f`` idiom).
    """
    if (code is None) == (file is None):
        exit_with_error(
            "Provide exactly one of --code / --file.",
            details=[
                'Literal: dku recipe set-code RECIPE --code "print(\\"hi\\")" -P PROJ',
                "From file (either form):",
                "  dku recipe set-code RECIPE --code @my_recipe.py -P PROJ",
                "  dku recipe set-code RECIPE --file my_recipe.py -P PROJ",
                "From stdin: cat my_recipe.py | dku recipe set-code RECIPE --code - -P PROJ",
            ],
        )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )

        if file is not None:
            code_text = Path(file).read_text()
        elif code == "-":
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
) -> None:
    """Get the code payload of a code recipe.

    Only works on code recipes (python, sql, r, shell, etc.). For visual
    recipes (prepare, join, group, etc.) use 'dku recipe get-settings' to
    inspect the recipe definition.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        help="Recipe definition JSON — updates raw_definition (connection, I/O, description). String, @file.json, or '-' for stdin. Shallow merge: top-level keys overwrite, siblings preserved (use 'dku recipe set-description' for the common description-only case).",
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
            details=[
                "--definition: updates raw recipe definition (connection, I/O mappings)",
                "--payload: updates obj_payload (visual recipe config: aggregations, computations)",
            ],
        )
    if definition and payload_json:
        exit_with_error(
            "Cannot use both --definition and --payload. Provide one.",
        )
    if deep_merge and not payload_json:
        exit_with_error(
            "--deep-merge can only be used with --payload.",
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
            new_def = _unwrap_recipe_definition_payload(new_def)
            raw = settings.get_recipe_raw_definition()
            raw.update(new_def)
            target = "definition"
        else:
            # A code recipe's payload IS its source code (stored as a string),
            # not a JSON config dict. _get_recipe_payload seeds str_payload="{}"
            # to obtain a mutable dict — which silently WIPES the source. Refuse
            # before that happens and point at the right verbs.
            if _is_text_payload_recipe(settings):
                rtype = settings.get_recipe_raw_definition().get("type", "")
                exit_with_error(
                    f"Recipe '{recipe_name}' is a code recipe (type '{rtype}') — "
                    "its payload is source code, not JSON config. --payload would "
                    "OVERWRITE the code.",
                    status=2,
                    details=[
                        f"Change the code:      dku recipe set-code {recipe_name} --file CODE -P {project_key}",
                        f"Change container/env: dku recipe set-env {recipe_name} --container-mode NONE --env-mode USE_BUILTIN_MODE -P {project_key}",
                    ],
                )
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


@app.command("set-description")
def set_description(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    description: str = typer.Option(
        ...,
        "--description",
        "-d",
        help="Description text: literal string, @file.md, or '-' for stdin.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the recipe description (shortcut for set-definition --definition '{"description":"..."}').

    Description lives at .definition.description on get-definition output (NOT
    .recipe.description). Other top-level definition fields (type, name, I/O
    mappings) are preserved.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        text = read_text_input(description)
        settings = recipe.get_settings()
        raw = settings.get_recipe_raw_definition()
        raw["description"] = text
        settings.save()
        success(f"Updated description for recipe '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-env")
def set_env(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    env_mode: str | None = typer.Option(
        None,
        "--env-mode",
        help=(
            "Code-env mode: INHERIT (project default), USE_BUILTIN_MODE, "
            "EXPLICIT_ENV (specify --env-name). Sets params.envSelection.envMode."
        ),
    ),
    env_name: str | None = typer.Option(
        None,
        "--env-name",
        help="Code env name when --env-mode EXPLICIT_ENV. Sets params.envSelection.envName.",
    ),
    container_mode: str | None = typer.Option(
        None,
        "--container-mode",
        help=(
            "Container execution mode: INHERIT (project default), NONE (run on the "
            "DSS process), EXPLICIT_CONTAINER (use --container-conf), KUBERNETES, "
            "EXPLICIT_K8S. Sets params.containerSelection.containerMode."
        ),
    ),
    container_conf: str | None = typer.Option(
        None,
        "--container-conf",
        help="Container configuration name when --container-mode EXPLICIT_CONTAINER.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the code env and/or container of an existing code recipe.

    Updates a python/r/sql/pyspark/cpython/sparkr recipe's code-env and container
    selection in place — the same knobs `recipe create` exposes, but for a recipe
    that already exists (e.g. after `set-code`). Avoids the `set-settings` round-trip,
    which rejects code recipes because their `payload` is a code string, not a dict.

    Pin a recipe to a built code env and run it on the DSS process:

      dku recipe set-env my_recipe --env-mode EXPLICIT_ENV --env-name my_env \\
        --container-mode NONE -P PROJ
    """
    if not (env_mode or container_mode):
        exit_with_error(
            "Nothing to set — pass --env-mode and/or --container-mode.",
        )
    # DSS deserializes an unknown enum value to null and only fails at build
    # time — validate up-front against the same enums `recipe create` uses.
    if env_mode and env_mode.upper() not in {m.value for m in EnvMode}:
        exit_with_error(
            f"Invalid --env-mode '{env_mode}'.",
            details=[f"Use {', '.join(m.value for m in EnvMode)}."],
        )
    if container_mode and container_mode.upper() not in {
        m.value for m in ContainerMode
    }:
        exit_with_error(
            f"Invalid --container-mode '{container_mode}'.",
            details=[f"Use {', '.join(m.value for m in ContainerMode)}."],
        )
    if env_mode and env_mode.upper() == "EXPLICIT_ENV" and not env_name:
        exit_with_error(
            "--env-mode EXPLICIT_ENV requires --env-name.",
        )
    if (
        container_mode
        and container_mode.upper() == "EXPLICIT_CONTAINER"
        and not container_conf
    ):
        exit_with_error(
            "--container-mode EXPLICIT_CONTAINER requires --container-conf.",
        )
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        if env_name:
            # DSS accepts any string for envName without checking it exists, so a
            # typo'd / nonexistent env only surfaces as a confusing failure at
            # recipe build time. Validate up-front against the live env list.
            known = {e.get("envName") for e in client.list_code_envs()}
            if env_name not in known:
                exit_with_error(
                    f"Code env '{env_name}' does not exist on this instance.",
                    status=2,
                    details=[
                        "List available envs: dku code-env list",
                        f"Create it:           dku code-env create {env_name} --python-version 3.11",
                    ],
                )
        recipe = _get_recipe_or_exit(
            client.get_project(project_key), recipe_name, project_key
        )
        settings = recipe.get_settings()
        rp = _get_or_create_recipe_params(settings)
        if container_mode:
            cs = rp.setdefault("containerSelection", {})
            cs["containerMode"] = container_mode.upper()
            if container_conf:
                cs["containerConf"] = container_conf
            info(
                f"Container: {container_mode.upper()}"
                + (f" ({container_conf})" if container_conf else "")
            )
        if env_mode:
            es = rp.setdefault("envSelection", {})
            es["envMode"] = env_mode.upper()
            if env_name:
                es["envName"] = env_name
            info(f"Env: {env_mode.upper()}" + (f" ({env_name})" if env_name else ""))
        settings.save()
        success(f"Updated env/container for recipe '{recipe_name}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-settings")
def get_settings_cmd(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
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
    output = resolve_output_format()
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
        "--definition",
        "-d",
        help=(
            "Settings JSON (string, @file.json, or '-' for stdin). "
            "Aliases: -s/--settings (canonical) and -d/--definition "
            "(for cross-verb consistency with insight/dashboard set-definition)."
        ),
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
                # Code recipes (python/sql/r/shell) have a STRING payload (the
                # source). For these, set-settings is the wrong tool — the string
                # payload is correct, not a json.dumps mistake. Point to the
                # dedicated verbs instead.
                if _is_text_payload_recipe(settings):
                    exit_with_error(
                        "This is a code recipe — its `payload` is the source "
                        "code (a string), so `set-settings` cannot edit it.",
                        details=[
                            "Use the dedicated verbs instead:",
                            "  • change the code   → dku recipe set-code R -c @file -P PROJ",
                            "  • change env/container → dku recipe set-env R "
                            "--env-mode … --container-mode NONE -P PROJ",
                            "",
                            "On a docker-less DSS, an INHERIT container mode can "
                            "resolve to a container and the job dies with a "
                            "misleading 'python process failed (exit code: 1)' — "
                            "set --container-mode NONE to run on the DSS process.",
                            "",
                            "To edit non-payload definition keys (inputs, tags, "
                            "params), drop `payload` from your JSON and re-send.",
                        ],
                        status=2,
                    )
                exit_with_error(
                    "Recipe payload must be a JSON object, not a "
                    f"{type(new_payload).__name__}.",
                    details=[
                        "`get-settings` JSON output already returns `payload` as a "
                        "parsed object — do NOT re-stringify it with "
                        "`json.dumps(payload)` before sending to `set-settings`.",
                        "",
                        "Fix: keep `payload` as a nested dict in your input "
                        "JSON. Example with jq:",
                        "  dku --format json recipe get-settings R -P PROJ  \\\\",
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
                details=[f"Existing refs in role '{role}': {existing}"],
            )

        # Visual recipes mirror the inputs in payload.virtualInputs[].dataset.
        # When the dataset reference is stored there too, keep them in sync —
        # including originLabel (the human-readable source tag emitted by Stack
        # recipes' addOriginColumn). Leaving originLabel pointing at the old
        # ref makes get-settings output misleading and breaks any downstream
        # consumer of the origin column.
        try:
            payload = settings.obj_payload
        except (AttributeError, TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            for vi in payload.get("virtualInputs") or []:
                if isinstance(vi, dict) and vi.get("dataset") == old_ref:
                    vi["dataset"] = new_ref
                    # Only rewrite originLabel when it matches the old ref —
                    # preserve user-customized labels.
                    if vi.get("originLabel") == old_ref:
                        vi["originLabel"] = new_ref

        settings.save()
        success(
            f"Replaced input '{old_ref}' → '{new_ref}' on recipe '{recipe_name}' (role={role})"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
