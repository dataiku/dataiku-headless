"""Tests for recipe commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_recipe_list(patch_client):
    result = runner.invoke(app, ["recipe", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "recipe1" in result.output


def test_recipe_list_json(patch_client):
    result = runner.invoke(app, ["recipe", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "recipe1"
    assert parsed[0]["type"] == "python"


def test_recipe_get(patch_client):
    result = runner.invoke(app, ["recipe", "get", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "input_ds" in result.output


def test_recipe_get_json(patch_client):
    result = runner.invoke(
        app, ["recipe", "get", "recipe1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "type" in parsed


def test_recipe_run(patch_client):
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_recipe_run_wait(patch_client):
    result = runner.invoke(
        app, ["recipe", "run", "recipe1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0


def test_recipe_run_with_type(patch_client):
    """Run with --type uses job builder."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "recipe1",
            "--type",
            "RECURSIVE_BUILD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")
    builder = proj.new_job.return_value
    # Should build recipe's output refs
    builder.with_output.assert_called_once_with("output_ds")


def test_recipe_run_auto_update_schema(patch_client):
    """Run with --auto-update-schema uses job builder."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "run",
            "recipe1",
            "--auto-update-schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_called_once_with(True)


# --- New commands ---


def test_recipe_create(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "new_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("python", "new_recipe")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("input_ds")
    # MagicMock has all attrs, so hasattr picks with_existing_output
    builder.with_existing_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_create_code_recipe_fallback(patch_client):
    """CodeRecipeCreator lacks with_existing_output — falls back to with_output."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Remove with_existing_output to simulate CodeRecipeCreator
    del builder.with_existing_output
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "code_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    builder.with_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_create_output_confusion_detected(patch_client):
    """Using --output with a dataset name suggests --output-ds."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--output",
            "my_dataset",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--output-ds" in result.output
    assert "my_dataset" in result.output


def test_recipe_create_output_dataset_alias(patch_client):
    """--output-dataset works as an alias for --output-ds."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "my_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-dataset",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_existing_output.assert_called_once_with("output_ds")


def test_recipe_create_output_ds_already_exists(patch_client):
    """Recipe create gives specific error when output dataset already exists."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.build.side_effect = Exception("already exists: dataset 'output_ds'")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "new_recipe",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_recipe_create_with_connection(patch_client):
    """--connection uses with_new_output_dataset for code recipes."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    # Remove with_existing_output to simulate CodeRecipeCreator
    del builder.with_existing_output
    result = runner.invoke(app, [
        "recipe", "create", "code_recipe",
        "--type", "python",
        "--input", "input_ds",
        "--output-ds", "output_ds",
        "--connection", "filesystem_managed",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    builder.with_new_output_dataset.assert_called_once_with("output_ds", "filesystem_managed")
    builder.with_output.assert_not_called()
    builder.build.assert_called_once()


def test_recipe_create_connection_ignored_for_visual(patch_client):
    """--connection is ignored (with warning) for visual recipes that use with_existing_output."""
    result = runner.invoke(app, [
        "recipe", "create", "visual_recipe",
        "--type", "join",
        "--input", "input_ds",
        "--output-ds", "output_ds",
        "--connection", "filesystem_managed",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    builder = patch_client.get_project("PROJ1").new_recipe.return_value
    builder.with_existing_output.assert_called_once_with("output_ds")
    builder.with_new_output_dataset.assert_not_called()


def test_recipe_create_connection_required_error(patch_client):
    """Missing managed connection gives actionable error suggesting --connection."""
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    del builder.with_existing_output
    builder.build.side_effect = Exception(
        "java.lang.IllegalArgumentException: Need to create output dataset or folder, "
        "but creationInfo params are suppressing it"
    )
    result = runner.invoke(app, [
        "recipe", "create", "code_recipe",
        "--type", "python",
        "--input", "input_ds",
        "--output-ds", "output_ds",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "--connection" in result.output
    assert "filesystem_managed" in result.output


def test_recipe_delete(patch_client):
    result = runner.invoke(app, ["recipe", "delete", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted recipe" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.delete.assert_called_once()


def test_recipe_set_code_inline(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            "print('hello')",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated code" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.set_payload.assert_called_once_with("print('hello')")
    settings.save.assert_called()


def test_recipe_set_code_from_file(patch_client, tmp_path):
    code_file = tmp_path / "script.py"
    code_file.write_text("import dataiku\nds = dataiku.Dataset('test')")
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            f"@{code_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    payload_arg = settings.set_payload.call_args[0][0]
    assert "import dataiku" in payload_arg
    assert "Dataset('test')" in payload_arg


def test_recipe_get_code(patch_client):
    result = runner.invoke(app, ["recipe", "get-code", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "# Python code" in result.output


def test_recipe_get_code_json(patch_client):
    result = runner.invoke(
        app, ["recipe", "get-code", "recipe1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["code"].startswith("# Python code")
    assert "import dataiku" in result.output


def test_recipe_set_code_from_stdin(patch_client):
    stdin_code = "import dataiku\nprint('from stdin')"
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-code",
            "recipe1",
            "--code",
            "-",
            "--project",
            "PROJ1",
        ],
        input=stdin_code,
    )
    assert result.exit_code == 0
    assert "Updated code" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    payload_arg = settings.set_payload.call_args[0][0]
    assert "import dataiku" in payload_arg
    assert "from stdin" in payload_arg


def test_recipe_create_type_as_name_detected(patch_client):
    """Detect when recipe_name is actually a recipe type (e.g. 'python')."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create",
            "python",
            "--type",
            "python",
            "--input",
            "input_ds",
            "--output-ds",
            "output_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "looks like a recipe type" in result.output
    assert "dku recipe create <NAME> --type python" in result.output


def test_recipe_set_definition(patch_client):
    new_def = json.dumps({"type": "sql", "customFields": {"key": "val"}})
    result = runner.invoke(
        app,
        [
            "recipe",
            "set-definition",
            "recipe1",
            "--definition",
            new_def,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.save.assert_called()


def test_recipe_add_input(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "extra_input",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added input" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("main", "extra_input")
    settings.save.assert_called()


def test_recipe_add_output(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-output",
            "recipe1",
            "extra_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added output" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_output.assert_called_once_with("main", "extra_output")
    settings.save.assert_called()


def test_recipe_add_input_custom_role(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "add-input",
            "recipe1",
            "lookup_ds",
            "--role",
            "lookup",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("lookup", "lookup_ds")


# --- GenAI recipe creation ---


def test_recipe_create_embed(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed",
            "my_embed",
            "--input",
            "text_data",
            "--output-kb",
            "my_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created embed recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("nlp_llm_rag_embedding", "my_embed")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("text_data")
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-small", "CHROMA"
    )
    builder.build.assert_called_once()


def test_recipe_create_embed_custom_vector_store(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed",
            "my_embed",
            "--input",
            "text_data",
            "--output-kb",
            "my_kb",
            "--embedding-llm",
            "openai:text-embedding-3-large",
            "--vector-store-type",
            "FAISS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-large", "FAISS"
    )


def test_recipe_create_embed_docs(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input",
            "documents",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created embed-docs recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("embed_documents", "doc_embed")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_not_called()
    builder.with_output_knowledge_bank.assert_called_once()
    builder.build.assert_called_once()


def test_recipe_create_embed_docs_with_vlm(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input",
            "documents",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--vlm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_called_once_with("openai:gpt-4o")


def test_recipe_create_extract(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-extract",
            "my_extract",
            "--input",
            "documents",
            "--output-ds",
            "extracted_text",
            "--vlm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created extract recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("extract_content", "my_extract")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("documents")
    builder.with_vlm.assert_called_once_with("openai:gpt-4o")
    builder.with_existing_output.assert_called_once_with("extracted_text")
    builder.build.assert_called_once()


def test_recipe_create_llm_eval_minimal(patch_client):
    patch_client._perform_json.return_value = {"name": "my_eval"}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "my_eval",
            "--input",
            "responses",
            "--eval-store",
            "eval_store_1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created LLM eval recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    patch_client._perform_json.assert_called_once()
    _, kwargs = patch_client._perform_json.call_args
    body = kwargs["body"]
    assert body["recipePrototype"]["type"] == "nlp_llm_evaluation"
    assert body["recipePrototype"]["inputs"]["main"]["items"][0]["ref"] == "responses"
    assert (
        body["recipePrototype"]["outputs"]["evaluationStore"]["items"][0]["ref"]
        == "eval_store_1"
    )
    assert "main" not in body["recipePrototype"]["outputs"]
    assert "metrics" not in body["recipePrototype"]["outputs"]
    assert body["creationSettings"] == {"rawCreation": True}
    proj.get_recipe.assert_called_once_with("my_eval")


def test_recipe_create_llm_eval_full(patch_client):
    patch_client._perform_json.return_value = {"name": "rag_eval"}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-ds",
            "eval_scored",
            "--output-metrics",
            "eval_metrics",
            "--task-type",
            "QUESTION_ANSWERING",
            "--metrics",
            "answerRelevancy,faithfulness",
            "--input-col",
            "question",
            "--output-col",
            "answer",
            "--ground-truth-col",
            "expected",
            "--context-col",
            "context",
            "--completion-llm",
            "openai:gpt-4o",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = patch_client._perform_json.call_args
    body = kwargs["body"]
    assert (
        body["recipePrototype"]["outputs"]["main"]["items"][0]["ref"] == "eval_scored"
    )
    assert (
        body["recipePrototype"]["outputs"]["metrics"]["items"][0]["ref"]
        == "eval_metrics"
    )

    # Verify post-creation payload settings
    recipe = patch_client.get_project("PROJ1").get_recipe.return_value
    settings = recipe.get_settings.return_value
    payload = settings.obj_payload
    assert payload["taskType"] == "QUESTION_ANSWERING"
    assert payload["metrics"] == ["answerRelevancy", "faithfulness"]
    assert payload["inputColumnName"] == "question"
    assert payload["outputColumnName"] == "answer"
    assert payload["groundTruthColumnName"] == "expected"
    assert payload["contextColumnName"] == "context"
    assert payload["completionLLMId"] == "openai:gpt-4o"
    assert payload["embeddingLLMId"] == "openai:text-embedding-3-small"
    settings.save.assert_called()


def test_recipe_create_llm_eval_initializes_missing_payload(patch_client):
    patch_client._perform_json.return_value = {"name": "rag_eval"}
    recipe = patch_client.get_project("PROJ1").get_recipe.return_value
    settings = recipe.get_settings.return_value
    settings.obj_payload = None

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--task-type",
            "QUESTION_ANSWERING",
            "--project",
            "PROJ1",
        ],
    )

    assert result.exit_code == 0
    assert settings.obj_payload["taskType"] == "QUESTION_ANSWERING"
    settings.save.assert_called()


def test_recipe_create_llm_eval_requires_existing_output_dataset(patch_client):
    dataset_mock = patch_client.get_project("PROJ1").get_dataset("eval_scored")
    dataset_mock.get_definition.side_effect = Exception(
        "NotFoundException: dataset does not exist"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-ds",
            "eval_scored",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Output dataset 'eval_scored'" in result.output
    assert "then retry" in result.output
    patch_client._perform_json.assert_not_called()


def test_recipe_create_llm_eval_requires_existing_metrics_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")

    def _get_dataset(name):
        dataset = proj.get_dataset.return_value
        if name == "eval_metrics":
            dataset.get_definition.side_effect = Exception(
                "NotFoundException: dataset does not exist"
            )
        return dataset

    proj.get_dataset.side_effect = _get_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-metrics",
            "eval_metrics",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Metrics output dataset 'eval_metrics'" in result.output
    patch_client._perform_json.assert_not_called()


def test_recipe_create_llm_eval_preserves_non_not_found_dataset_errors(patch_client):
    dataset_mock = patch_client.get_project("PROJ1").get_dataset("eval_scored")
    dataset_mock.get_definition.side_effect = Exception("403 Forbidden")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-eval",
            "rag_eval",
            "--input",
            "qa_data",
            "--eval-store",
            "eval_store_1",
            "--output-ds",
            "eval_scored",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Permission denied" in result.output
    patch_client._perform_json.assert_not_called()


def test_recipe_create_agent_eval_minimal(patch_client):
    patch_client._perform_json.return_value = {"name": "agent_eval"}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent eval recipe" in result.output
    _, kwargs = patch_client._perform_json.call_args
    body = kwargs["body"]
    assert body["recipePrototype"]["type"] == "nlp_agent_evaluation"
    assert body["recipePrototype"]["inputs"]["main"]["items"][0]["ref"] == "agent_runs"
    assert (
        body["recipePrototype"]["outputs"]["evaluationStore"]["items"][0]["ref"]
        == "agent_store_1"
    )

    # Default input format
    recipe = patch_client.get_project("PROJ1").get_recipe.return_value
    settings = recipe.get_settings.return_value
    assert settings.obj_payload["inputFormat"] == "AGENT_EXECUTION"
    settings.save.assert_called()


def test_recipe_create_agent_eval_requires_existing_output_dataset(patch_client):
    dataset_mock = patch_client.get_project("PROJ1").get_dataset("eval_out")
    dataset_mock.get_definition.side_effect = Exception(
        "NotFoundException: dataset does not exist"
    )
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--output-ds",
            "eval_out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Output dataset 'eval_out'" in result.output
    patch_client._perform_json.assert_not_called()


def test_recipe_create_agent_eval_requires_existing_metrics_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")

    def _get_dataset(name):
        dataset = proj.get_dataset.return_value
        if name == "eval_metrics":
            dataset.get_definition.side_effect = Exception(
                "NotFoundException: dataset does not exist"
            )
        return dataset

    proj.get_dataset.side_effect = _get_dataset
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--output-metrics",
            "eval_metrics",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Metrics output dataset 'eval_metrics'" in result.output
    patch_client._perform_json.assert_not_called()


def test_recipe_create_agent_eval_full(patch_client):
    patch_client._perform_json.return_value = {"name": "agent_eval"}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-agent-eval",
            "agent_eval",
            "--input",
            "agent_runs",
            "--eval-store",
            "agent_store_1",
            "--output-ds",
            "eval_out",
            "--output-metrics",
            "eval_metrics",
            "--metrics",
            "toolCallExactMatch,agentGoalAccuracyWithoutReference",
            "--completion-llm",
            "openai:gpt-4o",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--input-format",
            "PROMPT_RECIPE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = patch_client._perform_json.call_args
    body = kwargs["body"]
    assert body["recipePrototype"]["outputs"]["main"]["items"][0]["ref"] == "eval_out"
    assert (
        body["recipePrototype"]["outputs"]["metrics"]["items"][0]["ref"]
        == "eval_metrics"
    )

    recipe = patch_client.get_project("PROJ1").get_recipe.return_value
    settings = recipe.get_settings.return_value
    payload = settings.obj_payload
    assert payload["inputFormat"] == "PROMPT_RECIPE"
    assert payload["metrics"] == [
        "toolCallExactMatch",
        "agentGoalAccuracyWithoutReference",
    ]
    assert payload["completionLLMId"] == "openai:gpt-4o"
    assert payload["embeddingLLMId"] == "openai:text-embedding-3-small"


def test_recipe_get_json_error_payload(patch_client):
    patch_client.get_project("PROJ1").get_recipe.side_effect = Exception(
        "NotFoundException: recipe does not exist"
    )
    result = runner.invoke(
        app,
        ["--errors", "json", "recipe", "get", "missing_recipe", "--project", "PROJ1"],
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    parsed = json.loads(result.stderr)
    assert parsed["error"]["code"] == "not_found"
    assert parsed["error"]["exit_code"] == 3
    assert "recipe does not exist" in parsed["error"]["message"]


# ── Schema inspection commands ───────────────────────────────────────


def test_recipe_check_schema_no_changes(patch_client):
    """check-schema exits 0 when no changes needed."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "no schema updates" in result.output.lower()


def test_recipe_check_schema_changes_needed(patch_client):
    """check-schema exits 1 when changes are needed."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe("recipe1")
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True
    updates.data = {
        "totalIncompatibilities": 2,
        "computables": [
            {
                "datasetName": "output_ds",
                "type": "DATASET",
                "newSchema": {
                    "columns": [
                        {"name": "col1", "type": "string"},
                        {"name": "col2", "type": "int"},
                    ]
                },
                "schemaChanged": True,
            }
        ],
    }
    result = runner.invoke(
        app,
        [
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "schema updates required" in result.output.lower()


def test_recipe_check_schema_json(patch_client):
    """check-schema JSON output."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert "totalIncompatibilities" in result.output


def test_recipe_apply_schema_no_changes(patch_client):
    """apply-schema does nothing when no changes needed."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "apply-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "no schema updates" in result.output.lower()


def test_recipe_apply_schema_with_changes(patch_client):
    """apply-schema applies updates when changes exist."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe("recipe1")
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True
    updates.data = {"totalIncompatibilities": 1, "computables": []}
    updates.apply.return_value = [{"status": "ok"}]
    result = runner.invoke(
        app,
        [
            "recipe",
            "apply-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "applied" in result.output.lower()
    updates.apply.assert_called_once()


# ── Visual recipe: create-join ────────────────────────────────────────


def test_recipe_create_join(patch_client):
    """Basic join recipe creation with 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined_data",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created join recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("join", "my_join")
    builder = proj.new_recipe.return_value
    assert builder.with_input.call_count == 2
    builder.with_existing_output.assert_called_once_with("joined_data")
    builder.build.assert_called_once()


def test_recipe_create_join_requires_two_inputs(patch_client):
    """Join needs >= 2 inputs."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "only_one",
            "--output-ds",
            "out",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "at least 2" in result.output


def test_recipe_create_join_with_join_key(patch_client):
    """--join-key adds EQ condition to first join."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-key",
            "customer_id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(join_dict["on"]) == 1
    assert join_dict["on"][0]["column1"]["name"] == "customer_id"
    assert join_dict["on"][0]["column2"]["name"] == "customer_id"
    assert join_dict["on"][0]["type"] == "EQ"
    settings.save.assert_called()


def test_recipe_create_join_with_different_column_names(patch_client):
    """--join-key col1=col2 maps different column names."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-key",
            "order_cust_id=id",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert join_dict["on"][0]["column1"]["name"] == "order_cust_id"
    assert join_dict["on"][0]["column2"]["name"] == "id"


def test_recipe_create_join_multiple_keys(patch_client):
    """Multiple --join-key flags add multiple conditions."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    join_dict = {"table1": 0, "table2": 1, "on": []}
    settings.raw_joins = [join_dict]

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--join-key",
            "customer_id",
            "--join-key",
            "region=region_code",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(join_dict["on"]) == 2
    assert join_dict["on"][0]["column1"]["name"] == "customer_id"
    assert join_dict["on"][1]["column1"]["name"] == "region"
    assert join_dict["on"][1]["column2"]["name"] == "region_code"


def test_recipe_create_join_no_key_backward_compat(patch_client):
    """Without --join-key, join recipe is created with default behavior."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created join recipe" in result.output
    # get_settings should NOT be called for join key configuration
    proj = patch_client.get_project("PROJ1")
    # builder.build is called, but no post-build settings modification
    proj.new_recipe.return_value.build.assert_called_once()


# ── Visual recipe: create-group with --agg ────────────────────────────


def test_recipe_create_group(patch_client):
    """Basic group recipe creation."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("grouping", "my_group")
    builder = proj.new_recipe.return_value
    builder.with_group_key.assert_called_once_with("region")


def test_recipe_create_group_with_agg(patch_client):
    """--agg configures column aggregations after build."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum,avg",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings.set_column_aggregations.assert_called_once_with(
        "amount",
        sum=True,
        avg=True,
        min=False,
        max=False,
        count=False,
        count_distinct=False,
        concat=False,
        stddev=False,
    )
    settings.save.assert_called()


def test_recipe_create_group_multiple_agg(patch_client):
    """Multiple --agg flags configure different columns."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--agg",
            "amount:sum,avg",
            "--agg",
            "order_id:count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert settings.set_column_aggregations.call_count == 2


def test_recipe_create_group_invalid_agg_format(patch_client):
    """--agg without colon gives clear error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "--agg",
            "amount_sum",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid --agg format" in result.output


def test_recipe_create_group_invalid_agg_function(patch_client):
    """--agg with unknown function gives clear error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "--agg",
            "amount:median",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown aggregation" in result.output


def test_recipe_create_group_no_agg_backward_compat(patch_client):
    """Without --agg, group recipe uses default COUNT behavior."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "my_group",
            "-i",
            "sales",
            "--output-ds",
            "sales_grouped",
            "-k",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created group recipe" in result.output


# ── Auto apply-schema ─────────────────────────────────────────────────


def test_visual_recipe_auto_applies_schema(patch_client):
    """Visual recipe creation auto-applies schema updates."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    updates = recipe_mock.compute_schema_updates.return_value
    updates.any_action_required.return_value = True

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "my_join",
            "-i",
            "orders",
            "-i",
            "customers",
            "--output-ds",
            "joined",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    updates.apply.assert_called_once()


def test_auto_apply_schema_failure_warns_not_crashes(patch_client):
    """Schema auto-apply failure emits warning, doesn't crash."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    recipe_mock.compute_schema_updates.side_effect = Exception("schema error")

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "deduped",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created distinct recipe" in result.output


# ── Dynamic connection discovery ──────────────────────────────────────


def test_ensure_output_finds_managed_connection(patch_client):
    """Uses first connection with allowManagedDatasets=True."""
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_definition.side_effect = Exception(
        "NotFoundException"
    )

    patch_client.list_connections.return_value = {
        "my_sql_conn": {"type": "PostgreSQL", "allowManagedDatasets": False},
        "s3_managed": {"type": "S3", "allowManagedDatasets": True},
    }

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "new_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("s3_managed")


def test_ensure_output_falls_back_on_permission_error(patch_client):
    """Falls back to filesystem_managed when list_connections fails (403)."""
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_definition.side_effect = Exception(
        "NotFoundException"
    )
    patch_client.list_connections.side_effect = Exception("403 Forbidden")

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-distinct",
            "my_distinct",
            "-i",
            "data",
            "--output-ds",
            "new_output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = proj.new_managed_dataset.return_value
    builder.with_store_into.assert_called_once_with("filesystem_managed")


# ---------------------------------------------------------------------------
# Prepare recipe step commands
# ---------------------------------------------------------------------------


def _setup_prepare_mock(patch_client, steps=None):
    """Configure mock for prepare recipe tests. Returns (proj, recipe_mock, settings)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {"type": "shaker", "name": "prep1"}
    payload = {"steps": list(steps) if steps else []}
    settings.obj_payload = payload
    settings.raw_steps = payload["steps"]
    settings._obj_payload = payload
    return proj, recipe_mock, settings


# -- list-steps --


def test_recipe_list_steps_empty(patch_client):
    _setup_prepare_mock(patch_client, steps=[])
    result = runner.invoke(app, ["recipe", "list-steps", "prep1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "No steps" in result.output


def test_recipe_list_steps_table(patch_client):
    _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": "ColumnRenamer", "name": "Rename cols", "params": {"renamings": [{"from": "a", "to": "b"}]}},
        {"metaType": "PROCESSOR", "type": "CreateColumnWithGREL", "params": {"expression": "upper(city)", "column": "city_upper"}},
    ])
    result = runner.invoke(app, ["recipe", "list-steps", "prep1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ColumnRenamer" in result.output
    assert "CreateColumnWithGREL" in result.output


def test_recipe_list_steps_json(patch_client):
    steps = [
        {"metaType": "PROCESSOR", "type": "ColumnRenamer", "params": {"renamings": []}},
    ]
    _setup_prepare_mock(patch_client, steps=steps)
    result = runner.invoke(app, ["recipe", "list-steps", "prep1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["type"] == "ColumnRenamer"


def test_recipe_list_steps_wrong_type(patch_client):
    """Non-prepare recipe gives prescriptive error."""
    # Default mock returns type: "python"
    result = runner.invoke(app, ["recipe", "list-steps", "recipe1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "not 'prepare'" in result.output


# -- add-step --


def test_recipe_add_step_basic(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-step", "prep1",
        "--type", "ColumnRenamer",
        "--params", '{"renamings":[{"from":"a","to":"b"}]}',
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 1
    assert settings.obj_payload["steps"][0]["type"] == "ColumnRenamer"
    settings.save.assert_called_once()


def test_recipe_add_step_at_index(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
        {"metaType": "PROCESSOR", "type": "Step1", "params": {}},
    ])
    result = runner.invoke(app, [
        "recipe", "add-step", "prep1",
        "--type", "Inserted",
        "--params", "{}",
        "--at", "1",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][1]["type"] == "Inserted"
    assert len(settings.obj_payload["steps"]) == 3


def test_recipe_add_step_with_name(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-step", "prep1",
        "--type", "FillEmptyWithValue",
        "--params", '{"column":"age","value":"0"}',
        "--name", "Fill missing ages",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["name"] == "Fill missing ages"
    assert step["type"] == "FillEmptyWithValue"


def test_recipe_add_step_wrong_type(patch_client):
    """Non-prepare recipe gives error."""
    result = runner.invoke(app, [
        "recipe", "add-step", "recipe1",
        "--type", "ColumnRenamer",
        "--params", "{}",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "not 'prepare'" in result.output


# -- remove-step --


def test_recipe_remove_step_single(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
        {"metaType": "PROCESSOR", "type": "Step1", "params": {}},
        {"metaType": "PROCESSOR", "type": "Step2", "params": {}},
    ])
    result = runner.invoke(app, [
        "recipe", "remove-step", "prep1",
        "--index", "1",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 2
    assert settings.obj_payload["steps"][0]["type"] == "Step0"
    assert settings.obj_payload["steps"][1]["type"] == "Step2"
    settings.save.assert_called_once()


def test_recipe_remove_step_multiple(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": f"Step{i}", "params": {}} for i in range(4)
    ])
    result = runner.invoke(app, [
        "recipe", "remove-step", "prep1",
        "--index", "0",
        "--index", "3",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert len(settings.obj_payload["steps"]) == 2
    assert settings.obj_payload["steps"][0]["type"] == "Step1"
    assert settings.obj_payload["steps"][1]["type"] == "Step2"


def test_recipe_remove_step_out_of_range(patch_client):
    _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
    ])
    result = runner.invoke(app, [
        "recipe", "remove-step", "prep1",
        "--index", "5",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "out of range" in result.output


# -- get-step --


def test_recipe_get_step(patch_client):
    step = {"metaType": "PROCESSOR", "type": "CreateColumnWithGREL", "params": {"expression": "upper(x)", "column": "y"}}
    _setup_prepare_mock(patch_client, steps=[step])
    result = runner.invoke(app, [
        "recipe", "get-step", "prep1",
        "--index", "0",
        "-o", "json",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "CreateColumnWithGREL"
    assert parsed["params"]["expression"] == "upper(x)"


def test_recipe_get_step_out_of_range(patch_client):
    _setup_prepare_mock(patch_client, steps=[])
    result = runner.invoke(app, [
        "recipe", "get-step", "prep1",
        "--index", "0",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "no steps" in result.output.lower()


# -- disable-step / enable-step --


def test_recipe_disable_step(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": "Step0", "params": {}},
    ])
    result = runner.invoke(app, [
        "recipe", "disable-step", "prep1",
        "--index", "0",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][0]["disabled"] is True
    settings.save.assert_called_once()


def test_recipe_enable_step(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": "Step0", "params": {}, "disabled": True},
    ])
    result = runner.invoke(app, [
        "recipe", "enable-step", "prep1",
        "--index", "0",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][0]["disabled"] is False
    settings.save.assert_called_once()


def test_recipe_disable_step_multiple(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client, steps=[
        {"metaType": "PROCESSOR", "type": f"Step{i}", "params": {}} for i in range(3)
    ])
    result = runner.invoke(app, [
        "recipe", "disable-step", "prep1",
        "--index", "0",
        "--index", "2",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["steps"][0]["disabled"] is True
    assert settings.obj_payload["steps"][2]["disabled"] is True


# ---------------------------------------------------------------------------
# Prepare recipe step shortcuts
# ---------------------------------------------------------------------------


def test_recipe_add_formula(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-formula", "prep1",
        "--expr", "upper(city)",
        "--column", "city_upper",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "CreateColumnWithGREL"
    assert step["params"]["expression"] == "upper(city)"
    assert step["params"]["column"] == "city_upper"
    settings.save.assert_called_once()


def test_recipe_add_rename_single(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-rename", "prep1",
        "--from", "old_name",
        "--to", "new_name",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "ColumnRenamer"
    assert step["params"]["renamings"] == [{"from": "old_name", "to": "new_name"}]


def test_recipe_add_rename_bulk(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-rename", "prep1",
        "--mappings", '{"col_a":"column_a","col_b":"column_b"}',
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    renamings = settings.obj_payload["steps"][0]["params"]["renamings"]
    assert len(renamings) == 2
    names = {r["from"] for r in renamings}
    assert names == {"col_a", "col_b"}


def test_recipe_add_rename_validation(patch_client):
    """--from without --to gives error."""
    _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-rename", "prep1",
        "--from", "old_name",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "--from" in result.output or "--to" in result.output


def test_recipe_add_filter_rows_by_value(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-filter-rows", "prep1",
        "--column", "status",
        "--values", "active,pending",
        "--action", "KEEP_ROW",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FlagOnValue"
    assert step["params"]["columns"] == ["status"]
    assert step["params"]["values"] == ["active", "pending"]
    assert step["params"]["action"] == "KEEP_ROW"


def test_recipe_add_filter_rows_by_formula(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-filter-rows", "prep1",
        "--formula", "price > 100",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FilterOnFormula"
    assert step["params"]["expression"] == "price > 100"
    assert step["params"]["action"] == "REMOVE_ROW"


def test_recipe_add_fill_empty(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-fill-empty", "prep1",
        "--column", "age",
        "--value", "0",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FillEmptyWithValue"
    assert step["params"]["columns"] == ["age"]
    assert step["params"]["value"] == "0"


def test_recipe_add_delete_columns(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-delete-columns", "prep1",
        "--columns", "tmp1,tmp2,debug_col",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "ColumnsSelector"
    assert step["params"]["columns"] == ["tmp1", "tmp2", "debug_col"]
    assert step["params"]["keep"] is False


def test_recipe_add_find_replace(patch_client):
    _proj, _recipe, settings = _setup_prepare_mock(patch_client)
    result = runner.invoke(app, [
        "recipe", "add-find-replace", "prep1",
        "--column", "category",
        "--find", "Electronics",
        "--replace", "Tech",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    step = settings.obj_payload["steps"][0]
    assert step["type"] == "FindReplace"
    assert step["params"]["columns"] == ["category"]
    assert step["params"]["mapping"] == [{"from": "Electronics", "to": "Tech"}]
    assert step["params"]["matching"] == "FULL_STRING"


# ── Visual recipe: create-window with --partition-key / --order-key ────


def test_recipe_create_window_basic(patch_client):
    """Basic window recipe creation without flags."""
    result = runner.invoke(app, [
        "recipe", "create-window", "my_window",
        "-i", "transactions",
        "--output-ds", "windowed",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created window recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("window", "my_window")


def test_recipe_create_window_with_partition_key(patch_client):
    """--partition-key sets partitioningColumns in payload."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(app, [
        "recipe", "create-window", "my_window",
        "-i", "transactions",
        "--output-ds", "windowed",
        "--partition-key", "customer_id",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["partitioningColumns"] == [{"column": "customer_id"}]
    settings.save.assert_called()


def test_recipe_create_window_with_order_key(patch_client):
    """--order-key sets orders in payload (ascending by default)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(app, [
        "recipe", "create-window", "my_window",
        "-i", "transactions",
        "--output-ds", "windowed",
        "--order-key", "date",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["orders"] == [{"column": "date", "desc": False}]
    settings.save.assert_called()


def test_recipe_create_window_order_key_desc(patch_client):
    """--order-key with :desc suffix sets descending order."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(app, [
        "recipe", "create-window", "my_window",
        "-i", "transactions",
        "--output-ds", "windowed",
        "--partition-key", "customer_id",
        "--order-key", "amount:desc",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["partitioningColumns"] == [{"column": "customer_id"}]
    assert settings.obj_payload["orders"] == [{"column": "amount", "desc": True}]
    settings.save.assert_called()


def test_recipe_create_window_multiple_keys(patch_client):
    """Multiple --partition-key and --order-key flags."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value

    result = runner.invoke(app, [
        "recipe", "create-window", "my_window",
        "-i", "transactions",
        "--output-ds", "windowed",
        "--partition-key", "customer_id",
        "--partition-key", "region",
        "--order-key", "date",
        "--order-key", "amount:desc",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert settings.obj_payload["partitioningColumns"] == [
        {"column": "customer_id"}, {"column": "region"},
    ]
    assert settings.obj_payload["orders"] == [
        {"column": "date", "desc": False}, {"column": "amount", "desc": True},
    ]
