"""Surf #190 — agent-tool type/param discoverability + plugin component listing.

Imports each command's OWN sub-app (not dku_cli.main.app) and monkeypatches
get_client_from_ctx, so only the edited modules + shared infra import.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.agent_tool import app as agent_tool_app
from dku_cli.commands.plugin import app as plugin_app

runner = CliRunner()


def _settings_mock(params=None, raw=None):
    settings = MagicMock()
    settings.params = {} if params is None else params
    settings.get_raw.return_value = {} if raw is None else raw
    return settings


# ---------------------------------------------------------------------------
# describe — built-in (no DSS needed)
# ---------------------------------------------------------------------------


def test_describe_builtin_returns_known_keys():
    result = runner.invoke(agent_tool_app, ["describe", "VectorStoreSearch"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "knowledgeBankRef" in result.output


def test_describe_unknown_type_is_prescriptive():
    result = runner.invoke(agent_tool_app, ["describe", "NoSuchType"])
    assert result.exit_code != 0
    assert "agent-tool types" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# create / set-definition — unknown param key warning (monkeypatched client)
# ---------------------------------------------------------------------------


def _patch_create_client(monkeypatch):
    tool = MagicMock()
    tool.id = "newtool"
    tool.get_settings.return_value = _settings_mock(params={})
    builder = MagicMock()
    builder.create.return_value = tool
    proj = MagicMock()
    proj.new_agent_tool.return_value = builder
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )
    return client


def test_create_unknown_param_key_warns(monkeypatch):
    _patch_create_client(monkeypatch)
    result = runner.invoke(
        agent_tool_app,
        [
            "create",
            "my_tool",
            "--type",
            "LLMMeshLLMQuery",
            "--params",
            '{"bogus_key": 1}',
            "-P",
            "PROJ",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "bogus_key" in result.stderr
    assert "not known" in result.stderr


def test_set_definition_unknown_param_key_warns(monkeypatch):
    tool = MagicMock()
    tool.get_settings.return_value = _settings_mock(
        raw={"type": "LLMMeshLLMQuery", "params": {}}
    )
    proj = MagicMock()
    proj.get_agent_tool.return_value = tool
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )

    result = runner.invoke(
        agent_tool_app,
        ["set-definition", "tool1", "--params", '{"bogus_key": 1}', "-P", "PROJ"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "bogus_key" in result.stderr
    assert "not known" in result.stderr


def test_set_definition_known_key_no_warn(monkeypatch):
    tool = MagicMock()
    tool.get_settings.return_value = _settings_mock(
        raw={"type": "LLMMeshLLMQuery", "params": {}}
    )
    proj = MagicMock()
    proj.get_agent_tool.return_value = tool
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )

    result = runner.invoke(
        agent_tool_app,
        ["set-definition", "tool1", "--params", '{"llmId": "x"}', "-P", "PROJ"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "not known" not in result.stderr


def test_dataset_row_lookup_live_keys_do_not_warn(monkeypatch):
    tool = MagicMock()
    tool.get_settings.return_value = _settings_mock(
        raw={"type": "DatasetRowLookup", "params": {"datasetRef": "customers"}}
    )
    proj = MagicMock()
    proj.get_agent_tool.return_value = tool
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )

    result = runner.invoke(
        agent_tool_app,
        [
            "set-definition",
            "tool1",
            "--params",
            '{"retrievalMode": "MULTIPLE_RECORDS", "maxRecords": 20}',
            "-P",
            "PROJ",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "not known" not in result.stderr


def test_set_definition_params_preserves_existing_param_siblings(monkeypatch):
    raw = {
        "type": "DatasetRowLookup",
        "params": {
            "datasetRef": "customers",
            "datasetSmartName": "customers",
            "retrievalMode": "SINGLE_RECORD",
        },
    }
    tool = MagicMock()
    tool.get_settings.return_value = _settings_mock(raw=raw)
    proj = MagicMock()
    proj.get_agent_tool.return_value = tool
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )

    result = runner.invoke(
        agent_tool_app,
        [
            "set-definition",
            "tool1",
            "--definition",
            '{"params": {"retrievalMode": "MULTIPLE_RECORDS"}}',
            "-P",
            "PROJ",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert raw["params"] == {
        "datasetRef": "customers",
        "datasetSmartName": "customers",
        "retrievalMode": "MULTIPLE_RECORDS",
    }


# ---------------------------------------------------------------------------
# types --include-plugins + describe plugin descriptor (dev plugin tree)
# ---------------------------------------------------------------------------


def _dev_plugin_client(descriptor=None):
    tree = [
        {
            "name": "python-agent-tools",
            "path": "python-agent-tools",
            "children": [
                {
                    "name": "web-search",
                    "path": "python-agent-tools/web-search",
                    "children": [
                        {
                            "name": "tool.json",
                            "path": "python-agent-tools/web-search/tool.json",
                        },
                        {
                            "name": "tool.py",
                            "path": "python-agent-tools/web-search/tool.py",
                        },
                    ],
                }
            ],
        }
    ]
    plugin = MagicMock()
    plugin.list_files.return_value = tree
    if descriptor is not None:
        fp = MagicMock()
        fp.read.return_value = json.dumps(descriptor)
        cm = MagicMock()
        cm.__enter__.return_value = fp
        cm.__exit__.return_value = False
        plugin.get_file.return_value = cm
    client = MagicMock()
    client.list_plugins.return_value = [{"id": "my-tools", "isDev": True}]
    client.get_plugin.return_value = plugin
    return client


def test_types_include_plugins_merges_dev_tool_types(monkeypatch):
    client = _dev_plugin_client()
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(agent_tool_app, ["types", "--include-plugins"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Custom_agent_tool_my-tools_web-search" in result.output


def test_describe_plugin_type_reads_descriptor(monkeypatch):
    descriptor = {
        "meta": {"label": "Web Search"},
        "params": [
            {
                "name": "api_key",
                "type": "STRING",
                "mandatory": True,
                "label": "API Key",
            }
        ],
    }
    client = _dev_plugin_client(descriptor=descriptor)
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(
        agent_tool_app, ["describe", "Custom_agent_tool_my-tools_web-search"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "api_key" in result.output


def test_describe_plugin_type_non_dev_is_honest(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = [{"id": "my-tools", "isDev": False}]
    monkeypatch.setattr(
        "dku_cli.commands.agent_tool.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(
        agent_tool_app, ["describe", "Custom_agent_tool_my-tools_web-search"]
    )
    assert result.exit_code != 0
    assert "non-dev" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# plugin components
# ---------------------------------------------------------------------------


def test_plugin_components_lists_dev_components(monkeypatch):
    tree = [
        {
            "name": "python-agent-tools",
            "children": [{"name": "web-search", "children": []}],
        },
        {
            "name": "custom-recipes",
            "children": [{"name": "my-step", "children": []}],
        },
    ]
    plugin = MagicMock()
    plugin.list_files.return_value = tree
    client = MagicMock()
    client.list_plugins.return_value = [{"id": "my-tools", "isDev": True}]
    client.get_plugin.return_value = plugin
    monkeypatch.setattr(
        "dku_cli.commands.plugin.get_client_from_ctx", lambda ctx: client
    )

    result = runner.invoke(plugin_app, ["components", "my-tools"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Custom_agent_tool_my-tools_web-search" in result.output
    assert "CustomCode_my-step" in result.output


def test_plugin_components_non_dev_footer(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = [{"id": "installed-plugin", "isDev": False}]
    monkeypatch.setattr(
        "dku_cli.commands.plugin.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(plugin_app, ["components", "installed-plugin"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "non-dev" in (result.stdout + result.stderr)
