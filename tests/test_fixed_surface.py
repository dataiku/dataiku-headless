"""The MCP catalog is fixed except for explicit transport safety gates."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
_PROBE = """
import asyncio
import json
import dataiku_mcp
from dataiku_mcp import config_mcp

tools = asyncio.run(dataiku_mcp.mcp.local_provider.list_tools())
print(json.dumps({
    "transport": dataiku_mcp.transport,
    "tools": sorted(tool.name for tool in tools),
    "legacy_config_present": any(hasattr(config_mcp, name) for name in (
        "DKU_MCP_COBUILD_MODE",
        "DKU_MCP_TOOL_EXPOSURE",
        "DKU_MCP_SEARCH_MAX_RESULTS",
        "DKU_MCP_SEARCH_ALWAYS_VISIBLE",
        "FULL_COBUILD_DISABLED_TOOLS",
    )),
}))
"""


def probe(**environment: str) -> dict:
    env = os.environ.copy()
    for name in (
        "DKU_MCP_COBUILD_MODE",
        "DKU_MCP_TOOL_EXPOSURE",
        "DKU_MCP_SEARCH_MAX_RESULTS",
        "DKU_MCP_SEARCH_ALWAYS_VISIBLE",
    ):
        env.pop(name, None)
    env.update(environment)
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_removed_exposure_environment_cannot_change_or_break_the_catalog():
    baseline = probe(DKU_MCP_TRANSPORT="stdio")
    legacy_values = probe(
        DKU_MCP_TRANSPORT="stdio",
        DKU_MCP_COBUILD_MODE="not-a-mode",
        DKU_MCP_TOOL_EXPOSURE="not-a-mode",
        DKU_MCP_SEARCH_MAX_RESULTS="not-an-int",
        DKU_MCP_SEARCH_ALWAYS_VISIBLE="missing,tools",
    )

    assert baseline["tools"] == legacy_values["tools"]
    assert baseline["legacy_config_present"] is False
    assert legacy_values["legacy_config_present"] is False
    assert "search_tools" not in baseline["tools"]
    assert "call_tool" not in baseline["tools"]


def test_transport_delta_contains_only_the_documented_safety_gates():
    stdio = set(probe(DKU_MCP_TRANSPORT="stdio")["tools"])
    http = set(probe(DKU_MCP_TRANSPORT="streamable-http")["tools"])

    assert stdio - http == {
        "create_upload_dataset",
        "upload_file_to_managed_folder",
        "write_project_library_file",
        "switch_instance",
        "list_instances",
    }
    assert http - stdio == {"create_upload_dataset_from_rows"}


def test_invalid_transport_still_fails_closed():
    with pytest.raises(subprocess.CalledProcessError) as exc:
        probe(DKU_MCP_TRANSPORT="websocket")
    assert "Invalid DKU_MCP_TRANSPORT" in exc.value.stderr
