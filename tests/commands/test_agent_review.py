"""Tests for agent-review commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- list ---


def test_list(patch_client):
    result = runner.invoke(app, ["agent-review", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "review1" in result.output
    assert "Quality Check" in result.output


def test_list_json(patch_client):
    result = runner.invoke(
        app, ["agent-review", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "review1"
    assert parsed[0]["name"] == "Quality Check"


# --- create ---


def test_create(patch_client):
    result = runner.invoke(
        app, ["agent-review", "create", "My Review", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_agent_review.assert_called_once_with(
        "My Review"
    )


# --- get ---


def test_get(patch_client):
    result = runner.invoke(
        app, ["agent-review", "get", "review1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "review1"
    assert parsed["name"] == "Quality Check"


def test_get_not_found(patch_client):
    result = runner.invoke(
        app, ["agent-review", "get", "nonexistent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# --- delete ---


def test_delete(patch_client):
    result = runner.invoke(
        app, ["agent-review", "delete", "review1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0


# --- set-agent ---


def test_set_agent(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "set-agent",
            "review1",
            "--agent",
            "agent1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# --- set-llm ---


def test_set_llm(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "set-llm",
            "review1",
            "--llm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# --- add-trait ---


def test_add_trait(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "add-trait",
            "review1",
            "--name",
            "Accuracy",
            "--description",
            "Checks accuracy",
            "--criteria",
            "Answer matches reference",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    review = patch_client.get_project("PROJ1").get_agent_review("review1")
    review.add_trait.assert_called_once()
    trait_arg = review.add_trait.call_args[0][0]
    assert trait_arg["name"] == "Accuracy"
    assert trait_arg["criteria"] == "Answer matches reference"
    assert trait_arg["enabled"] is True


def test_add_trait_with_llm(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "add-trait",
            "review1",
            "--name",
            "Tone",
            "--criteria",
            "Professional tone",
            "--llm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    trait_arg = (
        patch_client.get_project("PROJ1")
        .get_agent_review("review1")
        .add_trait.call_args[0][0]
    )
    assert trait_arg["llmId"] == "openai:gpt-4o"


def test_add_trait_inherits_helper_llm(patch_client):
    """add-trait without --llm defaults llmId to the review's helper_llm_id.

    Regression: traits with null llmId crash DSS 14.5.1+ review runs with
    NullPointerException ("Cannot invoke String.startsWith because id is null").
    """
    # Fixture sets review_mock.helper_llm_id = "llm1"
    result = runner.invoke(
        app,
        [
            "agent-review",
            "add-trait",
            "review1",
            "--name",
            "Helpfulness",
            "--criteria",
            "Is the answer helpful?",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    trait_arg = (
        patch_client.get_project("PROJ1")
        .get_agent_review("review1")
        .add_trait.call_args[0][0]
    )
    assert trait_arg["llmId"] == "llm1"


def test_set_llm_backfills_null_trait_llmId(patch_client):
    """set-llm populates llmId on traits that lack one — prevents DSS 14.5.1 NPE."""
    review = patch_client.get_project("PROJ1").get_agent_review("review1")
    # Seed two traits, one with explicit llmId, one without.
    review.data["traits"] = [
        {"id": "t1", "name": "Accuracy", "llmId": "anthropic:claude-4"},
        {"id": "t2", "name": "Tone"},  # null llmId
    ]
    result = runner.invoke(
        app,
        [
            "agent-review",
            "set-llm",
            "review1",
            "--llm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Trait with null llmId got backfilled; trait with explicit llmId preserved.
    assert review.data["traits"][0]["llmId"] == "anthropic:claude-4"
    assert review.data["traits"][1]["llmId"] == "openai:gpt-4o"
    assert "auto-populated 1 trait" in result.output


# --- list-tests ---


def test_list_tests(patch_client):
    result = runner.invoke(
        app, ["agent-review", "list-tests", "review1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "test1" in result.output


def test_list_tests_json(patch_client):
    result = runner.invoke(
        app,
        ["agent-review", "list-tests", "review1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "test1"
    assert parsed[0]["query"] == "What is 2+2?"


# --- create-test ---


def test_create_test(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "create-test",
            "review1",
            "--query",
            "What is 2+2?",
            "--reference",
            "4",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent_review(
        "review1"
    ).create_test.assert_called_once_with(
        query="What is 2+2?", reference_answer="4", expectations=None
    )


def test_create_test_with_expectations(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "create-test",
            "review1",
            "-q",
            "Summarize Q4",
            "-e",
            "Should mention revenue",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# --- import-tests ---


def test_import_tests(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "import-tests",
            "review1",
            "--dataset",
            "test_questions",
            "--query-column",
            "question",
            "--reference-column",
            "answer",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "3 tests" in result.output


def test_import_tests_with_top_n(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "import-tests",
            "review1",
            "--dataset",
            "test_qs",
            "--query-column",
            "q",
            "--top-n",
            "10",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# --- export-tests ---


def test_export_tests(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "export-tests",
            "review1",
            "--dataset",
            "output_tests",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "3 tests" in result.output


# --- run ---


def test_run(patch_client):
    result = runner.invoke(
        app, ["agent-review", "run", "review1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Run complete" in result.output


def test_run_no_wait(patch_client):
    result = runner.invoke(
        app, ["agent-review", "run", "review1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Run started" in result.output
    review = patch_client.get_project("PROJ1").get_agent_review("review1")
    review.perform_run.assert_called_once_with(wait=False, run_name=None)


def test_run_with_name(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "run",
            "review1",
            "--name",
            "nightly",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# --- list-runs ---


def test_list_runs(patch_client):
    result = runner.invoke(
        app, ["agent-review", "list-runs", "review1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "run1" in result.output
    assert "COMPLETED" in result.output


def test_list_runs_json(patch_client):
    result = runner.invoke(
        app,
        ["agent-review", "list-runs", "review1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "run1"


# --- results ---


def test_results(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "results",
            "review1",
            "--run",
            "run1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "result1" in result.output
    assert "PASSED" in result.output


def test_results_json(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "results",
            "review1",
            "--run",
            "run1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "result1"
    assert parsed[0]["status"] == "PASSED"
