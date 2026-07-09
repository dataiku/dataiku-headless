"""Tests for `--help` rendered as machine-readable spec JSON — always on."""

from __future__ import annotations

import json

import click
import typer
from typer.main import get_command
from typer.testing import CliRunner

from dku_cli import spec
from dku_cli.main import app
from dku_cli.spec_text import render_text_help

runner = CliRunner()


def _click_command(build):
    """Convert a single-command throwaway Typer app to its click Command."""
    throwaway = typer.Typer()
    build(throwaway)
    return get_command(throwaway)


def test_root_help_lists_groups_and_global_options():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    # no tool/version/path meta — it would repeat what the agent just typed
    for key in ("tool", "version", "path"):
        assert key not in spec
    assert "recipe" in spec["groups"]
    assert "dataset" in spec["groups"]
    assert "whoami" in spec["commands"]
    assert "options" in spec["commands"]["whoami"]
    # global options surface only at the root
    assert any(o["opts"] == ["--url"] for o in spec["global_options"])


def test_root_help_skips_hidden_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert "managedfolder" not in spec["groups"]
    assert "managed-folder" not in spec["groups"]


def test_bare_invocation_prints_root_spec():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert "recipe" in spec["groups"]


def test_group_help_surfaces_child_command_signatures():
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert isinstance(spec["commands"], dict)
    create_join = spec["commands"]["create-join"]
    # entries are keyed by command name; no redundant "name" field
    assert "name" not in create_join
    assert "help" in create_join
    # Group help is terse: a usage signature string, not full option objects.
    assert isinstance(create_join["signature"], str)
    assert "arguments" not in create_join
    assert "options" not in create_join
    # required input flag shows inline in the signature; choices may expand
    assert "--input" in create_join["signature"] or "-i" in create_join["signature"]


def test_group_help_is_small():
    """The whole point of terse group help: even the 75-command recipe group
    must stay an order of magnitude smaller than full per-command detail."""
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    # ~75 commands; full per-command detail was ~75KB. Terse signatures must
    # keep this well under that — a regression to full dumps trips here.
    assert len(result.stdout) < 16000


def test_command_help_has_args_and_options():
    result = runner.invoke(app, ["recipe", "create-join", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert spec["name"] == "create-join"
    assert "arguments" in spec and "options" in spec
    flags = {o["opts"][0] for o in spec["options"] if o["opts"]}
    assert any(f.startswith("--") for f in flags)


def test_command_help_surfaces_enum_choices():
    """Enum flags converted to click.Choice expose a `choices` array."""
    result = runner.invoke(app, ["recipe", "create-pivot", "--help"])
    spec = json.loads(result.stdout)
    by_name = {o["name"]: o for o in spec["options"]}
    assert "choices" in by_name["agg_type"]
    assert "SUM" in by_name["agg_type"]["choices"]


def test_scenario_python_env_mode_help_uses_canonical_choices():
    """Help must not advertise DSS enum values that serialize to null."""
    for command in ("add-step-python", "add-trigger-python"):
        result = runner.invoke(app, ["scenario", command, "--help"])
        assert result.exit_code == 0
        spec = json.loads(result.stdout)
        by_name = {o["name"]: o for o in spec["options"]}
        env_mode = by_name["env_mode"]
        assert env_mode["type"] == "choice"
        assert env_mode["choices"] == [
            "INHERIT",
            "USE_BUILTIN_MODE",
            "EXPLICIT_ENV",
        ]
        assert "USE_BUILTIN_ENV" not in result.stdout


def test_help_text_has_no_rich_markup():
    result = runner.invoke(app, ["--help"])
    spec = json.loads(result.stdout)
    assert "[blue bold]" not in spec["help"]
    assert "[/blue bold]" not in spec["help"]
    assert "Dataiku Headless" in spec["help"]


def test_help_is_compact():
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    payload = result.stdout.strip()
    assert "\n" not in payload
    assert "create-join" in json.loads(payload)["commands"]


def test_non_tty_help_is_spec_json():
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    assert "create-join" in json.loads(result.stdout)["commands"]


def test_human_mode_env_without_tty_help_stays_json(monkeypatch):
    monkeypatch.setenv("DKU_HUMAN_MODE", "1")
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    assert "create-join" in json.loads(result.stdout)["commands"]


def test_human_mode_help_renders_text(monkeypatch):
    from dku_cli import spec_text

    monkeypatch.setattr(spec_text, "is_human_mode", lambda stream=None: True)
    node = {"help": "Recipes", "commands": {"create-join": {"help": "Join."}}}
    text = spec_text.render_help(node, "dku recipe")
    assert text.startswith("Usage: dku recipe")
    assert "create-join" in text


def test_human_mode_help_defers_to_format_json(monkeypatch):
    from dku_cli import spec_text
    from dku_cli.output import set_output_format

    monkeypatch.setattr(spec_text, "is_human_mode", lambda stream=None: True)
    set_output_format("json")
    node = {"help": "Recipes"}
    assert json.loads(spec_text.render_help(node, "dku recipe")) == node


def test_text_help_renderer_uses_readable_sections():
    result = runner.invoke(app, ["recipe", "--help"])
    node = json.loads(result.stdout)

    text = render_text_help(node, "dku recipe")

    assert "Usage: dku recipe [command] [options]" in text
    assert "Commands:" in text
    assert "create-join" in text
    assert "\\n" not in text
    assert "[options]Add" not in text


def test_text_help_renderer_leaf_usage_does_not_claim_subcommands():
    result = runner.invoke(app, ["recipe", "create-join", "--help"])
    node = json.loads(result.stdout)

    text = render_text_help(node, "dku recipe create-join")

    assert "Usage: dku recipe create-join <recipe_name> [options]" in text
    assert "[command]" not in text.splitlines()[0]


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


def test_group_detail_skips_hidden_child_commands():
    group = click.Group("g")
    group.add_command(click.Command("visible", help="Visible command"))
    group.add_command(click.Command("secret", help="Hidden command", hidden=True))

    detail = spec._group_detail(group)

    assert "visible" in detail["commands"]
    assert "secret" not in detail["commands"]


def test_group_like_command_help_surfaces_child_commands():
    command = click.Command("plugin", help="Manage DSS plugins.")
    command.commands = {
        "list": click.Command("list", help="List installed plugins."),
    }
    root_ctx = click.Context(click.Group("dku"), info_name="dku")
    ctx = click.Context(command, info_name="plugin", parent=root_ctx)

    detail = spec.spec_node_for(command, ctx)

    assert "commands" in detail
    assert detail["commands"]["list"]["help"] == "List installed plugins."
    assert "arguments" not in detail
    assert "options" not in detail


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


def test_full_index_covers_every_visible_group():
    root = get_command(app)
    index = spec.full_index(root)
    assert "dataset" in index
    assert "recipe" in index
    assert "share" in index["dataset"]["commands"]
    assert "whoami" in index["root"]["commands"]
    assert "commands" in index["root"]["commands"]


def test_full_index_covers_nested_commands():
    root = get_command(app)
    index = spec.full_index(root)
    assert "metrics run" in index["dataset"]["commands"]
    assert "blueprint list-signoff-configs" in index["govern"]["commands"]
    assert "license upload" in index["admin"]["commands"]


def test_full_index_covers_every_visible_leaf_path():
    root = get_command(app)
    index = spec.full_index(root)
    indexed_paths = {
        command if group == "root" else f"{group} {command}"
        for group, node in index.items()
        for command in node["commands"]
    }

    leaf_paths: set[str] = set()

    def collect(cmd: click.Command, path: tuple[str, ...]) -> None:
        commands = spec._child_commands(cmd)
        if commands is None:
            leaf_paths.add(" ".join(path))
            return
        for name, child in commands.items():
            if not getattr(child, "hidden", False):
                collect(child, (*path, name))

    for name, cmd in root.commands.items():
        if not getattr(cmd, "hidden", False):
            collect(cmd, (name,))

    assert leaf_paths <= indexed_paths


def test_full_index_skips_hidden_groups_and_commands():
    root = get_command(app)
    index = spec.full_index(root)
    assert "managedfolder" not in index
    assert "managed-folder" not in index


def test_full_index_entries_are_flat_one_liners():
    """Only names + one-line help — no args/flags/types, that stays behind --help."""
    root = get_command(app)
    index = spec.full_index(root)
    node = index["recipe"]
    assert isinstance(node["help"], str)
    for one_liner in node["commands"].values():
        assert isinstance(one_liner, str)
        assert "\n" not in one_liner
