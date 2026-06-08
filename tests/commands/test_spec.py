"""Tests for DKU_AGENT_HELP — `--help` rendered as machine-readable spec JSON."""

from __future__ import annotations

import json

import pytest
import typer
from typer.main import get_command
from typer.testing import CliRunner

from dku_cli import spec
from dku_cli.main import app

runner = CliRunner()


def _click_command(build):
    """Convert a single-command throwaway Typer app to its click Command."""
    throwaway = typer.Typer()
    build(throwaway)
    return get_command(throwaway)


@pytest.fixture
def agent_help(monkeypatch):
    monkeypatch.setenv("DKU_AGENT_HELP", "1")


def test_root_help_lists_groups_and_global_options(agent_help):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert spec["tool"] == "dku"
    assert spec["path"] == []
    assert "recipe" in spec["groups"]
    assert "dataset" in spec["groups"]
    assert "whoami" in spec["commands"]
    assert "options" in spec["commands"]["whoami"]
    # global options surface only at the root
    assert any(o["opts"] == ["--url"] for o in spec["global_options"])


def test_group_help_surfaces_child_command_signatures(agent_help):
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert spec["path"] == ["recipe"]
    assert isinstance(spec["commands"], dict)
    create_join = spec["commands"]["create-join"]
    assert create_join["name"] == "create-join"
    assert "help" in create_join
    # Group help is terse: a usage signature string, not full option objects.
    assert isinstance(create_join["signature"], str)
    assert "arguments" not in create_join
    assert "options" not in create_join
    # required input flag shows inline in the signature; choices may expand
    assert "--input" in create_join["signature"] or "-i" in create_join["signature"]


def test_group_help_is_small(agent_help):
    """The whole point of terse group help: even the 75-command recipe group
    must stay an order of magnitude smaller than full per-command detail."""
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    # ~75 commands; full per-command detail was ~75KB. Terse signatures must
    # keep this well under that — a regression to full dumps trips here.
    assert len(result.stdout) < 16000


def test_command_help_has_args_and_options(agent_help):
    result = runner.invoke(app, ["recipe", "create-join", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert spec["path"] == ["recipe", "create-join"]
    assert "arguments" in spec and "options" in spec
    flags = {o["opts"][0] for o in spec["options"] if o["opts"]}
    assert any(f.startswith("--") for f in flags)


def test_command_help_surfaces_enum_choices(agent_help):
    """Enum flags converted to click.Choice expose a `choices` array."""
    result = runner.invoke(app, ["recipe", "create-pivot", "--help"])
    spec = json.loads(result.stdout)
    by_name = {o["name"]: o for o in spec["options"]}
    assert "choices" in by_name["agg_type"]
    assert "SUM" in by_name["agg_type"]["choices"]


def test_help_text_has_no_rich_markup(agent_help):
    result = runner.invoke(app, ["--help"])
    spec = json.loads(result.stdout)
    assert "[blue bold]" not in spec["help"]
    assert "[/blue bold]" not in spec["help"]
    assert "Developer CLI" in spec["help"]


def test_agent_help_is_compact_by_default(agent_help):
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    payload = result.stdout.strip()
    assert "\n" not in payload
    assert json.loads(payload)["path"] == ["recipe"]


def test_compact_flag_still_works_with_agent_help(agent_help):
    result = runner.invoke(app, ["--compact", "recipe", "--help"])
    assert result.exit_code == 0
    payload = result.stdout.strip()
    assert "\n" not in payload
    assert json.loads(payload)["path"] == ["recipe"]


def test_help_is_human_text_when_env_unset(monkeypatch):
    monkeypatch.delenv("DKU_AGENT_HELP", raising=False)
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)
    assert "Usage" in result.stdout


# --- idx 15: secondary opts for bool flags in usage strings ------------------
def test_usage_string_renders_both_names_of_secondary_bool_flag():
    """A required ``--pass/--fail`` flag must show both names, not just --pass,
    so agents can discover the FAIL verdict path from the group-level signature."""

    def build(t):
        @t.command("override-trait")
        def _override(
            result_id: str,
            trait: str = typer.Option(..., "--trait"),
            verdict: bool = typer.Option(..., "--pass/--fail"),
        ):
            pass

    sig = spec._usage_string(_click_command(build))
    assert "--pass / --fail" in sig
    # the secondary name must not be silently dropped
    assert "--fail" in sig


def test_usage_string_single_bool_flag_unchanged():
    """A plain bool flag with no secondary name still renders as its primary."""

    def build(t):
        @t.command("c")
        def _c(force: bool = typer.Option(..., "--force")):
            pass

    sig = spec._usage_string(_click_command(build))
    assert "--force" in sig
    assert "/" not in sig


# --- idx 16: hidden params are skipped like Click's own formatter ------------
def test_command_detail_skips_hidden_options():
    def build(t):
        @t.command("c")
        def _c(
            visible: str = typer.Option("v", "--visible"),
            secret: str = typer.Option("s", "--secret", hidden=True),
        ):
            pass

    detail = spec._command_detail(_click_command(build))
    names = {o["name"] for o in detail["options"]}
    assert "visible" in names
    assert "secret" not in names


def test_usage_string_skips_hidden_required_option():
    def build(t):
        @t.command("c")
        def _c(
            req: str = typer.Option(..., "--req"),
            sneaky: str = typer.Option(..., "--sneaky", hidden=True),
        ):
            pass

    sig = spec._usage_string(_click_command(build))
    assert "--req" in sig
    assert "--sneaky" not in sig


# --- idx 17: default serialization still works after dead-guard removal ------
def test_param_default_still_serialized_after_guard_cleanup():
    """Removing the inert ``p.default is not p.type`` guard must not change the
    fact that a real, JSON-serializable default is emitted in the spec."""

    def build(t):
        @t.command("c")
        def _c(name: str = typer.Option("hello", "--name")):
            pass

    detail = spec._command_detail(_click_command(build))
    by_name = {o["name"]: o for o in detail["options"]}
    assert by_name["name"]["default"] == "hello"


# --- idx 2: UNSET import is safe / sentinel suppresses no-default params ------
def test_unset_sentinel_suppresses_default_key():
    """A param with no explicit default (Click's UNSET sentinel) must not emit a
    ``default`` key. This is the path the UNSET import guards."""

    def build(t):
        @t.command("c")
        def _c(target: str = typer.Argument(...)):
            pass

    detail = spec._command_detail(_click_command(build))
    by_name = {a["name"]: a for a in detail["arguments"]}
    assert "default" not in by_name["target"]


def test_unset_import_is_defined():
    """spec.UNSET must always be importable (real click.core.UNSET or fallback)."""
    assert spec.UNSET is not None
