"""Tests for dku agent-block commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()

# ── list ──────────────────────────────────────────────────────────────────


def test_list_blocks(patch_client):
    result = runner.invoke(
        app, ["agent-block", "list", "agent_blocks", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "init_state" in result.output
    assert "classify" in result.output
    assert "emit_result" in result.output


def test_list_blocks_json(patch_client):
    result = runner.invoke(
        app, ["agent-block", "list", "agent_blocks", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 3
    ids = [b["id"] for b in parsed]
    assert "init_state" in ids
    assert "classify" in ids
    assert "emit_result" in ids
    # Starting block should be marked
    start_block = [b for b in parsed if b["id"] == "init_state"][0]
    assert start_block["start"] == "*"


def test_list_blocks_simple_mode(patch_client):
    """Agent in SIMPLE mode should warn and show empty list."""
    result = runner.invoke(app, ["agent-block", "list", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_list_blocks_resolve_by_name(patch_client):
    """Agent-block commands should resolve agents by name, not just ID."""
    result = runner.invoke(
        app, ["agent-block", "list", "Block Agent", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "init_state" in result.output


# ── get ───────────────────────────────────────────────────────────────────


def test_get_block(patch_client):
    result = runner.invoke(
        app, ["agent-block", "get", "agent_blocks", "classify", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "classify" in result.output
    assert "LLM_REQUEST" in result.output


def test_get_block_json(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "get",
            "agent_blocks",
            "classify",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "classify"
    assert parsed["type"] == "LLM_REQUEST"


def test_get_block_not_found(patch_client):
    result = runner.invoke(
        app, ["agent-block", "get", "agent_blocks", "nonexistent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# ── add ───────────────────────────────────────────────────────────────────


def test_add_block(patch_client):
    block = json.dumps({"type": "EMIT_OUTPUT", "id": "new_emit", "template": "Hello"})
    result = runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "new_emit" in result.output

    # Verify block was appended
    settings = (
        patch_client.get_project("PROJ1").get_agent("agent_blocks").get_settings()
    )
    raw = settings.get_raw()
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    assert any(b["id"] == "new_emit" for b in blocks)
    settings.save.assert_called()


def test_add_block_set_start(patch_client):
    block = json.dumps({"type": "EMIT_OUTPUT", "id": "new_start", "template": "Hi"})
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--set-start",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    assert (
        raw["versions"][0]["structuredAgentSettings"]["startingBlockId"] == "new_start"
    )


def test_add_block_duplicate_id(patch_client):
    block = json.dumps({"type": "EMIT_OUTPUT", "id": "init_state", "template": "Dup"})
    result = runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_add_block_missing_id(patch_client):
    block = json.dumps({"type": "EMIT_OUTPUT", "template": "No ID"})
    result = runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_add_block_missing_type(patch_client):
    block = json.dumps({"id": "no_type"})
    result = runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_add_block_auto_mode_switch(patch_client):
    """Adding a block should create blocks list and set starting block."""
    block = json.dumps(
        {"type": "EMIT_OUTPUT", "id": "first_block", "template": "Hello"}
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "structured_agent_empty",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("structured_agent_empty")
        .get_settings()
        .get_raw()
    )
    sas = raw["versions"][0]["structuredAgentSettings"]
    # First block should auto-become starting block
    assert sas.get("startingBlockId") == "first_block"


# ── remove ────────────────────────────────────────────────────────────────


def test_remove_block(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "remove",
            "agent_blocks",
            "emit_result",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Removed" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    assert not any(b["id"] == "emit_result" for b in blocks)


def test_remove_block_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "remove",
            "agent_blocks",
            "nonexistent",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code != 0


def test_remove_starting_block(patch_client):
    """Removing the starting block should clear startingBlockId."""
    result = runner.invoke(
        app,
        [
            "agent-block",
            "remove",
            "agent_blocks",
            "init_state",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    sas = raw["versions"][0]["structuredAgentSettings"]
    assert sas.get("startingBlockId") is None


# ── connect / disconnect ──────────────────────────────────────────────────


def test_connect_blocks(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "agent_blocks",
            "--from",
            "emit_result",
            "--to",
            "init_state",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Connected" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    emit_block = [b for b in blocks if b["id"] == "emit_result"][0]
    assert emit_block["nextBlock"] == "init_state"


def test_connect_source_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "agent_blocks",
            "--from",
            "nonexistent",
            "--to",
            "classify",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_connect_target_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "agent_blocks",
            "--from",
            "classify",
            "--to",
            "nonexistent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_connect_standard_react_uses_default_next_block(patch_client):
    """STANDARD_REACT blocks must use defaultNextBlock, not nextBlock."""
    # Add a STANDARD_REACT block to the graph first
    block = json.dumps({"type": "STANDARD_REACT", "id": "react_block", "tools": []})
    runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )

    result = runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "agent_blocks",
            "--from",
            "react_block",
            "--to",
            "emit_result",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    react = [b for b in blocks if b["id"] == "react_block"][0]
    assert react.get("defaultNextBlock") == "emit_result"
    assert "nextBlock" not in react


def test_connect_python_code_fails_with_guidance(patch_client):
    """PYTHON_CODE blocks cannot be wired with connect — must use set-graph."""
    block = json.dumps(
        {"type": "PYTHON_CODE", "id": "py_block", "code": "def process(trace): pass"}
    )
    runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )

    result = runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "agent_blocks",
            "--from",
            "py_block",
            "--to",
            "emit_result",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "PYTHON_CODE" in result.output or "set-graph" in result.output


def test_disconnect_block(patch_client):
    result = runner.invoke(
        app,
        ["agent-block", "disconnect", "agent_blocks", "classify", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Disconnected" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    classify_block = [b for b in blocks if b["id"] == "classify"][0]
    assert "nextBlock" not in classify_block


def test_disconnect_standard_react_clears_default_next_block(patch_client):
    """STANDARD_REACT disconnect must clear defaultNextBlock, not nextBlock."""
    # First add and connect a STANDARD_REACT block
    block = json.dumps({"type": "STANDARD_REACT", "id": "react_block", "tools": []})
    runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )
    runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "agent_blocks",
            "--from",
            "react_block",
            "--to",
            "emit_result",
            "--project",
            "PROJ1",
        ],
    )

    # Verify it's connected via defaultNextBlock
    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    react = [b for b in blocks if b["id"] == "react_block"][0]
    assert react.get("defaultNextBlock") == "emit_result"

    # Now disconnect it
    result = runner.invoke(
        app,
        [
            "agent-block",
            "disconnect",
            "agent_blocks",
            "react_block",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Disconnected" in result.output

    # Verify defaultNextBlock is gone
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    react = [b for b in blocks if b["id"] == "react_block"][0]
    assert "defaultNextBlock" not in react


def test_disconnect_python_code_fails_with_guidance(patch_client):
    """PYTHON_CODE blocks cannot be disconnected with disconnect — must use set-graph."""
    block = json.dumps(
        {"type": "PYTHON_CODE", "id": "py_block", "code": "def process(trace): pass"}
    )
    runner.invoke(
        app,
        ["agent-block", "add", "agent_blocks", "--block", block, "--project", "PROJ1"],
    )

    result = runner.invoke(
        app,
        [
            "agent-block",
            "disconnect",
            "agent_blocks",
            "py_block",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "PYTHON_CODE" in result.output or "set-graph" in result.output


def test_disconnect_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "disconnect",
            "agent_blocks",
            "nonexistent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


# ── set-start ─────────────────────────────────────────────────────────────


def test_set_start(patch_client):
    result = runner.invoke(
        app,
        ["agent-block", "set-start", "agent_blocks", "classify", "--project", "PROJ1"],
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    assert (
        raw["versions"][0]["structuredAgentSettings"]["startingBlockId"] == "classify"
    )


def test_set_start_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-block",
            "set-start",
            "agent_blocks",
            "nonexistent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


# ── set-mode ──────────────────────────────────────────────────────────────


def test_set_mode_to_blocks_graph(patch_client):
    result = runner.invoke(
        app, ["agent-block", "set-mode", "agent1", "BLOCKS_GRAPH", "--project", "PROJ1"]
    )
    assert result.exit_code == 0

    raw = patch_client.get_project("PROJ1").get_agent("agent1").get_settings().get_raw()
    tuas = raw["versions"][0]["toolsUsingAgentSettings"]
    assert tuas["mode"] == "BLOCKS_GRAPH"
    assert isinstance(tuas.get("blocks"), list)


def test_set_mode_to_simple(patch_client):
    result = runner.invoke(
        app, ["agent-block", "set-mode", "agent_blocks", "SIMPLE", "--project", "PROJ1"]
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    assert raw["versions"][0]["structuredAgentSettings"]["mode"] == "SIMPLE"


def test_set_mode_invalid(patch_client):
    result = runner.invoke(
        app,
        ["agent-block", "set-mode", "agent_blocks", "INVALID", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


# ── get-graph / set-graph ─────────────────────────────────────────────────


def test_get_graph(patch_client):
    result = runner.invoke(
        app, ["agent-block", "get-graph", "agent_blocks", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["mode"] == "BLOCKS_GRAPH"
    assert len(parsed["blocks"]) == 3
    assert parsed["startingBlockId"] == "init_state"


def test_set_graph(patch_client):
    new_graph = json.dumps(
        {
            "mode": "BLOCKS_GRAPH",
            "startingBlockId": "greet",
            "blocks": [
                {
                    "type": "EMIT_OUTPUT",
                    "id": "greet",
                    "template": "Hi",
                    "addToMessages": True,
                },
            ],
            "tools": [],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "set-graph",
            "agent_blocks",
            "--definition",
            new_graph,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    sas = raw["versions"][0]["structuredAgentSettings"]
    assert sas["mode"] == "BLOCKS_GRAPH"
    assert len(sas["blocks"]) == 1
    assert sas["blocks"][0]["id"] == "greet"


def test_set_graph_from_file(patch_client, tmp_path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "mode": "BLOCKS_GRAPH",
                "startingBlockId": "start",
                "blocks": [{"type": "EMIT_OUTPUT", "id": "start", "template": "OK"}],
                "tools": [],
            }
        )
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "set-graph",
            "agent_blocks",
            "--definition",
            f"@{graph_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    assert raw["versions"][0]["structuredAgentSettings"]["startingBlockId"] == "start"


# ── agent not found ───────────────────────────────────────────────────────


# ── Structured agent (DSS 14.5+ — structuredAgentSettings) ──────────────


def test_list_blocks_structured_agent(patch_client):
    """Structured agents use structuredAgentSettings, not toolsUsingAgentSettings."""
    result = runner.invoke(
        app, ["agent-block", "list", "structured_agent", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "main_loop" in result.output
    assert "output" in result.output


def test_list_blocks_shows_default_next_block(patch_client):
    """CORE_LOOP blocks should show defaultNextBlock with (default) suffix."""
    result = runner.invoke(
        app, ["agent-block", "list", "structured_agent", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "(default)" in result.output


def test_list_blocks_default_next_block_json(patch_client):
    """JSON output should include defaultNextBlock with (default) suffix."""
    result = runner.invoke(
        app,
        ["agent-block", "list", "structured_agent", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    loop = [b for b in parsed if b["id"] == "main_loop"][0]
    assert loop["next_block"] == "output (default)"


def test_get_graph_structured_agent(patch_client):
    """get-graph should return structuredAgentSettings for structured agents."""
    result = runner.invoke(
        app, ["agent-block", "get-graph", "structured_agent", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["mode"] == "BLOCKS_GRAPH"
    assert len(parsed["blocks"]) == 2
    assert parsed["blocks"][0]["type"] == "CORE_LOOP"


def test_set_graph_structured_agent(patch_client):
    """set-graph should write to structuredAgentSettings for structured agents."""
    new_graph = json.dumps(
        {
            "mode": "BLOCKS_GRAPH",
            "startingBlockId": "loop",
            "blocks": [
                {"type": "CORE_LOOP", "id": "loop", "defaultNextBlock": "out"},
                {"type": "GENERATE_OUTPUT", "id": "out", "template": "Done"},
            ],
            "tools": [],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "set-graph",
            "structured_agent",
            "--definition",
            new_graph,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("structured_agent")
        .get_settings()
        .get_raw()
    )
    # Must write to structuredAgentSettings, NOT toolsUsingAgentSettings
    cfg = raw["versions"][0]["structuredAgentSettings"]
    assert cfg["mode"] == "BLOCKS_GRAPH"
    assert len(cfg["blocks"]) == 2
    assert cfg["blocks"][0]["type"] == "CORE_LOOP"


def test_connect_core_loop_uses_default_next_block(patch_client):
    """CORE_LOOP blocks (DSS 14.5+) must use defaultNextBlock, same as STANDARD_REACT."""
    # Add a CORE_LOOP block to the existing structured agent
    block = json.dumps({"type": "CORE_LOOP", "id": "new_loop", "tools": []})
    runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "structured_agent",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )

    result = runner.invoke(
        app,
        [
            "agent-block",
            "connect",
            "structured_agent",
            "--from",
            "new_loop",
            "--to",
            "output",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("structured_agent")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    loop = [b for b in blocks if b["id"] == "new_loop"][0]
    assert loop.get("defaultNextBlock") == "output"
    assert "nextBlock" not in loop


def test_add_block_structured_agent(patch_client):
    """Adding blocks to structured agent should work via structuredAgentSettings."""
    block = json.dumps({"type": "LLM_REQUEST", "id": "classify", "llmId": "llm1"})
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "structured_agent",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added block" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("structured_agent")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["structuredAgentSettings"]["blocks"]
    ids = [b["id"] for b in blocks]
    assert "classify" in ids


def test_add_block_structured_agent_no_initial_settings(patch_client):
    """Adding blocks to a newly-created STRUCTURED_AGENT (no structuredAgentSettings yet)
    should create structuredAgentSettings, NOT fall back to toolsUsingAgentSettings."""
    block = json.dumps({"type": "LLM_REQUEST", "id": "first_block", "llmId": "llm1"})
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "structured_agent_empty",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added block" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("structured_agent_empty")
        .get_settings()
        .get_raw()
    )
    ver = raw["versions"][0]
    # Must write to structuredAgentSettings, not toolsUsingAgentSettings
    assert "structuredAgentSettings" in ver
    assert "toolsUsingAgentSettings" not in ver
    blocks = ver["structuredAgentSettings"]["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["id"] == "first_block"
    # First block should be auto-set as starting block
    assert ver["structuredAgentSettings"]["startingBlockId"] == "first_block"


def test_list_blocks_structured_agent_empty(patch_client):
    """Listing blocks on a STRUCTURED_AGENT with no settings yet should return empty."""
    result = runner.invoke(
        app,
        [
            "agent-block",
            "list",
            "structured_agent_empty",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# ── agent not found ───────────────────────────────────────────────────


def test_list_blocks_agent_not_found(patch_client):
    result = runner.invoke(
        app, ["agent-block", "list", "nonexistent_agent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# ── CEL validation ───────────────────────────────────────────────────


def test_add_routing_block_empty_cel_rejected(patch_client):
    """ROUTING block with empty CEL expression must be rejected."""
    block = json.dumps(
        {
            "type": "ROUTING",
            "id": "bad_routing",
            "routingMode": "CLAUSES",
            "clausesBasedDecisions": [
                {
                    "clause": {
                        "type": "EXPRESSION",
                        "expression": {"language": "CEL", "expression": ""},
                    },
                    "nextBlock": "some_block",
                }
            ],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Micro-CEL" in result.output or "EMPTY CEL" in result.output


def test_add_routing_block_valid_cel_accepted(patch_client):
    """ROUTING block with valid CEL expression should be accepted."""
    block = json.dumps(
        {
            "type": "ROUTING",
            "id": "good_routing",
            "routingMode": "CLAUSES",
            "clausesBasedDecisions": [
                {
                    "clause": {
                        "type": "EXPRESSION",
                        "expression": {
                            "language": "CEL",
                            "expression": 'state["intent"] == "billing"',
                        },
                    },
                    "nextBlock": "billing_handler",
                }
            ],
            "defaultNextBlockIfNoClauseMatch": "fallback",
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added block" in result.output


def test_add_routing_block_llm_based_clause_no_cel_ok(patch_client):
    """ROUTING block with LLM_BASED clauses (no CEL) should be accepted."""
    block = json.dumps(
        {
            "type": "ROUTING",
            "id": "llm_routing",
            "routingMode": "CLAUSES",
            "clausesBasedDecisions": [
                {
                    "clause": {
                        "type": "LLM_BASED",
                        "passConversationHistory": True,
                        "systemPromptAfterHistory": "Is this a billing question?",
                    },
                    "nextBlock": "billing_handler",
                }
            ],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added block" in result.output


def test_set_graph_empty_cel_rejected(patch_client):
    """set-graph with ROUTING block containing empty CEL must be rejected."""
    graph = json.dumps(
        {
            "mode": "BLOCKS_GRAPH",
            "startingBlockId": "bad_routing",
            "blocks": [
                {
                    "type": "ROUTING",
                    "id": "bad_routing",
                    "routingMode": "CLAUSES",
                    "clausesBasedDecisions": [
                        {
                            "clause": {
                                "type": "EXPRESSION",
                                "expression": {"language": "CEL", "expression": "  "},
                            },
                            "nextBlock": "target",
                        }
                    ],
                }
            ],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "set-graph",
            "agent_blocks",
            "--definition",
            graph,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Micro-CEL" in result.output or "EMPTY CEL" in result.output


# ── SET_STATE_ENTRIES / SAVE_TO_STATE / LLM block validation ──────────


def test_add_set_state_entries_empty_value_rejected(patch_client):
    """SET_STATE_ENTRIES with an empty-string CEL value must be rejected."""
    block = json.dumps(
        {
            "type": "SET_STATE_ENTRIES",
            "id": "bad_set",
            "entriesToSet": [{"key": "foo", "value": ""}],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "EMPTY CEL" in result.output


def test_add_set_state_entries_valid_cel_accepted(patch_client):
    """SET_STATE_ENTRIES with a valid CEL literal should be accepted."""
    block = json.dumps(
        {
            "type": "SET_STATE_ENTRIES",
            "id": "good_set",
            "entriesToSet": [{"key": "intent", "value": "''"}],
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


def test_add_save_to_state_missing_output_key_rejected(patch_client):
    """Block with outputMode=SAVE_TO_STATE but no output key must be rejected."""
    block = json.dumps(
        {
            "type": "LLM_REQUEST",
            "id": "bad_save",
            "outputMode": "SAVE_TO_STATE",
            "llmId": "openai:conn:gpt-4o",
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "output key" in result.output or "outputKey" in result.output


def test_add_llm_block_missing_llm_id_warns(patch_client):
    """LLM-dependent block without llmId should warn but still succeed."""
    block = json.dumps(
        {
            "type": "CORE_LOOP",
            "id": "loop_no_llm",
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent_blocks",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "llmId" in result.output


# ── agent type validation ─────────────────────────────────────────────


def test_add_block_to_tools_using_agent_errors(patch_client):
    """Adding a block to TOOLS_USING_AGENT should error, not just warn."""
    block = json.dumps(
        {
            "type": "EMIT_OUTPUT",
            "id": "new_output",
            "template": "Done",
        }
    )
    result = runner.invoke(
        app,
        [
            "agent-block",
            "add",
            "agent1",
            "--block",
            block,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "STRUCTURED_AGENT" in result.output
