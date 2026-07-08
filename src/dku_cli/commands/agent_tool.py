"""dku agent-tool — list, get, create, set-definition, run, types, delete."""

from __future__ import annotations

import contextlib
import json

import typer

from dku_cli.definition_merge import merge_params_preserving_siblings
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_knowledge_bank,
    resolve_project,
)
from dku_cli.output import (
    emit_created,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

from .agent_tool_catalog import BUILTIN_TOOL_PARAM_KEYS

# Built-in agent tool types, live-verified on DSS 14.6 by probe-creating each
# via new_agent_tool() — DSS exposes NO endpoint to list tool types, so this
# catalog is CLI-maintained. Catalog gaps cost agents dozens of blind guesses
# (the Model Predict type took ~28 type + 15 param-field attempts to discover).
# Other doc-listed tools (SQL Q&A, Google Search, Jira, Salesforce, MCP, ...)
# are plugin-distributed: use the Custom_agent_tool_<plugin>_<tool> type format.
BUILTIN_TOOL_TYPES = {
    "DatasetRowLookup": (
        "Query rows from a dataset by a single configured filter "
        "(use --dataset; run input is "
        '{"filter":{"column":"col","operator":"EQUALS","value":"x"}})'
    ),
    "DatasetRowAppend": (
        "Append rows to a dataset (set the target via --dataset or "
        "set-definition --params)"
    ),
    "VectorStoreSearch": (
        "Search a knowledge bank (use --knowledge-bank). If direct run returns "
        "a DSS null error, wrap the KB as a RAG LLM and use LLMMeshLLMQuery."
    ),
    "LLMMeshLLMQuery": (
        "Call another LLM or agent via LLM Mesh (use --llm; run input is "
        '{"question":"..."} at the root)'
    ),
    "ClassicalPredictionModelPredict": (
        "Predict with a saved ML model (use --saved-model → params.smRef; "
        'run input is {"record": {...}} at the root)'
    ),
    "ApiEndpoint": (
        "Call a deployed API service endpoint (configure via set-definition --params)"
    ),
    "ImageGeneration": (
        "Generate images via an image LLM (params: nbImagesToGenerate, "
        "imageHandlingMode)"
    ),
    "GenerateArtifact": (
        "Render a Jinja template into an artifact (params: templateType, "
        "outputFormat, variables)"
    ),
}

app = typer.Typer(help="Manage DSS agent tools.")


def _warn_unknown_param_keys(tool_type: str, param_keys) -> None:
    """Warn (stderr, non-blocking) on param keys unknown to a BUILT-IN type.

    DSS accepts arbitrary keys, so this is a speed-bump, not a gate. For plugin
    types (or built-ins whose schema is uncharacterised) the known set is empty
    and we stay silent — there is no public API to introspect their params.
    """
    known = BUILTIN_TOOL_PARAM_KEYS.get(tool_type)
    if not known:
        return
    unknown = [k for k in param_keys if k not in known]
    if unknown:
        warn(
            f"Param key(s) {unknown} are not known for built-in type "
            f"'{tool_type}' (known: {known}). DSS does not validate param keys, "
            "so a wrong key persists silently and the tool fails at run time. "
            f"Check expected keys: dku agent-tool describe {tool_type}"
        )


@app.command("list")
def list_agent_tools(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List agent tools in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tools = proj.list_agent_tools(include_shared=True)

        data = []
        for t in tools:
            data.append(
                {
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "type": t.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Agent Tools ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Tool name"),
    tool_type: str = typer.Option(
        ..., "--type", "-t", help="Tool type (run 'dku agent-tool types' to list)"
    ),
    knowledge_bank: str | None = typer.Option(
        None,
        "--knowledge-bank",
        "--kb",
        help="Knowledge bank ID (required for VectorStoreSearch)",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "--ds",
        help=(
            "Dataset name for DatasetRowLookup / DatasetRowAppend "
            "(auto-detects field name per DSS version)"
        ),
    ),
    llm: str | None = typer.Option(
        None,
        "--llm",
        help="LLM ID e.g. openai:conn:gpt-4o (sets llmId for LLMMeshLLMQuery)",
    ),
    saved_model: str | None = typer.Option(
        None,
        "--saved-model",
        "--sm",
        help=(
            "Saved model ID or name (sets params.smRef for "
            "ClassicalPredictionModelPredict)"
        ),
    ),
    params: str | None = typer.Option(
        None,
        "--params",
        help=(
            "Tool params JSON: literal, @file.json, or '-' for stdin. Merged "
            "into the new tool's settings.params on create (atomic — if the "
            "params write fails, the tool is deleted so you don't leave "
            "orphans). Required for plugin tool types like "
            "`Custom_agent_tool_<plugin>_<tool>` that have no dedicated flag."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new agent tool.

    Run 'dku agent-tool types' for the built-in type catalog (verified per DSS
    version). For custom Python tools, build a plugin and use
    Custom_agent_tool_<plugin>_<tool>.

    Use `--params @config.json` for plugin tool types that need configuration
    that has no dedicated flag (e.g. semantic-model-query, google-search-tool).
    The params write is atomic: if it fails, the half-built tool is deleted so
    you don't leave orphans.

    Examples:
      dku agent-tool create my_lookup --type DatasetRowLookup --dataset customers -P PROJ
      dku agent-tool create my_search --type VectorStoreSearch --kb my_kb -P PROJ
      dku agent-tool create my_llm --type LLMMeshLLMQuery --llm openai:conn:gpt-4o -P PROJ
      dku agent-tool create churn_predict --type ClassicalPredictionModelPredict --saved-model my_model -P PROJ
      dku agent-tool create "Web Search" --type Custom_agent_tool_google-search-tool_google-search-tool -P PROJ
      dku agent-tool create sm_query --type Custom_agent_tool_semantic-models-lab_semantic-model-query \\
          --params '{"config":{"semantic_model_id":"sm","llm_id":"<LLM>","embedding_llm_id":"<EMB>","sql_generation_mode":"VERSION"}}'
          # NOTE: semantic-model-query needs the config{} wrapper with BOTH llm_id and
          # embedding_llm_id. A flat {"semanticModelId":...} saves but fails at runtime:
          # "Tool is not fully configured: Semantic model and LLM are required".
    """
    project_key = resolve_project(project)
    # Validate --params up front so we don't half-create the tool on bad JSON.
    parsed_params: dict | None = None
    if params is not None:
        parsed_params = read_json_input(params)
        if not isinstance(parsed_params, dict):
            exit_with_error(
                "--params must be a JSON object.",
                details=[
                    'Pass a JSON object, e.g. \'{"key":"value"}\', @file.json, '
                    "or '-' for stdin.",
                ],
            )
        _warn_unknown_param_keys(tool_type, parsed_params.keys())

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        builder = proj.new_agent_tool(tool_type, name=name)

        # VectorStoreSearch requires a knowledge bank
        if tool_type == "VectorStoreSearch":
            if knowledge_bank is None:
                exit_with_error(
                    "VectorStoreSearch tools require --knowledge-bank.",
                    details=[
                        "Example: dku agent-tool create my_search "
                        "--type VectorStoreSearch --kb my_kb -P PROJ",
                        "List knowledge banks with: dku knowledge list -P PROJ",
                    ],
                )
            # Resolve name → ID. DSS stores knowledgeBankRef as the KB ID;
            # passing a name silently breaks the tool at runtime.
            kb = resolve_knowledge_bank(proj, knowledge_bank)
            builder.with_knowledge_bank(kb.id)

        tool = builder.create()

        # From here on, every error path must delete the tool we just created;
        # otherwise a half-configured plugin tool stays in the project and the
        # next `agent-tool create` with the same name fails with "already
        # exists" — exactly the orphan-tool footgun the user reported.
        def _cleanup_orphan() -> None:
            # Best-effort — the original error is more informative.
            with contextlib.suppress(Exception):
                tool.delete()

        try:
            # Post-creation param configuration for built-in types
            if dataset and tool_type in ("DatasetRowLookup", "DatasetRowAppend"):
                settings = tool.get_settings()
                # Detect which field the server uses (datasetRef in DSS 14.5+,
                # datasetSmartName in older versions). Write to existing field,
                # or both if fresh tool for version compatibility.
                if "datasetRef" in settings.params:
                    settings.params["datasetRef"] = dataset
                elif "datasetSmartName" in settings.params:
                    settings.params["datasetSmartName"] = dataset
                else:
                    settings.params["datasetSmartName"] = dataset
                    settings.params["datasetRef"] = dataset
                settings.save()
            elif dataset:
                _cleanup_orphan()
                exit_with_error(
                    f"--dataset is only for DatasetRowLookup/DatasetRowAppend tools, not {tool_type}.",
                    details=[
                        f"Example: dku agent-tool create {name} "
                        f"--type DatasetRowLookup --dataset my_ds -P {project_key}",
                    ],
                )

            if llm and tool_type == "LLMMeshLLMQuery":
                settings = tool.get_settings()
                settings.params["llmId"] = llm
                settings.save()
            elif llm:
                _cleanup_orphan()
                exit_with_error(
                    f"--llm is only for LLMMeshLLMQuery tools, not {tool_type}.",
                    details=[
                        f"Example: dku agent-tool create {name} --type LLMMeshLLMQuery --llm openai:conn:gpt-4o -P {project_key}",
                    ],
                )

            if saved_model and tool_type == "ClassicalPredictionModelPredict":
                from dku_cli.helpers import resolve_saved_model

                sm = resolve_saved_model(proj, saved_model)
                settings = tool.get_settings()
                # Verified live (DSS 14.6): the model field is `smRef` — NOT
                # savedModelId/modelId. Params are not validated server-side,
                # so a wrong key persists silently and the tool fails at run
                # time with "Model to use is not specified".
                settings.params["smRef"] = sm.sm_id
                settings.save()
            elif saved_model:
                _cleanup_orphan()
                exit_with_error(
                    f"--saved-model is only for ClassicalPredictionModelPredict tools, not {tool_type}.",
                    details=[
                        f"Example: dku agent-tool create {name} "
                        "--type ClassicalPredictionModelPredict "
                        f"--saved-model my_model -P {project_key}",
                    ],
                )

            # --params merges arbitrary fields into settings.params. This is
            # the documented escape hatch for plugin tools that have no
            # dedicated flag.
            if parsed_params:
                settings = tool.get_settings()
                # settings.params is a dict-like proxy on real DSS; on the
                # test MagicMock it behaves enough like a dict for .update().
                for k, v in parsed_params.items():
                    settings.params[k] = v
                settings.save()
        except typer.Exit:
            raise
        except Exception:
            _cleanup_orphan()
            raise

        emit_created(
            {"id": tool.id, "name": name, "type": tool_type},
            message=f"Created agent tool '{name}' (id={tool.id}, type={tool_type})",
            next_command=f"dku agent-tool get {tool.id} -P {project_key}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="Definition JSON merged at the top level (string, @file.json, or - for stdin)",
    ),
    params: str | None = typer.Option(
        None,
        "--params",
        help=(
            "Params-only JSON merged into settings.params (same escape hatch "
            'as create --params), e.g. \'{"smRef":"model_id"}\''
        ),
    ),
    deep_merge: bool = typer.Option(
        False,
        "--deep-merge",
        help=(
            "Recursively merge --definition params into the existing params "
            "instead of replacing the params object wholesale"
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update agent tool settings (params, config, etc.).

    Use --params to merge keys into settings.params without restating the full
    definition (parity with create --params). Note: DSS does NOT validate
    params keys against the tool type — unknown keys persist silently, so
    "it saved" does not mean "it is configured correctly". Check the expected
    keys with 'dku agent-tool types' and verify with 'dku agent-tool run'.
    """
    project_key = resolve_project(project)
    if definition is None and params is None:
        exit_with_error(
            "Pass --definition and/or --params.",
            details=[
                "Merge params only: dku agent-tool set-definition ID "
                '--params \'{"smRef":"model_id"}\' -P PROJ',
                "Replace top-level keys: dku agent-tool set-definition ID -d @definition.json -P PROJ",
            ],
        )
    parsed_params: dict | None = None
    if params is not None:
        parsed_params = read_json_input(params)
        if not isinstance(parsed_params, dict):
            exit_with_error(
                "--params must be a JSON object.",
                details=[
                    'Pass a JSON object, e.g. \'{"key":"value"}\', @file.json, '
                    "or '-' for stdin.",
                ],
            )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        settings = tool.get_settings()
        raw = settings.get_raw()
        if parsed_params:
            _warn_unknown_param_keys(raw.get("type", ""), parsed_params.keys())
        if definition is not None:
            updates = read_json_input(definition)
            if isinstance(updates, dict) and isinstance(updates.get("params"), dict):
                _warn_unknown_param_keys(raw.get("type", ""), updates["params"].keys())
            merge_params_preserving_siblings(raw, updates, deep=deep_merge)
        if parsed_params:
            raw.setdefault("params", {}).update(parsed_params)
        settings.save()
        success(f"Updated agent tool '{tool_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _tree_children(tree, names: list[str]):
    """Walk a list_files() tree along NAMES; return the final node's children.

    Returns None if any segment is missing. Accepts the list-or-dict root shape
    DSS returns from DSSPlugin.list_files().
    """
    nodes = tree if isinstance(tree, list) else [tree]
    for name in names:
        match = None
        for n in nodes:
            if isinstance(n, dict) and n.get("name") == name:
                match = n
                break
        if match is None:
            return None
        nodes = match.get("children", []) or []
    return nodes


def _dev_plugin_agent_tools(client):
    """Enumerate agent-tool components of DEV plugins.

    Returns (discovered, opaque) where discovered is a list of
    (plugin_id, tool_folder) for DEV plugins whose file tree exposes
    python-agent-tools/, and opaque is the list of non-dev plugin ids whose
    components cannot be introspected via the public API.
    """
    from dku_cli.commands.plugin import _plugin_is_dev

    discovered: list[tuple[str, str]] = []
    opaque: list[str] = []
    for p in client.list_plugins():
        pid = p.get("id", "") if isinstance(p, dict) else getattr(p, "plugin_id", "")
        if not pid:
            continue
        if not _plugin_is_dev(p):
            opaque.append(pid)
            continue
        try:
            tree = client.get_plugin(pid).list_files()
        except Exception:
            opaque.append(pid)
            continue
        children = _tree_children(tree, ["python-agent-tools"])
        if not children:
            continue
        for child in children:
            if isinstance(child, dict) and child.get("children") is not None:
                discovered.append((pid, child.get("name", "")))
    return discovered, opaque


def _read_plugin_tool_descriptor(client, plugin_id: str, folder: str):
    """Read a DEV plugin agent-tool descriptor JSON. Returns dict or None."""
    plugin = client.get_plugin(plugin_id)
    try:
        tree = plugin.list_files()
    except Exception:
        return None
    children = _tree_children(tree, ["python-agent-tools", folder])
    if not children:
        return None
    json_child = next(
        (
            c
            for c in children
            if isinstance(c, dict) and str(c.get("name", "")).endswith(".json")
        ),
        None,
    )
    if json_child is None:
        return None
    path = json_child.get("path") or f"python-agent-tools/{folder}/{json_child['name']}"
    try:
        with plugin.get_file(path) as fp:
            content = fp.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return json.loads(content)
    except Exception:
        return None


@app.command()
def types(
    ctx: typer.Context,
    include_plugins: bool = typer.Option(
        False,
        "--include-plugins",
        help=(
            "Also enumerate agent-tool components of installed DEV plugins as "
            "real Custom_agent_tool_<plugin>_<tool> type strings. Non-dev plugin "
            "tool types have no public introspection API and are reported as a note."
        ),
    ),
    project: str | None = typer.Option(
        None,
        "--project",
        "-P",
        help="Accepted and ignored. This command is instance-scoped — tool types are global, not project-scoped.",
    ),
) -> None:
    """List known built-in agent tool types.

    Instance-scoped: tool type names are global. Pass `-P PROJ` if your shell
    pipeline sets it; the flag is accepted and ignored.

    These are the type names accepted by 'dku agent-tool create --type TYPE'.
    For custom Python tools, build a plugin with python-agent-tools/ and use
    the type format: Custom_agent_tool_<plugin-id>_<tool-folder-name>

    Example: plugin 'my-tools' with tool folder 'web-search' →
      dku agent-tool create "Web Search"
      --type Custom_agent_tool_my-tools_web-search -P PROJ

    With --include-plugins, DEV plugin agent-tool components are discovered and
    merged as real type strings (non-dev plugins are listed as an honest note).
    """
    del project  # accepted for ergonomic parity with project-scoped commands
    output = resolve_output_format()
    data = [{"type": t, "description": d} for t, d in BUILTIN_TOOL_TYPES.items()]

    if not include_plugins:
        data.append(
            {
                "type": "Custom_agent_tool_<plugin-id>_<tool-folder>",
                "description": "Plugin-based tool (build a plugin with python-agent-tools/)",
            }
        )
        render(
            data,
            ["type", "description"],
            output_format=output,
            title="Agent Tool Types",
        )
        return

    opaque: list[str] = []
    try:
        client = get_client_from_ctx(ctx)
        discovered, opaque = _dev_plugin_agent_tools(client)
    except Exception as e:
        handle_api_error(e)
        return

    for pid, folder in discovered:
        data.append(
            {
                "type": f"Custom_agent_tool_{pid}_{folder}",
                "description": f"Plugin '{pid}' agent-tool component '{folder}' (dev plugin)",
            }
        )
    render(
        data, ["type", "description"], output_format=output, title="Agent Tool Types"
    )
    if opaque and output != "json":
        info(
            "The public API cannot enumerate agent-tool components of installed "
            "(non-dev) plugins: " + ", ".join(sorted(set(opaque)))
        )
        info(
            "Their type is Custom_agent_tool_<plugin-id>_<tool-folder>, where "
            "<tool-folder> is the directory name under python-agent-tools/ in "
            "the plugin (see its store page or source ZIP)."
        )


@app.command()
def describe(
    ctx: typer.Context,
    tool_type: str = typer.Argument(
        help="Tool type: a built-in name or Custom_agent_tool_<plugin>_<tool>"
    ),
    project: str | None = typer.Option(
        None,
        "--project",
        "-P",
        help="Accepted and ignored. Tool types are instance-global, not project-scoped.",
    ),
) -> None:
    """Describe an agent tool type: its known param keys and usage.

    Built-in types resolve from the CLI-maintained catalog (DSS exposes no
    endpoint to introspect built-in tool params). Plugin types
    (Custom_agent_tool_<plugin>_<tool>) resolve from the DEV plugin descriptor
    when readable; non-dev plugin tool types have NO public introspection API
    and report that honestly.
    """
    del project  # instance-global; accepted for pipeline parity
    output = resolve_output_format()

    if tool_type in BUILTIN_TOOL_TYPES:
        _describe_builtin(tool_type, output)
        return

    if tool_type.startswith("Custom_agent_tool_"):
        try:
            client = get_client_from_ctx(ctx)
            _describe_plugin_type(client, tool_type, output)
        except typer.Exit:
            raise
        except Exception as e:
            handle_api_error(e)
        return

    exit_with_error(
        f"Unknown agent tool type '{tool_type}'.",
        details=[
            "List built-in types: dku agent-tool types",
            "List plugin tool types too: dku agent-tool types --include-plugins",
        ],
    )


def _describe_builtin(tool_type: str, output: str) -> None:
    known = BUILTIN_TOOL_PARAM_KEYS.get(tool_type, [])
    description = BUILTIN_TOOL_TYPES[tool_type]
    note = (
        "Keys are CLI-observed; DSS does not validate param keys, so unknown "
        "keys persist silently and fail at run time."
    )
    if output == "json":
        render_raw(
            {
                "type": tool_type,
                "description": description,
                "knownParamKeys": known,
                "note": note,
            },
            output_format="json",
        )
        return
    info(description)
    if known:
        render(
            [{"param": k} for k in known],
            ["param"],
            output_format=output,
            title=f"{tool_type} known param keys",
        )
    else:
        warn(
            f"No param-key schema is recorded for built-in type '{tool_type}'. "
            "DSS exposes no endpoint to introspect built-in tool params; "
            "configure it via its dedicated flag or --params."
        )


def _describe_plugin_type(client, tool_type: str, output: str) -> None:
    from dku_cli.commands.plugin import _plugin_is_dev

    remainder = tool_type[len("Custom_agent_tool_") :]
    match = None
    for p in client.list_plugins():
        pid = p.get("id", "") if isinstance(p, dict) else getattr(p, "plugin_id", "")
        if pid and remainder.startswith(pid + "_"):
            match = (pid, p, remainder[len(pid) + 1 :])
            break

    if match is None:
        exit_with_error(
            f"No installed plugin matches type '{tool_type}'.",
            details=[
                "List installed plugins: dku plugin list",
                "List discoverable plugin tool types: "
                "dku agent-tool types --include-plugins",
            ],
        )

    pid, p, folder = match
    if not _plugin_is_dev(p):
        exit_with_error(
            f"Plugin '{pid}' is installed (non-dev): its agent-tool descriptor "
            "cannot be introspected via the public API.",
            details=[
                f"Inspect its source instead: dku plugin download {pid}",
                "Or reinstall it as a dev plugin to enable descriptor reads.",
                f"The type string itself is valid: Custom_agent_tool_{pid}_{folder}",
            ],
        )

    descriptor = _read_plugin_tool_descriptor(client, pid, folder)
    if descriptor is None:
        exit_with_error(
            f"Could not read the agent-tool descriptor for '{folder}' in dev "
            f"plugin '{pid}'.",
            details=[
                f"List its files: dku plugin list-files {pid}",
                "Read the descriptor JSON: dku plugin get-file "
                f"{pid} --path python-agent-tools/{folder}/<descriptor>.json",
            ],
        )

    params = descriptor.get("params", []) if isinstance(descriptor, dict) else []
    rows = [
        {
            "param": pp.get("name", ""),
            "type": pp.get("type", ""),
            "mandatory": str(pp.get("mandatory", "")),
            "label": pp.get("label", ""),
        }
        for pp in params
        if isinstance(pp, dict)
    ]
    if output == "json":
        render_raw(
            {
                "type": tool_type,
                "plugin": pid,
                "tool": folder,
                "params": params,
            },
            output_format="json",
        )
        return
    meta = descriptor.get("meta", {}) if isinstance(descriptor, dict) else {}
    label = meta.get("label") or descriptor.get("id") or folder
    info(f"Plugin '{pid}' agent-tool '{folder}' — {label}")
    if rows:
        render(
            rows,
            ["param", "type", "mandatory", "label"],
            output_format=output,
            title=f"{tool_type} params",
        )
    else:
        info("Descriptor declares no configurable params.")


@app.command()
def get(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show agent tool settings."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        settings = tool.get_settings()
        raw = settings.get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


def _diagnose_vectorstore_null(client, project_key, settings, tool_id) -> None:
    """Diagnose a VectorStoreSearch null by probing its KB — never returns.

    A null from `agent-tool run` does NOT mean the KB is unbuilt. Probe the
    referenced KB directly: if it returns documents the tool is fine (the null is
    the direct-invocation context, not the build) and must not be deleted; if it
    returns nothing the KB was never populated and the embed recipe must run.
    """
    from dataikuapi.dss.utils import AnyLoc

    from dku_cli.helpers import probe_knowledge_bank

    kb_ref = settings.get_raw().get("params", {}).get("knowledgeBankRef")
    if not kb_ref:
        exit_with_error(
            f"VectorStoreSearch tool '{tool_id}' has no knowledgeBankRef configured.",
            details=[
                f"Point it at a KB: dku agent-tool set-definition {tool_id} "
                '-d \'{"params":{"knowledgeBankRef":"KB_ID"}}\' '
                f"-P {project_key}",
            ],
        )

    loc = AnyLoc.from_ref(project_key, kb_ref)
    kb = client.get_project(loc.project_key).get_knowledge_bank(loc.object_id)
    count, probe_err = probe_knowledge_bank(kb)

    if count:
        exit_with_error(
            f"Tool '{tool_id}' returned a server-side null, but its knowledge bank "
            f"'{loc.object_id}' IS built and queryable (probe returned documents).",
            details=[
                "Do NOT delete or rebuild this tool — it is correctly configured.",
                "Direct `agent-tool run` does not resolve full runtime context for "
                "VectorStoreSearch (same limitation as plugin tools).",
                f"Confirm the KB directly: dku knowledge search {loc.object_id} "
                f"-q 'your query' -P {loc.project_key}",
                "Use the tool through an agent: "
                f"dku agent test AGENT_ID -P {project_key}",
            ],
        )

    if probe_err is not None:
        exit_with_error(
            f"Tool '{tool_id}' returned null and its knowledge bank '{loc.object_id}' "
            f"could not be probed to diagnose further (search failed: {probe_err}).",
            details=[
                "This is likely a transient DSS/search/auth issue, not "
                "necessarily an empty KB.",
                f"Probe the KB directly: dku knowledge search {loc.object_id} "
                f"-q 'test' -P {loc.project_key}",
                "If that returns documents the tool is fine; retry the run or "
                "use it through an agent.",
            ],
        )

    exit_with_error(
        f"Tool '{tool_id}' returned null: knowledge bank '{loc.object_id}' has no "
        "indexed content (search returned 0 documents).",
        details=[
            "A `knowledge build` job reporting DONE does not populate a KB by "
            "itself — the embed recipe must run and write rows into it.",
            "Run the embed recipe: "
            f"dku recipe run EMBED_RECIPE --wait -P {loc.project_key} "
            f"(find it: dku --format json flow list -P {loc.project_key})",
            "Then confirm: "
            f"dku knowledge search {loc.object_id} -q 'test' -P {loc.project_key}",
        ],
    )


@app.command()
def run(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    input_data: str | None = typer.Option(
        None, "--input", help="Input JSON (string, @file.json, or - for stdin)"
    ),
) -> None:
    """Run an agent tool.

    --input is the tool's logical input at the ROOT (the SDK adds the
    {"input": {...}} envelope — do not nest it yourself). Verified shapes:

      ClassicalPredictionModelPredict: '{"record": {"feat1": 1, "feat2": "a"}}'
      VectorStoreSearch:               '{"query": "search terms"}'
      LLMMeshLLMQuery:                 '{"question": "question to ask"}'
      DatasetRowLookup:
        '{"filter": {"column": "sku", "operator": "EQUALS", "value": "ABC"}}'

    DatasetRowLookup is single-filter. For multi-column lookup, create a
    deterministic key column upstream (for example model_family || "|" ||
    trim_grade) and filter that key.

    The exact shape for a configured tool is in its descriptor:
    dku --format json agent-tool get TOOL_ID -P PROJ | jq -r '.quickTestQueryStr'
    quickTestQueryStr shows the ENVELOPED form used by DSS, so strip the outer
    {"input": ...} wrapper when passing --input.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)

        input_dict = read_json_input(input_data) or {}
        try:
            result = tool.run(input_dict)
        except Exception as e:
            is_null = "NullPointerException" in str(e) or "null" in str(e).lower()
            if is_null and tool.get_settings().get_raw().get("type") == (
                "VectorStoreSearch"
            ):
                _diagnose_vectorstore_null(
                    client, project_key, tool.get_settings(), tool_id
                )
            if tool_id.startswith("Custom_agent_tool_"):
                exit_with_error(
                    f"Plugin tool '{tool_id}' failed: {e}",
                    details=[
                        "Plugin tools may fail when tested directly — presets and "
                        "connections are only resolved inside agent execution context.",
                        "Test via the agent instead: "
                        f"dku agent test AGENT_ID -P {project_key}",
                    ],
                )
            if is_null:
                exit_with_error(
                    f"Agent tool '{tool_id}' failed with a server-side null error.",
                    details=[
                        "Most often the --input shape is wrong. Inspect the "
                        "expected form: "
                        f"dku --format json agent-tool get {tool_id} -P {project_key} "
                        "| jq -r '.quickTestQueryStr'",
                        "quickTestQueryStr shows the ENVELOPED form — strip the outer "
                        '{"input": ...} wrapper when passing --input.',
                    ],
                )
            raise

        render_raw(result, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete an agent tool."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="agent_tool.delete",
        subject=f"agent tool '{tool_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete agent tool '{tool_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        tool.delete()
        success(f"Deleted agent tool '{tool_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
