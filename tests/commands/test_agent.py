"""Tests for agent commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _wire_code_agent_saved_model(patch_client, inline_versions, *, active="v1"):
    """Wire proj1.get_saved_model to a saved model whose get_raw() returns a
    single mutable dict (shared across get_settings() calls, mirroring DSS's
    GET → mutate → PUT → GET round-trip)."""
    sm_raw = {"activeVersion": active, "inlineVersions": inline_versions}
    sm_settings = MagicMock()
    sm_settings.get_raw.return_value = sm_raw
    sm_settings.save.return_value = None
    sm = MagicMock()
    sm.get_settings.return_value = sm_settings
    sm.set_active_version.return_value = None
    proj1 = patch_client.get_project("PROJ1")
    proj1.get_saved_model.side_effect = None
    proj1.get_saved_model.return_value = sm
    return sm, sm_settings, sm_raw


def test_agent_set_code_happy(patch_client):
    """set-code mutates the active inline version's code in place + round-trips."""
    sm, sm_settings, sm_raw = _wire_code_agent_saved_model(
        patch_client, [{"versionId": "v1", "code": "old"}]
    )
    sm_raw["savedModelType"] = "PYTHON_AGENT"
    result = runner.invoke(
        app,
        ["agent", "set-code", "agent1", "-f", "def process(): return 1", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    sm_settings.save.assert_called_once()
    assert sm_raw["inlineVersions"][0]["code"] == "def process(): return 1"


def test_agent_set_code_new_version_activate(patch_client):
    """--new-version appends a fresh version; --activate flips the active pointer."""
    sm, sm_settings, sm_raw = _wire_code_agent_saved_model(
        patch_client, [{"versionId": "v1", "code": "old"}]
    )
    sm_raw["savedModelType"] = "PYTHON_AGENT"
    result = runner.invoke(
        app,
        [
            "agent",
            "set-code",
            "agent1",
            "-f",
            "new",
            "--new-version",
            "--activate",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(sm_raw["inlineVersions"]) == 2
    assert sm_raw["inlineVersions"][1]["versionId"] == "v2"
    assert sm_raw["inlineVersions"][1]["code"] == "new"
    sm.set_active_version.assert_called_once_with("v2")


def test_agent_set_code_rejects_non_python_agent(patch_client):
    """A non-PYTHON_AGENT is rejected up front, before any save()."""
    sm, sm_settings, sm_raw = _wire_code_agent_saved_model(
        patch_client, [{"versionId": "v1"}]
    )
    sm_raw["savedModelType"] = "TOOLS_USING_AGENT"
    result = runner.invoke(
        app, ["agent", "set-code", "agent1", "-f", "x=1", "-P", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "TOOLS_USING_AGENT" in result.output
    assert "PYTHON_AGENT" in result.output
    sm_settings.save.assert_not_called()


def test_agent_set_code_no_inline_versions(patch_client):
    """An agent with no inline versions is not a Code Agent → prescriptive error."""
    sm, sm_settings, sm_raw = _wire_code_agent_saved_model(patch_client, [])
    result = runner.invoke(
        app, ["agent", "set-code", "agent1", "-f", "x=1", "-P", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "not a Code Agent" in result.output
    sm_settings.save.assert_not_called()


def test_agent_set_code_activate_requires_new_version(patch_client):
    """--activate without --new-version is rejected before touching DSS."""
    result = runner.invoke(
        app, ["agent", "set-code", "agent1", "-f", "x=1", "--activate", "-P", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "requires --new-version" in result.output


def test_agent_list(patch_client):
    result = runner.invoke(app, ["agent", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "agent1" in result.output


def test_agent_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "agent", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "agent1"
    assert parsed[0]["name"] == "My Agent"


def test_agent_create(patch_client):
    result = runner.invoke(app, ["agent", "create", "My Agent", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_agent.assert_called_once_with(
        "My Agent", type="TOOLS_USING_AGENT"
    )


def test_agent_create_prints_id_as_data(patch_client):
    """The created agent is data on stdout — `$(... | jq -r .id)` must work."""
    result = runner.invoke(app, ["agent", "create", "My Agent", "--project", "PROJ1"])
    assert result.exit_code == 0
    created = json.loads(result.stdout.strip().splitlines()[0])
    assert created == {
        "id": "new_agent_1",
        "name": "My Agent",
        "type": "TOOLS_USING_AGENT",
    }


def test_agent_create_custom_type(patch_client):
    result = runner.invoke(
        app,
        ["agent", "create", "My Agent", "--type", "PYTHON_AGENT", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_agent.assert_called_once_with(
        "My Agent", type="PYTHON_AGENT"
    )


def test_agent_create_type_case_insensitive(patch_client):
    result = runner.invoke(
        app,
        ["agent", "create", "My Agent", "--type", "structured_agent", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_agent.assert_called_once_with(
        "My Agent", type="STRUCTURED_AGENT"
    )


def test_agent_create_invalid_type_fails_at_parse(patch_client):
    result = runner.invoke(
        app,
        ["agent", "create", "My Agent", "--type", "VISUAL_AGENT", "-P", "PROJ1"],
    )
    assert result.exit_code == 2
    assert "structured_agent" in result.output.lower()
    patch_client.get_project("PROJ1").create_agent.assert_not_called()


def test_agent_get(patch_client):
    result = runner.invoke(app, ["agent", "get", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "agent1" in result.output


def test_agent_get_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "agent", "get", "agent1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "agent1"


def test_agent_delete(patch_client):
    result = runner.invoke(
        app, ["agent", "delete", "agent1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").delete.assert_called_once()


def test_agent_wake_up(patch_client):
    result = runner.invoke(app, ["agent", "wake-up", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").wake_up.assert_called_once()


def test_agent_shutdown(patch_client):
    result = runner.invoke(app, ["agent", "shutdown", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").shutdown.assert_called_once()


def test_agent_status(patch_client):
    result = runner.invoke(app, ["agent", "status", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "RUNNING" in result.output


def test_agent_status_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "agent", "status", "agent1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["state"] == "RUNNING"


def test_agent_add_tool_idempotent(patch_client):
    """Re-adding the same tool is a no-op — no duplicates, exit 0.

    Regression: prior behavior silently created duplicate toolRef entries.
    """
    # The fixture pre-populates one tool with toolRef='existing_tool'.
    result = runner.invoke(
        app,
        [
            "agent",
            "add-tool",
            "agent1",
            "--tool",
            "existing_tool",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already attached" in result.output
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_not_called()
    raw = settings.get_version_settings("v1").get_raw()
    tool_refs = [t["toolRef"] for t in raw["toolsUsingAgentSettings"]["tools"]]
    # Should not have duplicate
    assert tool_refs.count("existing_tool") == 1


def test_agent_add_tool(patch_client):
    result = runner.invoke(
        app, ["agent", "add-tool", "agent1", "--tool", "new_tool", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # Verify tool was added via version settings API (toolRef, not toolId)
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_called_once()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    tools = raw["toolsUsingAgentSettings"]["tools"]
    assert any(t["toolRef"] == "new_tool" for t in tools)


def test_agent_set_llm(patch_client):
    result = runner.invoke(
        app, ["agent", "set-llm", "agent1", "--llm-id", "gpt4", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # Verify LLM was set via version settings API (toolsUsingAgentSettings.llmId)
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_called()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    assert raw["toolsUsingAgentSettings"]["llmId"] == "gpt4"


def test_agent_set_prompt(patch_client):
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            "You are a helpful analyst.",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Set system prompt" in result.output
    # Verify prompt was set on version settings (systemPromptAppend on DSS 14.5+)
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_called()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    assert (
        raw["toolsUsingAgentSettings"]["systemPromptAppend"]
        == "You are a helpful analyst."
    )


def test_agent_set_prompt_from_file(patch_client, tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("You are a financial analyst.")
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            f"@{prompt_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    assert (
        raw["toolsUsingAgentSettings"]["systemPromptAppend"]
        == "You are a financial analyst."
    )


def test_agent_resolve_by_name(patch_client):
    """Agent commands accept name in addition to ID."""
    result = runner.invoke(app, ["agent", "get", "My Agent", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "agent1" in result.output


def test_agent_set_llm_by_name(patch_client):
    """set-llm works with agent name, not just ID."""
    result = runner.invoke(
        app, ["agent", "set-llm", "My Agent", "--llm-id", "gpt4", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Set LLM" in result.output


def test_agent_status_calls_status_not_get_status(patch_client):
    """Verify we call agent.status() (correct API) not agent.get_status()."""
    result = runner.invoke(app, ["agent", "status", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").status.assert_called_once()


# ── Structured agent (DSS 14.5+) ──────────────────────────────────────


def test_agent_set_prompt_structured_agent(patch_client):
    """Structured agents use systemPromptAppend in structuredAgentSettings."""
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "structured_agent",
            "--prompt",
            "New structured prompt",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "systemPromptAppend" in result.output

    settings = (
        patch_client.get_project("PROJ1").get_agent("structured_agent").get_settings()
    )
    ver_raw = settings.get_version_settings("v1").get_raw()
    assert (
        ver_raw["structuredAgentSettings"]["systemPromptAppend"]
        == "New structured prompt"
    )


def test_agent_set_prompt_simple_agent_uses_systemPromptAppend(patch_client):
    """TOOLS_USING_AGENT writes to systemPromptAppend (not systemPrompt) on DSS 14.5+.

    Regression: writing to `systemPrompt` made the runtime ignore the prompt — agents
    would respond as if the prompt were empty. Both agent types use the same field name.
    """
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            "New simple prompt",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "systemPromptAppend" in result.output

    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    ver_raw = settings.get_version_settings("v1").get_raw()
    assert (
        ver_raw["toolsUsingAgentSettings"]["systemPromptAppend"] == "New simple prompt"
    )
    # The legacy field must not be set — DSS reads systemPromptAppend.
    assert "systemPrompt" not in ver_raw["toolsUsingAgentSettings"]


def test_agent_set_llm_structured_agent(patch_client):
    """set-llm should fall back to raw dict mutation for structured agents."""
    result = runner.invoke(
        app,
        [
            "agent",
            "set-llm",
            "structured_agent",
            "--llm-id",
            "anthropic:conn:claude-4",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Set LLM" in result.output

    settings = (
        patch_client.get_project("PROJ1").get_agent("structured_agent").get_settings()
    )
    ver_raw = settings.get_version_settings("v1").get_raw()
    assert ver_raw["structuredAgentSettings"]["llmId"] == "anthropic:conn:claude-4"


def test_agent_add_tool_structured_agent_rejected(patch_client):
    """add-tool must refuse non-TOOLS_USING_AGENT types.

    Regression: the command used to silently write the tool to
    toolsUsingAgentSettings.tools — a key a structured agent never reads (its tools
    live inside blocks), so the tool was never attached despite a success message.
    It must now fail loudly and not save.
    """
    result = runner.invoke(
        app,
        [
            "agent",
            "add-tool",
            "structured_agent",
            "--tool",
            "new_tool_2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "TOOLS_USING_AGENT" in result.output
    assert "blocks" in result.output

    settings = (
        patch_client.get_project("PROJ1").get_agent("structured_agent").get_settings()
    )
    settings.save.assert_not_called()


def test_agent_test(patch_client):
    """Test sending a query to an agent."""
    result = runner.invoke(
        app,
        ["agent", "test", "agent1", "What is the refund policy?", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output


def test_agent_test_json(patch_client):
    """Test sending a query with JSON output."""
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "agent",
            "test",
            "agent1",
            "What is the refund policy?",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["agent_id"] == "agent1"
    assert parsed["query"] == "What is the refund policy?"
    assert parsed["response"] == "Hello from LLM"
    assert parsed["success"] is True


def test_agent_test_by_name(patch_client):
    """Test resolving agent by name for test command."""
    result = runner.invoke(
        app,
        ["agent", "test", "My Agent", "Hello", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output


# --- set-metadata ---


def test_agent_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "agent",
            "set-metadata",
            "agent1",
            "--description",
            "Customer support agent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output


def test_agent_set_metadata_by_name(patch_client):
    result = runner.invoke(
        app,
        [
            "agent",
            "set-metadata",
            "My Agent",
            "--description",
            "Help desk bot",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


def test_agent_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["agent", "set-metadata", "agent1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# ── Versioning: list-versions, create-version, set-active-version ──────


def test_agent_list_versions(patch_client):
    result = runner.invoke(
        app, ["agent", "list-versions", "agent1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "v1" in result.output


def test_agent_list_versions_json(patch_client):
    result = runner.invoke(
        app,
        ["--format", "json", "agent", "list-versions", "agent1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["version_id"] == "v1"
    assert parsed[0]["active"] == "✓"


def test_agent_create_version(patch_client):
    """create-version deep-copies the active version, picks next vN, persists."""
    result = runner.invoke(
        app, ["agent", "create-version", "agent1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created version 'v2'" in result.output

    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    raw = settings.get_raw()
    vids = [v["versionId"] for v in raw["versions"]]
    assert vids == ["v1", "v2"]
    # New version inherits config from v1
    v2 = next(v for v in raw["versions"] if v["versionId"] == "v2")
    assert v2["toolsUsingAgentSettings"]["llmId"] == "llm1"
    settings.save.assert_called()


def test_agent_create_version_activate(patch_client):
    """--activate calls saved_model.set_active_version with the new vid."""
    result = runner.invoke(
        app,
        ["agent", "create-version", "agent1", "--activate", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Created version 'v2'" in result.output
    assert "now active" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "agent1"
    ).set_active_version.assert_called_with("v2")


def test_agent_set_active_version(patch_client):
    """set-active-version uses the saved-model API (not raw activeVersion)."""
    # Seed a v2 first so the validation passes
    runner.invoke(app, ["agent", "create-version", "agent1", "--project", "PROJ1"])
    result = runner.invoke(
        app,
        ["agent", "set-active-version", "agent1", "v2", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "set to 'v2'" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "agent1"
    ).set_active_version.assert_called_with("v2")


def test_agent_set_active_version_bad_id(patch_client):
    """Asking to activate a missing version produces a prescriptive error."""
    result = runner.invoke(
        app,
        ["agent", "set-active-version", "agent1", "v999", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "v999" in result.output
    assert "v1" in result.output  # lists existing


def test_agent_set_prompt_new_version(patch_client):
    """--new-version creates a fresh version with the new prompt; v1 prompt stays untouched."""
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            "Version 2 prompt",
            "--new-version",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "version 'v2'" in result.output

    raw = patch_client.get_project("PROJ1").get_agent("agent1").get_settings().get_raw()
    v2 = next(v for v in raw["versions"] if v["versionId"] == "v2")
    # DSS 14.5+: both agent types use systemPromptAppend (was: systemPrompt).
    assert v2["toolsUsingAgentSettings"]["systemPromptAppend"] == "Version 2 prompt"
    # Inherits LLM from v1
    assert v2["toolsUsingAgentSettings"]["llmId"] == "llm1"
    # set-active-version was NOT called (no --activate)
    patch_client.get_project("PROJ1").get_saved_model(
        "agent1"
    ).set_active_version.assert_not_called()


def test_agent_set_prompt_new_version_activate(patch_client):
    """--activate flips active to the new version."""
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            "v2 prompt",
            "--new-version",
            "--activate",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "now active" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "agent1"
    ).set_active_version.assert_called_with("v2")


def test_agent_set_prompt_activate_requires_new_version(patch_client):
    """--activate without --new-version errors out (prevents silent in-place + no-op)."""
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            "x",
            "--activate",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--activate requires --new-version" in result.output


def test_agent_set_llm_new_version(patch_client):
    """--new-version on set-llm preserves tools + prompt from active version."""
    result = runner.invoke(
        app,
        [
            "agent",
            "set-llm",
            "agent1",
            "--llm-id",
            "gpt-5",
            "--new-version",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    raw = patch_client.get_project("PROJ1").get_agent("agent1").get_settings().get_raw()
    v2 = next(v for v in raw["versions"] if v["versionId"] == "v2")
    assert v2["toolsUsingAgentSettings"]["llmId"] == "gpt-5"
    # Tools from v1 are carried over
    assert any(
        t.get("toolRef") == "existing_tool"
        for t in v2["toolsUsingAgentSettings"]["tools"]
    )


def test_agent_add_tool_new_version(patch_client):
    """--new-version on add-tool appends to a fresh version, leaves v1 unchanged."""
    v1_tools_before = list(
        patch_client.get_project("PROJ1")
        .get_agent("agent1")
        .get_settings()
        .get_raw()["versions"][0]["toolsUsingAgentSettings"]["tools"]
    )
    result = runner.invoke(
        app,
        [
            "agent",
            "add-tool",
            "agent1",
            "--tool",
            "fresh_tool",
            "--new-version",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    raw = patch_client.get_project("PROJ1").get_agent("agent1").get_settings().get_raw()
    v1 = raw["versions"][0]
    v2 = next(v for v in raw["versions"] if v["versionId"] == "v2")
    # v1 tools unchanged
    assert v1["toolsUsingAgentSettings"]["tools"] == v1_tools_before
    # v2 has the new tool
    assert any(
        t.get("toolRef") == "fresh_tool" for t in v2["toolsUsingAgentSettings"]["tools"]
    )


# ── ergonomic aliases + tool name resolution ──────────────────────────────


def test_agent_test_accepts_query_flag(patch_client):
    """--query/-q works as an alias for the positional query."""
    result = runner.invoke(
        app,
        ["agent", "test", "agent1", "--query", "What is up?", "--project", "PROJ1"],
    )
    assert result.exit_code == 0


def test_agent_test_requires_some_query(patch_client):
    result = runner.invoke(app, ["agent", "test", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 2
    assert "--query" in result.output


def test_agent_add_tool_resolves_name_to_id(patch_client):
    """A tool NAME resolves to its ID before writing toolRef (a raw name
    saves fine but the tool silently never fires)."""
    result = runner.invoke(
        app,
        ["agent", "add-tool", "agent1", "--tool", "My Tool", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    raw = settings.get_version_settings("v1").get_raw()
    tools = raw["toolsUsingAgentSettings"]["tools"]
    assert any(t["toolRef"] == "tool1" for t in tools)  # resolved, not the name


def test_agent_add_tool_unknown_ref_fails_with_catalog(patch_client):
    result = runner.invoke(
        app,
        ["agent", "add-tool", "agent1", "--tool", "nope_xyz", "--project", "PROJ1"],
    )
    assert result.exit_code == 3
    assert "tool1" in result.output  # available tools listed
