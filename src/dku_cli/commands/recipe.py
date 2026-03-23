"""dku recipe — list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, plus GenAI recipe creation."""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_not_found_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS recipes.")


def _require_existing_dataset(proj, dataset_name: str, project_key: str, role: str) -> None:
    try:
        proj.get_dataset(dataset_name).get_definition()
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"{role} dataset '{dataset_name}' does not exist in project '{project_key}'. "
                "Create it first, then retry.",
                code="missing_dataset",
            )
        handle_api_error(e)


def _create_eval_recipe_raw(
    client,
    proj,
    recipe_name: str,
    recipe_type: str,
    input_ds: str,
    eval_store: str,
    output_ds: str | None,
    output_metrics: str | None,
):
    recipe_proto = {
        "projectKey": proj.project_key,
        "type": recipe_type,
        "name": recipe_name,
        "inputs": {
            "main": {
                "items": [{"ref": input_ds}],
            }
        },
        "outputs": {
            "evaluationStore": {
                "items": [{"ref": eval_store, "appendMode": False}],
            }
        },
    }

    if output_ds:
        recipe_proto["outputs"]["main"] = {
            "items": [{"ref": output_ds, "appendMode": False}],
        }
    if output_metrics:
        recipe_proto["outputs"]["metrics"] = {
            "items": [{"ref": output_metrics, "appendMode": True}],
        }

    # PRIVATE API: dataikuapi builders don't support eval-store outputs or rawCreation.
    # Switch to public builder when dataikuapi adds eval recipe support.
    response = client._perform_json(
        "POST",
        f"/projects/{proj.project_key}/recipes/",
        body={
            "recipePrototype": recipe_proto,
            "creationSettings": {"rawCreation": True},
        },
    )
    return proj.get_recipe(response["name"])


def _get_recipe_payload(settings) -> dict:
    payload = settings.obj_payload
    if payload is None:
        payload = {}
        settings.obj_payload = payload
    return payload


@app.command("list")
def list_recipes(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List recipes in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipes = proj.list_recipes()

        data = []
        for r in recipes:
            data.append({
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "tags": ", ".join(r.get("tags", [])) if isinstance(r.get("tags"), list) else "",
            })

        render(
            data,
            ["name", "type", "tags"],
            output_format=output,
            title=f"Recipes ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show recipe details."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = proj.get_recipe(recipe_name)
        settings = recipe.get_settings()
        raw_def = settings.get_recipe_raw_definition()

        if output == "json":
            print(json.dumps(raw_def, indent=2, default=str))
        else:
            input_refs = settings.get_flat_input_refs()
            output_refs = settings.get_flat_output_refs()

            data = [
                {"field": "Name", "value": recipe_name},
                {"field": "Type", "value": raw_def.get("type", "")},
                {"field": "Inputs", "value": ", ".join(input_refs) or "(none)"},
                {"field": "Outputs", "value": ", ".join(output_refs) or "(none)"},
            ]

            render(data, ["field", "value"], output_format=output, title=f"Recipe: {recipe_name}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
) -> None:
    """Run a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        recipe = proj.get_recipe(recipe_name)
        job = recipe.run()

        success(f"Recipe '{recipe_name}' started")
        info(f"Job ID: {job.id}")

        if wait:
            info("Waiting for completion...")
            while True:
                status = job.get_status()
                state = status.get("baseStatus", {}).get("state", "")
                if state in ("DONE", "FAILED", "ABORTED"):
                    break
                time.sleep(2)
            if state == "DONE":
                success("Recipe completed successfully")
            else:
                from dku_cli.output import error

                error(f"Recipe finished with state: {state}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    type_name: str = typer.Option(..., "--type", "-t", help="Recipe type (e.g. python, sql)"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset name"),
    output_ds: str = typer.Option(..., "--output", "-o", help="Output dataset name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe(type_name, recipe_name)
        builder.with_input(input_ds)
        builder.with_existing_output(output_ds)
        builder.build()
        success(f"Created recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        recipe.delete()
        success(f"Deleted recipe '{recipe_name}' from {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("set-code")
def set_code(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    code: str = typer.Option(..., "--code", "-c", help="Code string or @file.py to read from file"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the code payload of a code recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)

        if code.startswith("@"):
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
    """Get the code payload of a code recipe."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        payload = settings.get_payload()
        if output == "json":
            render_raw({"code": payload}, output_format="json")
        else:
            print(payload)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    definition: str = typer.Option(..., "--definition", "-d", help="Definition JSON (string, @file.json, or '-' for stdin)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the definition of a recipe from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        new_def = read_json_input(definition)
        raw = settings.get_recipe_raw_definition()
        raw.update(new_def)
        settings.save()
        success(f"Updated definition for recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-input")
def add_input(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Option(..., "--ref", "-r", help="Dataset reference to add as input"),
    role: str = typer.Option("main", "--role", help="Input role"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an input dataset to a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        settings.add_input(role, ref)
        settings.save()
        success(f"Added input '{ref}' to recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("add-output")
def add_output(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    ref: str = typer.Option(..., "--ref", "-r", help="Dataset reference to add as output"),
    role: str = typer.Option("main", "--role", help="Output role"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an output dataset to a recipe."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        recipe = client.get_project(project_key).get_recipe(recipe_name)
        settings = recipe.get_settings()
        settings.add_output(role, ref)
        settings.save()
        success(f"Added output '{ref}' to recipe '{recipe_name}'")
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# GenAI recipe creation commands
# ---------------------------------------------------------------------------


@app.command("create-embed")
def create_embed(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset name"),
    output_kb: str = typer.Option(..., "--output-kb", help="Output knowledge bank name"),
    embedding_llm: str = typer.Option(..., "--embedding-llm", help="Embedding LLM ID (e.g. openai:text-embedding-3-small)"),
    vector_store_type: str = typer.Option("CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Dataset recipe (embeds text columns into a Knowledge Bank)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("nlp_llm_rag_embedding", recipe_name)
        builder.with_input(input_ds)
        builder.with_output_knowledge_bank(output_kb, embedding_llm, vector_store_type)
        builder.build()
        success(f"Created embed recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-embed-docs")
def create_embed_docs(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset with document columns"),
    output_kb: str = typer.Option(..., "--output-kb", help="Output knowledge bank name"),
    embedding_llm: str = typer.Option(..., "--embedding-llm", help="Embedding LLM ID"),
    vlm: str = typer.Option(None, "--vlm", help="Vision LLM ID for document understanding"),
    vector_store_type: str = typer.Option("CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Documents recipe (extracts and embeds document content into a Knowledge Bank)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("embed_documents", recipe_name)
        builder.with_input(input_ds)
        if vlm:
            builder.with_vlm(vlm)
        builder.with_output_knowledge_bank(output_kb, embedding_llm, vector_store_type)
        builder.build()
        success(f"Created embed-docs recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-extract")
def create_extract(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset with documents"),
    output_ds: str = typer.Option(..., "--output", help="Output dataset name"),
    vlm: str = typer.Option(..., "--vlm", help="Vision LLM ID for content extraction"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Extract Content recipe (extracts structured content from documents using a VLM)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("extract_content", recipe_name)
        builder.with_input(input_ds)
        builder.with_vlm(vlm)
        builder.with_existing_output(output_ds)
        builder.build()
        success(f"Created extract recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-llm-eval")
def create_llm_eval(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset with LLM outputs to evaluate"),
    eval_store: str = typer.Option(..., "--eval-store", help="LLM evaluation store ID"),
    output_ds: str = typer.Option(None, "--output", help="Output scored dataset name"),
    output_metrics: str = typer.Option(None, "--output-metrics", help="Metrics dataset name"),
    task_type: str = typer.Option(None, "--task-type", help="Task type (e.g. QUESTION_ANSWERING, SUMMARIZATION)"),
    metrics: str = typer.Option(None, "--metrics", help="Comma-separated metrics (e.g. answerRelevancy,faithfulness)"),
    input_col: str = typer.Option(None, "--input-col", help="Input/question column name"),
    output_col: str = typer.Option(None, "--output-col", help="LLM output/answer column name"),
    ground_truth_col: str = typer.Option(None, "--ground-truth-col", help="Ground truth column name"),
    context_col: str = typer.Option(None, "--context-col", help="Context column name"),
    completion_llm: str = typer.Option(None, "--completion-llm", help="Completion LLM ID for evaluation logic"),
    embedding_llm: str = typer.Option(None, "--embedding-llm", help="Embedding LLM ID for similarity metrics"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an LLM Evaluation recipe (evaluates LLM outputs with metrics like relevancy, faithfulness)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        if output_ds:
            _require_existing_dataset(proj, output_ds, project_key, "Output")
        if output_metrics:
            _require_existing_dataset(proj, output_metrics, project_key, "Metrics output")
        recipe = _create_eval_recipe_raw(
            client,
            proj,
            recipe_name,
            "nlp_llm_evaluation",
            input_ds,
            eval_store,
            output_ds,
            output_metrics,
        )

        # Post-creation payload configuration
        settings = recipe.get_settings()
        payload = _get_recipe_payload(settings)
        if task_type:
            payload["taskType"] = task_type
        if metrics:
            payload["metrics"] = [m.strip() for m in metrics.split(",")]
        if input_col:
            payload["inputColumnName"] = input_col
        if output_col:
            payload["outputColumnName"] = output_col
        if ground_truth_col:
            payload["groundTruthColumnName"] = ground_truth_col
        if context_col:
            payload["contextColumnName"] = context_col
        if completion_llm:
            payload["completionLLMId"] = completion_llm
        if embedding_llm:
            payload["embeddingLLMId"] = embedding_llm
        if any([task_type, metrics, input_col, output_col, ground_truth_col, context_col, completion_llm, embedding_llm]):
            settings.save()

        success(f"Created LLM eval recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-agent-eval")
def create_agent_eval(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset with agent outputs"),
    eval_store: str = typer.Option(..., "--eval-store", help="Agent evaluation store ID"),
    output_ds: str = typer.Option(None, "--output", help="Output scored dataset name"),
    output_metrics: str = typer.Option(None, "--output-metrics", help="Metrics dataset name"),
    metrics: str = typer.Option(None, "--metrics", help="Comma-separated metrics (e.g. toolCallExactMatch,agentGoalAccuracyWithoutReference)"),
    completion_llm: str = typer.Option(None, "--completion-llm", help="Completion LLM ID"),
    embedding_llm: str = typer.Option(None, "--embedding-llm", help="Embedding LLM ID"),
    input_format: str = typer.Option("AGENT_EXECUTION", "--input-format", help="Input format: AGENT_EXECUTION or PROMPT_RECIPE"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Agent Evaluation recipe (evaluates agent tool-calling accuracy)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        if output_ds:
            _require_existing_dataset(proj, output_ds, project_key, "Output")
        if output_metrics:
            _require_existing_dataset(proj, output_metrics, project_key, "Metrics output")
        recipe = _create_eval_recipe_raw(
            client,
            proj,
            recipe_name,
            "nlp_agent_evaluation",
            input_ds,
            eval_store,
            output_ds,
            output_metrics,
        )

        # Post-creation payload configuration
        settings = recipe.get_settings()
        payload = _get_recipe_payload(settings)
        payload["inputFormat"] = input_format
        if metrics:
            payload["metrics"] = [m.strip() for m in metrics.split(",")]
        if completion_llm:
            payload["completionLLMId"] = completion_llm
        if embedding_llm:
            payload["embeddingLLMId"] = embedding_llm
        settings.save()

        success(f"Created agent eval recipe '{recipe_name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
