"""dku agent-tool — list, get, create, set-definition, run, types, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_knowledge_bank,
    resolve_project,
)
from dku_cli.output import render, render_raw, resolve_output_format, success

# Built-in agent tool types, live-verified on DSS 14.6 by probe-creating each
# via new_agent_tool() — DSS exposes NO endpoint to list tool types, so this
# catalog is CLI-maintained. Catalog gaps cost agents dozens of blind guesses
# (the Model Predict type took ~28 type + 15 param-field attempts to discover).
# Other doc-listed tools (SQL Q&A, Google Search, Jira, Salesforce, MCP, ...)
# are plugin-distributed: use the Custom_agent_tool_<plugin>_<tool> type format.
BUILTIN_TOOL_TYPES = {
    "DatasetRowLookup": (
        "Query rows from a dataset by column values (use --dataset; "
        "params: retrievalMode, maxRecords)"
    ),
    "DatasetRowAppend": (
        "Append rows to a dataset (set the target via --dataset or "
        "set-definition --params)"
    ),
    "VectorStoreSearch": "Search a knowledge bank (use --knowledge-bank)",
    "LLMMeshLLMQuery": "Call another LLM or agent via LLM Mesh (use --llm)",
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


@app.command("list")
def list_agent_tools(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List agent tools in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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
                code="bad_argument",
                details=[
                    'Pass a JSON object, e.g. \'{"key":"value"}\', @file.json, '
                    "or '-' for stdin.",
                ],
            )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        builder = proj.new_agent_tool(tool_type, name=name)

        # VectorStoreSearch requires a knowledge bank
        if tool_type == "VectorStoreSearch":
            if knowledge_bank is None:
                exit_with_error(
                    "VectorStoreSearch tools require --knowledge-bank.",
                    code="missing_param",
                    details=[
                        "Example: dku agent-tool create my_search --type VectorStoreSearch --kb my_kb -P PROJ",
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
            try:
                tool.delete()
            except Exception:
                pass  # Best-effort — the original error is more informative.

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
                    code="invalid_param",
                    details=[
                        f"Example: dku agent-tool create {name} --type DatasetRowLookup --dataset my_ds -P {project_key}",
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
                    code="invalid_param",
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
                    code="invalid_param",
                    details=[
                        f"Example: dku agent-tool create {name} --type ClassicalPredictionModelPredict --saved-model my_model -P {project_key}",
                    ],
                )

            # --params merges arbitrary fields into settings.params. This is
            # the documented escape hatch for plugin tools that have no
            # dedicated flag (e.g. Custom_agent_tool_semantic-models-lab_semantic-model-query).
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

        success(f"Created agent tool '{name}' (id={tool.id}, type={tool_type})")
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
            code="missing_param",
            details=[
                'Merge params only:  dku agent-tool set-definition ID --params \'{"smRef":"model_id"}\' -P PROJ',
                "Replace top-level keys: dku agent-tool set-definition ID -d @definition.json -P PROJ",
            ],
        )
    parsed_params: dict | None = None
    if params is not None:
        parsed_params = read_json_input(params)
        if not isinstance(parsed_params, dict):
            exit_with_error(
                "--params must be a JSON object.",
                code="bad_argument",
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
        if definition is not None:
            updates = read_json_input(definition)
            raw.update(updates)
        if parsed_params:
            raw.setdefault("params", {}).update(parsed_params)
        settings.save()
        success(f"Updated agent tool '{tool_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def types(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
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
      dku agent-tool create "Web Search" --type Custom_agent_tool_my-tools_web-search -P PROJ
    """
    del project  # accepted for ergonomic parity with project-scoped commands
    output = resolve_output_format(output)
    data = [{"type": t, "description": d} for t, d in BUILTIN_TOOL_TYPES.items()]
    data.append(
        {
            "type": "Custom_agent_tool_<plugin-id>_<tool-folder>",
            "description": "Plugin-based tool (build a plugin with python-agent-tools/)",
        }
    )
    render(
        data, ["type", "description"], output_format=output, title="Agent Tool Types"
    )


@app.command()
def get(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show agent tool settings."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)
        settings = tool.get_settings()
        raw = settings.get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    tool_id: str = typer.Argument(help="Agent tool ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    input_data: str | None = typer.Option(
        None, "--input", help="Input JSON (string, @file.json, or - for stdin)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Run an agent tool.

    --input is the tool's logical input at the ROOT (the SDK adds the
    {"input": {...}} envelope — do not nest it yourself). Verified shapes:

      ClassicalPredictionModelPredict: '{"record": {"feat1": 1, "feat2": "a"}}'
      VectorStoreSearch:               '{"query": "search terms"}'
      DatasetRowLookup:                lookup values for the configured columns

    The exact shape for a configured tool is in its descriptor:
    dku agent-tool get TOOL_ID -P PROJ -o json | jq -r '.quickTestQueryStr'
    (note: quickTestQueryStr shows the ENVELOPED form — strip the outer
    {"input": ...} wrapper when passing --input).
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        tool = proj.get_agent_tool(tool_id)

        input_dict = read_json_input(input_data) or {}
        try:
            result = tool.run(input_dict)
        except Exception as e:
            if "NullPointerException" in str(e) or "null" in str(e).lower():
                exit_with_error(
                    f"Agent tool '{tool_id}' failed with a server-side null error.",
                    code="tool_run_error",
                    details=[
                        "If this is a VectorStoreSearch tool, the knowledge bank must be built first.",
                        f"Build it with: dku knowledge build <KB_ID> --wait -P {project_key}",
                        "To check knowledge banks: dku knowledge list -P "
                        + project_key,
                    ],
                )
            if tool_id.startswith("Custom_agent_tool_"):
                exit_with_error(
                    f"Plugin tool '{tool_id}' failed: {e}",
                    code="plugin_tool_error",
                    details=[
                        "Plugin tools may fail when tested directly — presets and "
                        "connections are only resolved inside agent execution context.",
                        f"Test via the agent instead: dku agent test AGENT_ID -P {project_key}",
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
