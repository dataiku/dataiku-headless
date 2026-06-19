"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

from unittest.mock import MagicMock
from tests.commands.recipe.helpers import app, runner


# --- GenAI recipe creation ---


def test_recipe_create_embed(patch_client):
    """New KB: list_knowledge_banks is empty, so with_output_knowledge_bank is used."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
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
    proj.new_recipe.assert_called_once_with("nlp_llm_rag_embedding", "my_embed")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("text_data")
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-small", "CHROMA"
    )
    builder.set_raw_mode.assert_not_called()
    builder.build.assert_called_once()


def test_recipe_create_embed_custom_vector_store(patch_client):
    """New KB with custom vector store type."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
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
    builder = proj.new_recipe.return_value
    builder.with_output_knowledge_bank.assert_called_once_with(
        "my_kb", "openai:text-embedding-3-large", "FAISS"
    )
    builder.set_raw_mode.assert_not_called()


def test_recipe_create_embed_with_embed_column(patch_client):
    """--embed-column sets knowledgeColumn in obj_payload after creation."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
    recipe_mock = proj.get_recipe.return_value
    settings_mock = recipe_mock.get_settings.return_value

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
            "--embed-column",
            "description",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "description" in result.output
    assert settings_mock.obj_payload["knowledgeColumn"] == "description"
    settings_mock.save.assert_called_once()


def test_recipe_create_embed_with_metadata_cols(patch_client):
    """--metadata-col is repeatable and writes payload.metadataColumns[]."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
    recipe_mock = proj.get_recipe.return_value
    settings_mock = recipe_mock.get_settings.return_value

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
            "--embed-column",
            "body",
            "--metadata-col",
            "title",
            "--metadata-col",
            "url",
            "--chunk-size",
            "1500",
            "--chunk-overlap",
            "150",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings_mock.obj_payload["knowledgeColumn"] == "body"
    assert settings_mock.obj_payload["metadataColumns"] == [
        {"column": "title"},
        {"column": "url"},
    ]
    assert settings_mock.obj_payload["chunkSizeCharacters"] == 1500
    assert settings_mock.obj_payload["chunkOverlapCharacters"] == 150


def test_recipe_create_embed_without_embed_column_warns(patch_client):
    """Without --embed-column, a warning is shown and save is NOT called."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
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
    assert "No --embed-column specified" in result.output
    # get_recipe should NOT have been called (no embed_column to set)
    proj.get_recipe.assert_not_called()


def test_recipe_create_embed_rejects_full_rebuild_update_method(patch_client):
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
            "--vector-store-update-method",
            "FULL_REBUILD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    patch_client.get_project("PROJ1").new_recipe.assert_not_called()


def test_recipe_create_embed_existing_kb(patch_client):
    """Existing KB: uses set_raw_mode + direct ref instead of with_output_knowledge_bank."""
    proj = patch_client.get_project("PROJ1")
    existing_kb = MagicMock()
    existing_kb.name = "my_kb"
    existing_kb.id = "existing_id_abc"
    proj.list_knowledge_banks.return_value = [existing_kb]
    builder = proj.new_recipe.return_value
    builder.recipe_proto = {"outputs": {}}
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
    assert "Using existing knowledge bank" in result.output
    assert "existing_id_abc" in result.output
    builder.with_output_knowledge_bank.assert_not_called()
    builder.set_raw_mode.assert_called_once()
    assert builder.recipe_proto["outputs"]["knowledge_bank"] == {
        "items": [{"ref": "existing_id_abc", "appendMode": False}]
    }
    builder.build.assert_called_once()
    assert "No --embed-column specified" in result.output
    proj.get_recipe.assert_not_called()


def test_recipe_create_embed_docs(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
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
    proj.new_recipe.assert_called_once_with("embed_documents", "doc_embed")
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_not_called()
    builder.with_output_knowledge_bank.assert_called_once()
    builder.set_raw_mode.assert_not_called()
    builder.build.assert_called_once()


def test_recipe_create_embed_docs_with_vlm(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
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
    builder = proj.new_recipe.return_value
    builder.with_vlm.assert_called_once_with("openai:gpt-4o")


def test_recipe_create_embed_docs_existing_kb_seeds_payload(patch_client):
    """Existing KB raw-mode creation must still save a non-null visual payload."""
    proj = patch_client.get_project("PROJ1")
    existing_kb = MagicMock()
    existing_kb.name = "doc_kb"
    existing_kb.id = "existing_kb_id"
    proj.list_knowledge_banks.return_value = [existing_kb]
    builder = proj.new_recipe.return_value
    builder.recipe_proto = {"outputs": {}}
    recipe_obj = proj.get_recipe.return_value
    settings = recipe_obj.get_settings.return_value
    settings.obj_payload = {}
    raw_def: dict = {"inputs": {"main": {"items": [{"ref": "folder1"}]}}}
    settings.get_recipe_raw_definition.return_value = raw_def

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input-folder",
            "Data Folder",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Using existing knowledge bank" in result.output
    assert settings.obj_payload["chunkSizeCharacters"] == 3000
    assert settings.obj_payload["vectorStoreUpdateMethod"] == "SMART_OVERWRITE"
    assert raw_def["inputs"]["main"]["items"][0]["ref"] == "folder1"
    assert builder.recipe_proto["outputs"]["knowledge_bank"]["items"][0]["ref"] == (
        "existing_kb_id"
    )
    settings.save.assert_called()


def test_recipe_create_embed_docs_requires_input_or_folder(patch_client):
    """Neither --input nor --input-folder ⇒ prescriptive error."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--input" in result.output and "--input-folder" in result.output


def test_recipe_create_embed_docs_folder_only_rewires_main(patch_client):
    """--input-folder alone ⇒ inputs.main repointed to the folder (DSS 14.5+ pattern)."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
    # Capture the settings object we can inspect after the rewire.
    recipe_obj = proj.get_recipe.return_value
    settings = recipe_obj.get_settings.return_value
    raw_def: dict = {"inputs": {"main": {"items": [{"ref": "FOLDER_42"}]}}}
    settings.get_recipe_raw_definition.return_value = raw_def

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input-folder",
            "FOLDER_42",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    # The post-build rewire wrote inputs.main with the resolved folder ID.
    assert raw_def["inputs"]["main"]["items"][0]["ref"] == "folder1"
    settings.save.assert_called()


def test_recipe_create_embed_docs_resolves_folder_names(patch_client):
    """Managed-folder names are resolved before writing recipe refs."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
    recipe_obj = proj.get_recipe.return_value
    settings = recipe_obj.get_settings.return_value
    raw_def: dict = {"inputs": {"main": {"items": [{"ref": "Data Folder"}]}}}
    settings.get_recipe_raw_definition.return_value = raw_def

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input-folder",
            "Data Folder",
            "--output-images-folder",
            "Data Folder",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("folder1")
    assert raw_def["inputs"]["main"]["items"][0]["ref"] == "folder1"
    assert raw_def["outputs"]["images"]["items"][0]["ref"] == "folder1"
    settings.save.assert_called()


def test_recipe_create_embed_docs_legacy_folder_role_resolves_name(patch_client):
    """--input plus --input-folder writes the legacy documents role with folder ID."""
    proj = patch_client.get_project("PROJ1")
    proj.list_knowledge_banks.return_value = []
    recipe_obj = proj.get_recipe.return_value
    settings = recipe_obj.get_settings.return_value
    raw_def: dict = {"inputs": {"main": {"items": [{"ref": "documents"}]}}}
    settings.get_recipe_raw_definition.return_value = raw_def

    result = runner.invoke(
        app,
        [
            "recipe",
            "create-embed-docs",
            "doc_embed",
            "--input",
            "documents",
            "--input-folder",
            "Data Folder",
            "--output-kb",
            "doc_kb",
            "--embedding-llm",
            "openai:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw_def["inputs"]["documents"]["items"][0]["ref"] == "folder1"
    settings.save.assert_called()


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
    proj = patch_client.get_project("PROJ1")
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
    proj.new_recipe.assert_called_once_with("nlp_llm_evaluation", "my_eval")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("responses")
    builder.with_output_evaluation_store.assert_called_once_with("eval_store_1")
    builder.with_output.assert_not_called()
    builder.with_output_metrics.assert_not_called()
    builder.build.assert_called_once()


def test_recipe_create_llm_eval_full(patch_client):
    proj = patch_client.get_project("PROJ1")
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
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("qa_data")
    builder.with_output_evaluation_store.assert_called_once_with("eval_store_1")
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


def test_recipe_create_llm_eval_initializes_missing_payload(patch_client):
    from unittest.mock import PropertyMock

    proj = patch_client.get_project("PROJ1")
    recipe = proj.new_recipe.return_value.build.return_value
    settings = recipe.get_settings.return_value
    # obj_payload is a read-only property that returns None (no payload yet)
    type(settings).obj_payload = PropertyMock(return_value=None)
    # Provide raw_params dict so _get_recipe_payload can write to it
    settings.raw_params = {}

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
    # _get_recipe_payload falls through to raw_params when obj_payload is None
    assert settings.raw_params["payload"]["taskType"] == "QUESTION_ANSWERING"
    settings.save.assert_called()


def test_recipe_create_llm_eval_requires_existing_output_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")
    dataset_mock = proj.get_dataset("eval_scored")
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
    proj.new_recipe.assert_not_called()


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
    proj.new_recipe.assert_not_called()


def test_recipe_create_llm_eval_preserves_non_not_found_dataset_errors(patch_client):
    proj = patch_client.get_project("PROJ1")
    dataset_mock = proj.get_dataset("eval_scored")
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
    proj.new_recipe.assert_not_called()


def test_recipe_create_agent_eval_minimal(patch_client):
    proj = patch_client.get_project("PROJ1")
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
    proj.new_recipe.assert_called_once_with("nlp_agent_evaluation", "agent_eval")
    builder = proj.new_recipe.return_value
    builder.with_input.assert_called_once_with("agent_runs")
    builder.with_output_evaluation_store.assert_called_once_with("agent_store_1")

    # Default input format
    recipe = builder.build.return_value
    settings = recipe.get_settings.return_value
    assert settings.obj_payload["inputFormat"] == "AGENT_EXECUTION"
    settings.save.assert_called()


def test_recipe_create_agent_eval_requires_existing_output_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")
    dataset_mock = proj.get_dataset("eval_out")
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
    proj.new_recipe.assert_not_called()


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
    proj.new_recipe.assert_not_called()


def test_recipe_create_agent_eval_full(patch_client):
    proj = patch_client.get_project("PROJ1")
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
    builder = proj.new_recipe.return_value
    builder.with_output.assert_called_once_with("eval_out")
    builder.with_output_metrics.assert_called_once_with("eval_metrics")

    recipe = builder.build.return_value
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
    # get_recipe() is lazy; the existence check happens on get_settings()
    patch_client.get_project(
        "PROJ1"
    ).get_recipe.return_value.get_settings.side_effect = Exception("'recipe'")
    result = runner.invoke(
        app,
        ["--format", "json", "recipe", "get", "missing_recipe", "--project", "PROJ1"],
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    assert "Recipe 'missing_recipe' not found in project 'PROJ1'." in result.stderr
    assert "List recipes: dku recipe list -P PROJ1" in result.stderr
    assert "Inspect the project flow: dku project inspect PROJ1" in result.stderr


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
            "--format",
            "json",
            "recipe",
            "check-schema",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "totalIncompatibilities" in result.output


def test_recipe_apply_schema_no_changes(patch_client):
    """apply-schema does nothing when no changes needed."""
    # apply-schema now refuses code recipes (the default fixture types recipe1
    # as python); type it as a visual recipe so the compute/apply path runs.
    settings = patch_client.get_project("PROJ1").get_recipe("recipe1").get_settings()
    settings.get_recipe_raw_definition.return_value = {"type": "grouping"}
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
    # Visual recipe type so apply-schema doesn't refuse it as a code recipe.
    recipe_mock.get_settings().get_recipe_raw_definition.return_value = {
        "type": "grouping"
    }
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


# ── NET-NEW (PR surface): apply-schema refuses code recipes ───────────


def test_recipe_apply_schema_rejects_python_recipe(patch_client):
    """apply-schema on a Python recipe emits prescriptive guidance (not raw exception)."""
    # Default fixture has recipe1 typed as "python" — no override needed.
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
    assert result.exit_code == 2
    output = result.output.lower()
    # Rich wraps long lines; check unwrappable tokens.
    assert "write_with_schema" in output
    assert "dku recipe run" in output


# ── Visual recipe: create-join ────────────────────────────────────────
