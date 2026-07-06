"""Tests for llm commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_llm_list(patch_client):
    result = runner.invoke(app, ["llm", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "llm1" in result.output


def test_llm_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "llm", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "llm1"


def test_llm_list_with_purpose(patch_client):
    result = runner.invoke(
        app,
        [
            "llm",
            "list",
            "--project",
            "PROJ1",
            "--purpose",
            "TEXT_EMBEDDING_EXTRACTION",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").list_llms.assert_called_with(
        purpose="TEXT_EMBEDDING_EXTRACTION"
    )


def test_llm_completion(patch_client):
    result = runner.invoke(
        app, ["llm", "completion", "llm1", "Hello", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output


def test_llm_completion_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "llm",
            "completion",
            "llm1",
            "Hello",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["text"] == "Hello from LLM"


def test_llm_completion_with_system(patch_client):
    result = runner.invoke(
        app,
        [
            "llm",
            "completion",
            "llm1",
            "Hello",
            "--project",
            "PROJ1",
            "--system",
            "You are a helpful assistant",
        ],
    )
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output
    # System messages go through with_message(role="system") — the SDK has no
    # with_system_message() method; calling it raised AttributeError at runtime.
    proj = patch_client.get_project("PROJ1")
    llm = proj.get_llm("llm1")
    completion_obj = llm.new_completion()
    completion_obj.with_message.assert_any_call(
        "You are a helpful assistant", role="system"
    )


def test_llm_completion_with_json_output_flag(patch_client):
    result = runner.invoke(
        app,
        [
            "llm",
            "completion",
            "llm1",
            "List items",
            "--project",
            "PROJ1",
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output
    # Verify the message was augmented with JSON instruction
    proj = patch_client.get_project("PROJ1")
    llm = proj.get_llm("llm1")
    completion_obj = llm.new_completion()
    call_args = completion_obj.with_message.call_args[0][0]
    assert "Respond in valid JSON format" in call_args


def test_llm_embeddings(patch_client):
    result = runner.invoke(
        app,
        [
            "llm",
            "embeddings",
            "embedding1",
            "--text",
            "Hello world",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == [[0.4, 0.5, 0.6]]
    proj = patch_client.get_project("PROJ1")
    llm = proj.get_llm("embedding1")
    llm.new_embeddings().add_text.assert_called_with("Hello world")


def test_llm_embeddings_rejects_non_embedding_model(patch_client):
    result = runner.invoke(
        app,
        [
            "llm",
            "embeddings",
            "azureopenai:Azure_AI_Connection:4o",
            "--text",
            "Hello world",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "TEXT_EMBEDDING_EXTRACTION" in result.output


def test_llm_embeddings_error_is_prescriptive_text_on_stderr(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "llm",
            "embeddings",
            "azureopenai:Azure_AI_Connection:4o",
            "--text",
            "Hello world",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "dku llm list --purpose TEXT_EMBEDDING_EXTRACTION" in result.stderr
    assert "Requested LLM ID: azureopenai:Azure_AI_Connection:4o" in result.stderr


# --- completion --json-schema ---


def test_llm_completion_json_schema(patch_client):
    """--json-schema calls with_json_output on the completion."""
    schema = json.dumps({"type": "object", "properties": {"name": {"type": "string"}}})
    result = runner.invoke(
        app,
        [
            "llm",
            "completion",
            "llm1",
            "Extract name",
            "--json-schema",
            schema,
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# --- generate-image ---


def test_llm_generate_image(patch_client):
    result = runner.invoke(
        app,
        ["llm", "generate-image", "llm1", "--prompt", "A cat", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "success" in result.output


def test_llm_generate_image_to_file(patch_client, tmp_path):
    dest = tmp_path / "test.png"
    # Make first_image return bytes for bytes mode
    img_response = (
        patch_client.get_project("PROJ1")
        .get_llm("llm1")
        .new_images_generation()
        .execute.return_value
    )
    img_response.first_image.side_effect = lambda as_type="bytes": (
        b"\x89PNG\r\n" if as_type == "bytes" else "iVBOR..."
    )
    result = runner.invoke(
        app,
        [
            "llm",
            "generate-image",
            "llm1",
            "--prompt",
            "A sunset",
            "--dest",
            str(dest),
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert dest.exists()


# --- rerank ---


def test_llm_rerank_table(patch_client):
    result = runner.invoke(
        app,
        [
            "llm",
            "rerank",
            "llm1",
            "-q",
            "best food",
            "--doc",
            "Pizza place",
            "--doc",
            "Sushi bar",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Sushi bar" in result.output  # index 1 ranked first
    assert "0.9500" in result.output


def test_llm_rerank_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "llm",
            "rerank",
            "llm1",
            "-q",
            "best food",
            "--doc",
            "Pizza",
            "--doc",
            "Sushi",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["score"] == 0.95


# --- llm endpoint ---


def test_llm_endpoint_dense(patch_client):
    result = runner.invoke(app, ["llm", "endpoint", "-P", "PROJ1"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert (
        data["base_url"]
        == "https://dss.example.com/public/api/projects/PROJ1/llms/openai/v1"
    )
    assert "Bearer" in data["auth_header"]
    # The hard-won Mesh auth gotcha must be surfaced.
    assert "x-dku-apiticket" in result.stderr


def test_llm_endpoint_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "llm", "endpoint", "-P", "PROJ1"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["base_url"].endswith("/projects/PROJ1/llms/openai/v1")
    assert data["chat_completions_url"].endswith("/chat/completions")
    assert data["models_url"].endswith("/models")


def test_llm_endpoint_strips_trailing_slash(patch_client):
    patch_client.host = "https://dss.example.com/"
    result = runner.invoke(app, ["--format", "json", "llm", "endpoint", "-P", "PROJ1"])
    data = json.loads(result.stdout)
    assert "com//public" not in data["base_url"]
