"""Canary: --help must always emit parseable structured JSON.

This is the tripwire for the typer/click pins in pyproject.toml. typer >= 0.25
(and the matching click >= 8.4) change the help-rendering path enough to break
the machine-readable spec JSON that agents depend on. If those pins ever drift,
one of these assertions fails loudly instead of agents silently getting prose
help back.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()

_AGENT_HELP_ENV = {"DKU_AGENT_HELP": "1"}


def _help_json(args: list[str]) -> dict:
    result = runner.invoke(app, [*args, "--help"], env=_AGENT_HELP_ENV)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_root_help_is_json():
    """`dku --help` — root index with groups and global options."""
    parsed = _help_json([])
    assert "groups" in parsed
    assert "global_options" in parsed
    assert isinstance(parsed["groups"], dict)


def test_group_help_is_json():
    """`dku recipe --help` — a group's concise command signatures."""
    parsed = _help_json(["recipe"])
    assert "commands" in parsed
    assert isinstance(parsed["commands"], dict)
    assert parsed["commands"], "recipe group should list commands"


def test_leaf_command_help_is_json():
    """`dku project list --help` — full detail for one leaf command."""
    parsed = _help_json(["project", "list"])
    assert parsed["name"] == "list"
    assert "arguments" in parsed
    assert "options" in parsed
