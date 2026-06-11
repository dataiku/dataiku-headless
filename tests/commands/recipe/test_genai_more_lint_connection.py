"""Recipe command tests split from tests/commands/test_recipe.py."""

from __future__ import annotations

import json

from tests.commands.recipe.helpers import app, runner
from tests.helpers import strip_ansi


def test_recipe_create_eda_univariate_basic(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.create_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-eda-univariate",
            "stats",
            "-i",
            "clinical",
            "--output-ds",
            "stats_out",
            "--analyse",
            "VISIT:CATEGORICAL",
            "--analyse",
            "AVAL:NUMERICAL",
            "--with-frequency-table",
            "--with-quantile-table",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = settings.obj_payload
    assert payload["withFrequencyTable"] is True
    assert payload["withQuantileTable"] is True
    assert payload["withSummaryStats"] is True
    analyses = payload["analyses"]
    assert len(analyses) == 2
    assert analyses[0]["column"] == {"name": "VISIT", "type": "CATEGORICAL"}
    assert analyses[0]["frequencyTable"] is True
    assert analyses[0]["quantileTable"] is False
    assert analyses[1]["column"] == {"name": "AVAL", "type": "NUMERICAL"}
    assert analyses[1]["quantileTable"] is True
    assert analyses[1]["frequencyTable"] is False


def test_recipe_create_eda_univariate_invalid_type(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-eda-univariate",
            "stats",
            "-i",
            "clinical",
            "--output-ds",
            "out",
            "--analyse",
            "VISIT:WIBBLE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "WIBBLE" in result.output


def test_recipe_create_sql_script_basic(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = ""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sql-script",
            "setup",
            "--connection",
            "prod_pg",
            "--sql",
            "CREATE TABLE foo (id INT); INSERT INTO foo VALUES (1);",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output


def test_recipe_create_sql_script_statements_mode_case_insensitive(patch_client):
    """--statements-mode is the StatementsMode click.Choice (case_sensitive=False):
    lowercase input parses and the canonical uppercase value lands in the params."""
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_recipe.return_value.get_settings.return_value
    settings.obj_payload = ""
    # The command writes recipe params through the ATTACHED raw definition
    # (_get_or_create_recipe_params), so capture mutations via the raw dict.
    raw_def: dict = {"type": "sql_script"}
    settings.get_recipe_raw_definition.return_value = raw_def
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sql-script",
            "setup",
            "--connection",
            "prod_pg",
            "--sql",
            "CREATE TABLE foo (id INT);",
            "--statements-mode",
            "split",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw_def["params"]["statementsParsingMode"] == "SPLIT"


def test_recipe_create_sql_script_statements_mode_invalid_rejected(patch_client):
    """An invalid --statements-mode is rejected at parse time (exit 2) by the
    StatementsMode click.Choice, never reaching the recipe builder."""
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-sql-script",
            "setup",
            "--connection",
            "prod_pg",
            "--sql",
            "CREATE TABLE foo (id INT);",
            "--statements-mode",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    proj.get_recipe.assert_not_called()


def test_recipe_create_generate_features(patch_client):
    proj = patch_client.get_project("PROJ1")
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-generate-features",
            "autof",
            "-i",
            "raw",
            "--output-ds",
            "raw_with_features",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj.new_recipe.assert_called_with("generate_features", "autof")


def test_recipe_create_llm_classify_basic(patch_client):
    proj = patch_client.get_project("PROJ1")
    # _raw_create_recipe returns proj.create_recipe(...), not proj.get_recipe
    settings = proj.create_recipe.return_value.get_settings.return_value
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-classify",
            "classify_orders",
            "-i",
            "orders",
            "--output-ds",
            "orders_classified",
            "--completion-llm",
            "openai:gpt-4o-mini",
            "--input-col",
            "description",
            "--class",
            "urgent",
            "--class",
            "routine",
            "--class",
            "scheduled",
            "--explain-output",
            "--example",
            "Replace the conveyor belt motor immediately||urgent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = settings.obj_payload
    # DSS expects possibleClasses as [{"label": ...}], not flat strings
    assert payload["possibleClasses"] == [
        {"label": "urgent"},
        {"label": "routine"},
        {"label": "scheduled"},
    ]
    assert payload["completionLLMId"] == "openai:gpt-4o-mini"
    assert payload["inputColumnName"] == "description"
    assert payload["explainOutput"] is True
    assert len(payload["examples"]) == 1
    assert payload["examples"][0]["input"].startswith("Replace the conveyor")
    assert payload["examples"][0]["output"] == "urgent"


def test_recipe_create_llm_classify_requires_two_classes(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-classify",
            "classify",
            "-i",
            "in_ds",
            "--output-ds",
            "out",
            "--completion-llm",
            "x",
            "--input-col",
            "txt",
            "--class",
            "one",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "two --class" in result.output or "at least two" in result.output


def test_recipe_create_prompt_text(patch_client):
    proj = patch_client.get_project("PROJ1")
    settings = (
        proj.new_recipe.return_value.create.return_value.get_settings.return_value
    )
    settings.obj_payload = {}
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-prompt",
            "summarise",
            "-i",
            "articles",
            "--output-ds",
            "summaries",
            "--completion-llm",
            "openai:gpt-4o-mini",
            "--prompt",
            "Summarize:\n\n{{body}}",
            "--system-prompt",
            "You are concise.",
            "--input-var",
            "body=article_body",
            "--response-format",
            "json",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    p = settings.obj_payload
    assert p["llmId"] == "openai:gpt-4o-mini"
    assert "completionLLMId" not in p
    assert p["prompt"]["promptMode"] == "PROMPT_TEMPLATE_TEXT"
    assert p["prompt"]["textPromptTemplate"] == "Summarize:\n\n{{body}}"
    assert p["prompt"]["textPromptSystemTemplate"] == "You are concise."
    assert p["prompt"]["textPromptTemplateInputs"][0] == {
        "name": "body",
        "datasetColumnName": "article_body",
        "type": "TEXT",
    }
    assert p["completionSettings"]["responseFormat"] == {"type": "json"}


def test_recipe_create_prompt_requires_prompt(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-prompt",
            "p",
            "-i",
            "in_ds",
            "--output-ds",
            "out",
            "--completion-llm",
            "x",
            "--project",
            "PROJ1",
        ],
    )
    # --prompt is now REQUIRED; Typer/click exits 2 with a rich-formatted
    # "Missing option" error. The literal '--prompt' can be split by ANSI
    # escape sequences in the rendered output, so strip them before asserting.
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Missing option" in stripped and "--prompt" in stripped


def test_recipe_create_llm_classify_invalid_example_format(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-llm-classify",
            "classify",
            "-i",
            "in_ds",
            "--output-ds",
            "out",
            "--completion-llm",
            "x",
            "--input-col",
            "txt",
            "--class",
            "a",
            "--class",
            "b",
            "--example",
            "no-separator",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "TEXT||LABEL" in result.output


def test_recipe_create_join_right_limit_invalid_keep(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-join",
            "j",
            "-i",
            "a",
            "-i",
            "b",
            "--output-ds",
            "joined",
            "--right-limit-keep",
            "KEEP_RANDOM",
            "--project",
            "PROJ1",
        ],
    )
    # --right-limit-keep is a click.Choice enum: invalid values exit 2 with a
    # rich-formatted "Invalid value" message (not a bespoke exit-1 error).
    assert result.exit_code == 2
    assert "Invalid value" in result.output


# ── lint-formula / lint-sql / lint-python ───────────────────────────────


def _set_recipe_status(patch_client, severity, messages, actual_type="prepare"):
    """Configure the shared recipe mock's status + raw type for lint tests."""
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe("r")
    recipe.get_settings().get_recipe_raw_definition.return_value = {
        "type": actual_type,
        "name": "r",
    }
    status = recipe.get_status()
    status.get_status_severity.return_value = severity
    status.get_status_messages.return_value = messages
    return recipe


def test_recipe_lint_formula_clean(patch_client):
    _set_recipe_status(patch_client, "SUCCESS", [], actual_type="shaker")
    result = runner.invoke(
        app, ["recipe", "lint-formula", "my_prepare", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Linting formula recipe 'my_prepare' (type: shaker)" in result.output
    assert "No errors or warnings found." in result.output


def test_recipe_lint_formula_with_errors(patch_client):
    _set_recipe_status(
        patch_client,
        "ERROR",
        [
            {
                "severity": "ERROR",
                "code": "FORMULA_BAD",
                "title": "Invalid formula",
                "message": "Unknown column 'foo'",
            },
            {
                "severity": "WARNING",
                "code": "PERF",
                "title": "Slow step",
                "message": "consider indexing",
            },
        ],
        actual_type="shaker",
    )
    result = runner.invoke(
        app, ["recipe", "lint-formula", "my_prepare", "--project", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "Found 1 error(s):" in result.output
    assert "[FORMULA_BAD] Invalid formula: Unknown column 'foo'" in result.output
    assert "Plus 1 warning(s)" in result.output


def test_recipe_lint_formula_warnings_only(patch_client):
    _set_recipe_status(
        patch_client,
        "WARNING",
        [
            {
                "severity": "WARNING",
                "code": "PERF",
                "title": "Slow step",
                "message": "consider indexing",
            }
        ],
        actual_type="shaker",
    )
    result = runner.invoke(
        app, ["recipe", "lint-formula", "my_prepare", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Found 1 warning(s):" in result.output
    assert "[PERF] Slow step: consider indexing" in result.output


def test_recipe_lint_formula_json(patch_client):
    _set_recipe_status(
        patch_client,
        "ERROR",
        [{"severity": "ERROR", "code": "X", "title": "t", "message": "m"}],
        actual_type="shaker",
    )
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "recipe",
            "lint-formula",
            "my_prepare",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    parsed = json.loads(result.output[result.output.index("{") :])
    assert parsed["recipe"] == "my_prepare"
    assert parsed["type"] == "shaker"
    assert parsed["severity"] == "ERROR"
    assert parsed["lint_passed"] is False
    assert parsed["messages"][0]["code"] == "X"


def test_recipe_lint_sql_clean(patch_client):
    _set_recipe_status(patch_client, "SUCCESS", [], actual_type="sql_query")
    result = runner.invoke(
        app, ["recipe", "lint-sql", "my_query", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Linting SQL recipe 'my_query' (type: sql_query)" in result.output
    assert "No errors or warnings found." in result.output


def test_recipe_lint_sql_json_passed(patch_client):
    _set_recipe_status(patch_client, "SUCCESS", [], actual_type="sql_query")
    result = runner.invoke(
        app,
        ["--format", "json", "recipe", "lint-sql", "my_query", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output[result.output.index("{") :])
    assert parsed["lint_passed"] is True
    assert parsed["severity"] == "SUCCESS"


def test_recipe_lint_python_clean(patch_client):
    _set_recipe_status(patch_client, "SUCCESS", [], actual_type="python")
    result = runner.invoke(
        app, ["recipe", "lint-python", "my_script", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Linting Python recipe 'my_script' (type: python)" in result.output
    assert "No errors or warnings found." in result.output


def test_recipe_lint_python_fatal_error(patch_client):
    _set_recipe_status(
        patch_client,
        "FATAL",
        [
            {
                "severity": "FATAL",
                "code": "ENV_MISSING",
                "title": "Code env missing",
                "message": "env 'py39' not found",
            }
        ],
        actual_type="python",
    )
    result = runner.invoke(
        app, ["recipe", "lint-python", "my_script", "--project", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "Found 1 error(s):" in result.output
    assert "[ENV_MISSING] Code env missing: env 'py39' not found" in result.output


def test_recipe_lint_python_not_found(patch_client):
    proj = patch_client.get_project("PROJ1")
    recipe = proj.get_recipe("ghost")
    recipe.get_settings.side_effect = KeyError("recipe")
    result = runner.invoke(
        app, ["recipe", "lint-python", "ghost", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output


# ── --connection on visual create-* (in-database pipelines) ───────────────


def test_recipe_create_join_with_connection_uses_with_new_output(patch_client):
    """--connection creates the output managed on that connection (one-call
    in-DB pipelines) instead of the pre-create + with_existing_output dance."""
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
            "joined_sf",
            "--connection",
            "Snowflake-Conn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = patch_client.get_project("PROJ1").new_recipe.return_value
    builder.with_new_output.assert_called_once_with("joined_sf", "Snowflake-Conn")
    builder.with_existing_output.assert_not_called()


def test_recipe_create_prepare_with_connection_short_flag(patch_client):
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-prepare",
            "prep_x",
            "-i",
            "orders",
            "--output-ds",
            "prep_sf",
            "-c",
            "Snowflake-Conn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = patch_client.get_project("PROJ1").new_recipe.return_value
    builder.with_new_output.assert_called_once_with("prep_sf", "Snowflake-Conn")


def test_recipe_create_group_without_connection_keeps_default_path(patch_client):
    """Without --connection the output is ensured + attached as before."""
    result = runner.invoke(
        app,
        [
            "recipe",
            "create-group",
            "grp_x",
            "-i",
            "orders",
            "-k",
            "region",
            "--output-ds",
            "grouped",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = patch_client.get_project("PROJ1").new_recipe.return_value
    builder.with_existing_output.assert_called_once_with("grouped")
    builder.with_new_output.assert_not_called()
