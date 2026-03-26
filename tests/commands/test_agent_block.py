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
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
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
        raw["versions"][0]["toolsUsingAgentSettings"]["startingBlockId"] == "new_start"
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
    """Adding a block to a SIMPLE-mode agent should auto-switch to BLOCKS_GRAPH."""
    block = json.dumps(
        {"type": "EMIT_OUTPUT", "id": "first_block", "template": "Hello"}
    )
    result = runner.invoke(
        app, ["agent-block", "add", "agent1", "--block", block, "--project", "PROJ1"]
    )
    assert result.exit_code == 0

    raw = patch_client.get_project("PROJ1").get_agent("agent1").get_settings().get_raw()
    tuas = raw["versions"][0]["toolsUsingAgentSettings"]
    assert tuas["mode"] == "BLOCKS_GRAPH"
    # First block should auto-become starting block
    assert tuas.get("startingBlockId") == "first_block"


# ── remove ────────────────────────────────────────────────────────────────


def test_remove_block(patch_client):
    result = runner.invoke(
        app,
        ["agent-block", "remove", "agent_blocks", "emit_result", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Removed" in result.output

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
    assert not any(b["id"] == "emit_result" for b in blocks)


def test_remove_block_not_found(patch_client):
    result = runner.invoke(
        app,
        ["agent-block", "remove", "agent_blocks", "nonexistent", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_remove_starting_block(patch_client):
    """Removing the starting block should clear startingBlockId."""
    result = runner.invoke(
        app,
        ["agent-block", "remove", "agent_blocks", "init_state", "--project", "PROJ1"],
    )
    assert result.exit_code == 0

    raw = (
        patch_client.get_project("PROJ1")
        .get_agent("agent_blocks")
        .get_settings()
        .get_raw()
    )
    tuas = raw["versions"][0]["toolsUsingAgentSettings"]
    assert tuas.get("startingBlockId") is None


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
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
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
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
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
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
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
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
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
    blocks = raw["versions"][0]["toolsUsingAgentSettings"]["blocks"]
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
        raw["versions"][0]["toolsUsingAgentSettings"]["startingBlockId"] == "classify"
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
    assert raw["versions"][0]["toolsUsingAgentSettings"]["mode"] == "SIMPLE"


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
    tuas = raw["versions"][0]["toolsUsingAgentSettings"]
    assert tuas["mode"] == "BLOCKS_GRAPH"
    assert len(tuas["blocks"]) == 1
    assert tuas["blocks"][0]["id"] == "greet"


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
    assert raw["versions"][0]["toolsUsingAgentSettings"]["startingBlockId"] == "start"


# ── agent not found ───────────────────────────────────────────────────────


def test_list_blocks_agent_not_found(patch_client):
    result = runner.invoke(
        app, ["agent-block", "list", "nonexistent_agent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
