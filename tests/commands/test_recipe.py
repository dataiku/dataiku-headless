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
    result = runner.invoke(app, ["recipe", "get", "recipe1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "type" in parsed


def test_recipe_run(patch_client):
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_recipe_run_wait(patch_client):
    result = runner.invoke(app, ["recipe", "run", "recipe1", "--project", "PROJ1", "--wait"])
    assert result.exit_code == 0


# --- New commands ---


def test_recipe_create(patch_client):
    result = runner.invoke(app, [
        "recipe", "create", "new_recipe",
        "--type", "python",
        "--input", "input_ds",
        "--output", "output_ds",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("python", "new_recipe")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("input_ds")
    builder.with_existing_output.assert_called_once_with("output_ds")
    builder.build.assert_called_once()


def test_recipe_delete(patch_client):
    result = runner.invoke(app, ["recipe", "delete", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted recipe" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    recipe.delete.assert_called_once()


def test_recipe_set_code_inline(patch_client):
    result = runner.invoke(app, [
        "recipe", "set-code", "recipe1",
        "--code", "print('hello')",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Updated code" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.set_payload.assert_called_once_with("print('hello')")
    settings.save.assert_called()


def test_recipe_set_code_from_file(patch_client, tmp_path):
    code_file = tmp_path / "script.py"
    code_file.write_text("import dataiku\nds = dataiku.Dataset('test')")
    result = runner.invoke(app, [
        "recipe", "set-code", "recipe1",
        "--code", f"@{code_file}",
        "--project", "PROJ1",
    ])
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
    assert "import dataiku" in result.output


def test_recipe_set_definition(patch_client):
    new_def = json.dumps({"type": "sql", "customFields": {"key": "val"}})
    result = runner.invoke(app, [
        "recipe", "set-definition", "recipe1",
        "--definition", new_def,
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.save.assert_called()


def test_recipe_add_input(patch_client):
    result = runner.invoke(app, [
        "recipe", "add-input", "recipe1",
        "--ref", "extra_input",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Added input" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("main", "extra_input")
    settings.save.assert_called()


def test_recipe_add_output(patch_client):
    result = runner.invoke(app, [
        "recipe", "add-output", "recipe1",
        "--ref", "extra_output",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Added output" in result.output
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_output.assert_called_once_with("main", "extra_output")
    settings.save.assert_called()


def test_recipe_add_input_custom_role(patch_client):
    result = runner.invoke(app, [
        "recipe", "add-input", "recipe1",
        "--ref", "lookup_ds",
        "--role", "lookup",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    recipe = patch_client.get_project("PROJ1").get_recipe("recipe1")
    settings = recipe.get_settings()
    settings.add_input.assert_called_once_with("lookup", "lookup_ds")


# --- GenAI recipe creation ---


def test_recipe_create_embed(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-embed", "my_embed",
        "--input", "text_data",
        "--output-kb", "my_kb",
        "--embedding-llm", "openai:text-embedding-3-small",
        "--project", "PROJ1",
    ])
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
    result = runner.invoke(app, [
        "recipe", "create-embed", "my_embed",
        "--input", "text_data",
        "--output-kb", "my_kb",
        "--embedding-llm", "openai:text-embedding-3-large",
        "--vector-store-type", "FAISS",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-large", "FAISS"
    )


def test_recipe_create_embed_docs(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-embed-docs", "doc_embed",
        "--input", "documents",
        "--output-kb", "doc_kb",
        "--embedding-llm", "openai:text-embedding-3-small",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created embed-docs recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("embed_documents", "doc_embed")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_not_called()
    builder.with_output_knowledge_bank.assert_called_once()
    builder.build.assert_called_once()


def test_recipe_create_embed_docs_with_vlm(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-embed-docs", "doc_embed",
        "--input", "documents",
        "--output-kb", "doc_kb",
        "--embedding-llm", "openai:text-embedding-3-small",
        "--vlm", "openai:gpt-4o",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_called_once_with("openai:gpt-4o")


def test_recipe_create_extract(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-extract", "my_extract",
        "--input", "documents",
        "--output", "extracted_text",
        "--vlm", "openai:gpt-4o",
        "--project", "PROJ1",
    ])
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
    result = runner.invoke(app, [
        "recipe", "create-llm-eval", "my_eval",
        "--input", "responses",
        "--eval-store", "eval_store_1",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created LLM eval recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("nlp_llm_evaluation", "my_eval")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("responses")
    builder.with_output.assert_not_called()
    builder.with_output_metrics.assert_not_called()
    builder.with_output_evaluation_store.assert_called_once_with("eval_store_1")
    builder.build.assert_called_once()


def test_recipe_create_llm_eval_full(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-llm-eval", "rag_eval",
        "--input", "qa_data",
        "--eval-store", "eval_store_1",
        "--output", "eval_scored",
        "--output-metrics", "eval_metrics",
        "--task-type", "QUESTION_ANSWERING",
        "--metrics", "answerRelevancy,faithfulness",
        "--input-col", "question",
        "--output-col", "answer",
        "--ground-truth-col", "expected",
        "--context-col", "context",
        "--completion-llm", "openai:gpt-4o",
        "--embedding-llm", "openai:text-embedding-3-small",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_output.assert_called_once_with("eval_scored")
    builder.with_output_metrics.assert_called_once_with("eval_metrics")

    # Verify post-creation payload settings
    recipe = builder.build.return_value
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


def test_recipe_create_agent_eval_minimal(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-agent-eval", "agent_eval",
        "--input", "agent_runs",
        "--eval-store", "agent_store_1",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "Created agent eval recipe" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.new_recipe.assert_called_once_with("nlp_agent_evaluation", "agent_eval")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("agent_runs")
    builder.with_output_evaluation_store.assert_called_once_with("agent_store_1")

    # Default input format
    recipe = builder.build.return_value
    settings = recipe.get_settings.return_value
    assert settings.obj_payload["inputFormat"] == "AGENT_EXECUTION"
    settings.save.assert_called()


def test_recipe_create_agent_eval_full(patch_client):
    result = runner.invoke(app, [
        "recipe", "create-agent-eval", "agent_eval",
        "--input", "agent_runs",
        "--eval-store", "agent_store_1",
        "--output", "eval_out",
        "--output-metrics", "eval_metrics",
        "--metrics", "toolCallExactMatch,agentGoalAccuracyWithoutReference",
        "--completion-llm", "openai:gpt-4o",
        "--embedding-llm", "openai:text-embedding-3-small",
        "--input-format", "PROMPT_RECIPE",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_recipe.return_value
    builder.with_output.assert_called_once_with("eval_out")
    builder.with_output_metrics.assert_called_once_with("eval_metrics")

    recipe = builder.build.return_value
    settings = recipe.get_settings.return_value
    payload = settings.obj_payload
    assert payload["inputFormat"] == "PROMPT_RECIPE"
    assert payload["metrics"] == ["toolCallExactMatch", "agentGoalAccuracyWithoutReference"]
    assert payload["completionLLMId"] == "openai:gpt-4o"
    assert payload["embeddingLLMId"] == "openai:text-embedding-3-small"
