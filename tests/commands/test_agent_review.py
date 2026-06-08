"""Tests for agent-review commands."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _result_mock(patch_client):
    """The shared conftest result mock (reached via the run handle)."""
    return (
        patch_client.get_project("PROJ1")
        .get_agent_review("review1")
        .get_run("run1")
        .get_result("result1")
    )


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
    # Default wiring must be sent explicitly (DSS defaults are needsReference=True,
    # needsExpectations=False — we send them so behavior is deterministic).
    assert trait_arg["needsReference"] is True
    assert trait_arg["needsExpectations"] is False


def test_add_trait_no_needs_reference(patch_client):
    """Tone-style traits opt out of requiring a reference answer."""
    result = runner.invoke(
        app,
        [
            "agent-review",
            "add-trait",
            "review1",
            "--name",
            "Tone",
            "--criteria",
            "Is the response professional and courteous?",
            "--no-needs-reference",
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
    assert trait_arg["needsReference"] is False
    assert trait_arg["needsExpectations"] is False
    assert "judge sees: neither" in result.output


def test_add_trait_needs_expectations(patch_client):
    """Expectation-scored traits wire the test's expectations to the judge."""
    result = runner.invoke(
        app,
        [
            "agent-review",
            "add-trait",
            "review1",
            "--name",
            "Coverage",
            "--criteria",
            "Does the answer satisfy the stated requirements?",
            "--needs-expectations",
            "--no-needs-reference",
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
    assert trait_arg["needsReference"] is False
    assert trait_arg["needsExpectations"] is True
    assert "judge sees: expectations" in result.output


def test_add_trait_warns_on_expectations_mismatch(patch_client):
    """Criteria names expectations but the flag is off -> prescriptive nudge."""
    result = runner.invoke(
        app,
        [
            "agent-review",
            "add-trait",
            "review1",
            "--name",
            "Coverage",
            "--criteria",
            "Does the answer satisfy the stated expectations?",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "--needs-expectations" in result.output


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


def test_run_auto_publishes_missing_review_agent_version(patch_client):
    review = patch_client.get_project("PROJ1").get_agent_review("review1")
    review.data.pop("agentVersion", None)

    result = runner.invoke(
        app, ["agent-review", "run", "review1", "--no-wait", "--project", "PROJ1"]
    )

    assert result.exit_code == 0
    agent_raw = (
        patch_client.get_project("PROJ1").get_agent("agent1").get_settings().get_raw()
    )
    assert [v["versionId"] for v in agent_raw["versions"]] == ["v1", "v2"]
    assert review.data["agentVersion"] == "v2"
    patch_client.get_project("PROJ1").get_saved_model(
        "agent1"
    ).set_active_version.assert_called_with("v2")
    review.perform_run.assert_called_once_with(wait=False, run_name=None)


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


def test_results_by_trait(patch_client):
    """--by-trait pivots per-trait pass/fail from aiStatusPerTraitId."""
    result = runner.invoke(
        app,
        [
            "agent-review",
            "results",
            "review1",
            "--run",
            "run1",
            "--by-trait",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Trait column headers are surfaced from the review definition.
    assert "Accuracy" in result.output or "ACCURACY" in result.output
    assert "Tone" in result.output or "TONE" in result.output


def test_results_by_trait_json(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "results",
            "review1",
            "--run",
            "run1",
            "--by-trait",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    # Each result row has per-trait status. Dict-shaped trait value unwraps to status.
    assert parsed[0]["Accuracy"] == "PASSED"
    assert parsed[0]["Tone"] == "FAILED"


def test_results_show_justifications_implies_by_trait(patch_client):
    """--show-justifications adds the justifications field and forces pivot."""
    result = runner.invoke(
        app,
        [
            "agent-review",
            "results",
            "review1",
            "--run",
            "run1",
            "--show-justifications",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "justifications" in parsed[0]
    # The dict-shaped trait carried a justification.
    assert "matches the reference" in parsed[0]["justifications"]["trait_accuracy"]


# --- compare ---


def test_compare_runs(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "compare",
            "review1",
            "--runs",
            "run1,run2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    # Both run IDs appear as column headers.
    assert "run1" in result.output.lower() or "RUN1" in result.output
    assert "run2" in result.output.lower() or "RUN2" in result.output
    # Trait names appear as row labels.
    assert "Accuracy" in result.output


def test_compare_runs_json(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "compare",
            "review1",
            "--runs",
            "run1,run2",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["review_id"] == "review1"
    assert parsed["runs"] == ["run1", "run2"]
    # Tone trait: run1 = 0/1 = 0%, run2 = 1/1 = 100%
    tone = next(t for t in parsed["traits"] if t["trait_name"] == "Tone")
    assert tone["per_run"]["run1"]["passed"] == 0
    assert tone["per_run"]["run1"]["total"] == 1
    assert tone["per_run"]["run2"]["passed"] == 1


def test_compare_requires_two_runs(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-review",
            "compare",
            "review1",
            "--runs",
            "run1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "at least two runs" in result.output or "Compare needs" in result.output


# --- get-result (human verification view) ---


def test_get_result(patch_client):
    with patch(
        "dku_cli.commands.agent_review._get_result",
        return_value=_result_mock(patch_client),
    ):
        result = runner.invoke(
            app, ["agent-review", "get-result", "result1", "--project", "PROJ1"]
        )
    assert result.exit_code == 0
    # Trait names resolved via the parent review, and the human review surfaces.
    assert "Accuracy" in result.output
    assert "Tone" in result.output
    assert "SME confirms" in result.output


def test_get_result_json(patch_client):
    with patch(
        "dku_cli.commands.agent_review._get_result",
        return_value=_result_mock(patch_client),
    ):
        result = runner.invoke(
            app,
            [
                "agent-review",
                "get-result",
                "result1",
                "--project",
                "PROJ1",
                "-o",
                "json",
            ],
        )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "result1"
    traits = {t["trait"]: t for t in parsed["traits"]}
    # Tone: AI said FAILED, human override flipped FINAL to PASSED → overridden.
    assert traits["Tone"]["ai_status"] == "FAILED"
    assert traits["Tone"]["final_status"] == "PASSED"
    assert traits["Tone"]["overridden"] is True
    assert traits["Accuracy"]["overridden"] is False
    assert parsed["human_reviews"][0]["verdict"] == "PASS"
    assert parsed["trait_overrides"][0]["verdict"] == "FAIL"


# --- verify (human review write) ---


def test_verify_pass(patch_client):
    mock_res = _result_mock(patch_client)
    with patch("dku_cli.commands.agent_review._get_result", return_value=mock_res):
        result = runner.invoke(
            app,
            [
                "agent-review",
                "verify",
                "result1",
                "--pass",
                "-c",
                "looks good",
                "--project",
                "PROJ1",
            ],
        )
    assert result.exit_code == 0
    mock_res.create_human_review.assert_called_once_with(
        comment="looks good", like=True
    )
    assert "verdict=PASS" in result.output


def test_verify_fail_no_comment(patch_client):
    mock_res = _result_mock(patch_client)
    with patch("dku_cli.commands.agent_review._get_result", return_value=mock_res):
        result = runner.invoke(
            app,
            ["agent-review", "verify", "result1", "--fail", "--project", "PROJ1"],
        )
    assert result.exit_code == 0
    mock_res.create_human_review.assert_called_once_with(comment=None, like=False)


def test_verify_requires_verdict_or_comment(patch_client):
    """No verdict and no comment → prescriptive error, nothing written."""
    result = runner.invoke(
        app, ["agent-review", "verify", "result1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "--pass or --fail" in result.output


# --- override-trait (per-trait human override) ---


def test_override_trait(patch_client):
    mock_res = _result_mock(patch_client)
    with patch("dku_cli.commands.agent_review._get_result", return_value=mock_res):
        result = runner.invoke(
            app,
            [
                "agent-review",
                "override-trait",
                "result1",
                "--trait",
                "trait_tone",
                "--fail",
                "--project",
                "PROJ1",
            ],
        )
    assert result.exit_code == 0
    mock_res.create_trait_override.assert_called_once_with("trait_tone", like=False)
    assert "trait_tone" in result.output


def test_override_trait_requires_verdict(patch_client):
    """--trait given but no --pass/--fail → typer rejects (required)."""
    result = runner.invoke(
        app,
        [
            "agent-review",
            "override-trait",
            "result1",
            "--trait",
            "trait_tone",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
