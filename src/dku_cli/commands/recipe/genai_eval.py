"""GenAI evaluation recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *


@app.command("create-extract")
def create_extract(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with documents"
    ),
    output_ds: str = typer.Option(..., "--output-ds", help="Output dataset name"),
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
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with LLM outputs to evaluate"
    ),
    eval_store: str = typer.Option(..., "--eval-store", help="LLM evaluation store ID"),
    output_ds: str = typer.Option(
        None, "--output-ds", help="Output scored dataset name"
    ),
    output_metrics: str = typer.Option(
        None, "--output-metrics", help="Metrics dataset name"
    ),
    task_type: str = typer.Option(
        None, "--task-type", help="Task type (e.g. QUESTION_ANSWERING, SUMMARIZATION)"
    ),
    metrics: str = typer.Option(
        None,
        "--metrics",
        help="Comma-separated metrics (e.g. answerRelevancy,faithfulness)",
    ),
    input_col: str = typer.Option(
        None, "--input-col", help="Input/question column name"
    ),
    output_col: str = typer.Option(
        None, "--output-col", help="LLM output/answer column name"
    ),
    ground_truth_col: str = typer.Option(
        None, "--ground-truth-col", help="Ground truth column name"
    ),
    context_col: str = typer.Option(None, "--context-col", help="Context column name"),
    completion_llm: str = typer.Option(
        None, "--completion-llm", help="Completion LLM ID for evaluation logic"
    ),
    embedding_llm: str = typer.Option(
        None, "--embedding-llm", help="Embedding LLM ID for similarity metrics"
    ),
    bleu_tokenizer: str | None = typer.Option(
        None,
        "--bleu-tokenizer",
        help="BLEU/ROUGE tokenizer (e.g. 'whitespace', '13a', 'intl'). Sets payload.bleuTokenizer.",
    ),
    bertscore_model: str | None = typer.Option(
        None,
        "--bertscore-model",
        help="HuggingFace model used by BERTScore. Sets payload.bertScoreModel.",
    ),
    input_format: str | None = typer.Option(
        None,
        "--input-format",
        help="Input record format: SINGLE_TURN (default), CHAT, etc. Sets payload.inputFormat.",
    ),
    fail_on_errors: bool = typer.Option(
        False,
        "--fail-on-errors",
        help="Fail the build on metric errors instead of skipping. Sets payload.failOnErrors=true.",
    ),
    temperature: float | None = typer.Option(
        None,
        "--temperature",
        help="Completion temperature for LLM-judged metrics. Sets payload.completionSettings.temperature.",
    ),
    max_records: int | None = typer.Option(
        None,
        "--max-records",
        help="Cap the number of input records evaluated. Sets payload.sampling.selection.maxRecords.",
    ),
    sampling_method: str | None = typer.Option(
        None,
        "--sampling-method",
        help="Input sampling method (HEAD_SEQUENTIAL, RANDOM_FIXED_NB, ...). Sets payload.sampling.selection.samplingMethod.",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="Random seed for sampling reproducibility. Sets payload.sampling.selection.seed.",
    ),
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
            _require_existing_dataset(
                proj, output_metrics, project_key, "Metrics output"
            )
        try:
            recipe = _create_eval_recipe(
                proj,
                recipe_name,
                "nlp_llm_evaluation",
                input_ds,
                eval_store,
                output_ds,
                output_metrics,
            )
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "does not exist" in msg:
                raise  # Let handle_api_error process not-found errors
            if "eval" in msg or "evaluation" in msg or "store" in msg:
                exit_with_error(
                    f"Failed to create LLM eval recipe — eval store '{eval_store}' may not exist.",
                    code="eval_store_not_found",
                    details=[
                        f"Create one first: dku evaluation-store create MY_STORE --flavor LLM -P {project_key}",
                        f"Then retry: dku recipe create-llm-eval {recipe_name} --eval-store MY_STORE --input {input_ds} -P {project_key}",
                    ],
                )
            raise  # Re-raise network/auth/other errors unchanged

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
        if bleu_tokenizer:
            payload["bleuTokenizer"] = bleu_tokenizer
        if bertscore_model:
            payload["bertScoreModel"] = bertscore_model
        if input_format:
            payload["inputFormat"] = input_format
        if fail_on_errors:
            payload["failOnErrors"] = True
        if temperature is not None:
            payload.setdefault("completionSettings", {})["temperature"] = temperature
        if max_records is not None or sampling_method is not None or seed is not None:
            sampling = payload.setdefault("sampling", {}).setdefault("selection", {})
            if max_records is not None:
                sampling["maxRecords"] = max_records
            if sampling_method is not None:
                sampling["samplingMethod"] = sampling_method
            if seed is not None:
                sampling["seed"] = seed
        if any(
            [
                task_type,
                metrics,
                input_col,
                output_col,
                ground_truth_col,
                context_col,
                completion_llm,
                embedding_llm,
                bleu_tokenizer,
                bertscore_model,
                input_format,
                fail_on_errors,
                temperature is not None,
                max_records is not None,
                sampling_method is not None,
                seed is not None,
            ]
        ):
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
    input_ds: str = typer.Option(
        ..., "--input", "-i", help="Input dataset with agent outputs"
    ),
    eval_store: str = typer.Option(
        ..., "--eval-store", help="Agent evaluation store ID"
    ),
    output_ds: str = typer.Option(
        None, "--output-ds", help="Output scored dataset name"
    ),
    output_metrics: str = typer.Option(
        None, "--output-metrics", help="Metrics dataset name"
    ),
    metrics: str = typer.Option(
        None,
        "--metrics",
        help="Comma-separated metrics (e.g. toolCallExactMatch,agentGoalAccuracyWithoutReference)",
    ),
    completion_llm: str = typer.Option(
        None, "--completion-llm", help="Completion LLM ID"
    ),
    embedding_llm: str = typer.Option(None, "--embedding-llm", help="Embedding LLM ID"),
    input_format: str = typer.Option(
        "AGENT_EXECUTION",
        "--input-format",
        help="Input format: AGENT_EXECUTION or PROMPT_RECIPE",
    ),
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
            _require_existing_dataset(
                proj, output_metrics, project_key, "Metrics output"
            )
        try:
            recipe = _create_eval_recipe(
                proj,
                recipe_name,
                "nlp_agent_evaluation",
                input_ds,
                eval_store,
                output_ds,
                output_metrics,
            )
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "does not exist" in msg:
                raise  # Let handle_api_error process not-found errors
            if "eval" in msg or "evaluation" in msg or "store" in msg:
                exit_with_error(
                    f"Failed to create agent eval recipe — eval store '{eval_store}' may not exist.",
                    code="eval_store_not_found",
                    details=[
                        f"Create one first: dku evaluation-store create MY_STORE --flavor AGENT -P {project_key}",
                        f"Then retry: dku recipe create-agent-eval {recipe_name} --eval-store MY_STORE --input {input_ds} -P {project_key}",
                    ],
                )
            raise  # Re-raise network/auth/other errors unchanged

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
