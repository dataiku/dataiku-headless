"""Tests for the agent-help examples registry and its spec rendering."""

from __future__ import annotations

import json
import shlex

import click
from typer.main import get_command
from typer.testing import CliRunner

from dku_cli.examples import EXAMPLES, examples_for
from dku_cli.main import app

runner = CliRunner()


def _resolve(path: tuple[str, ...]) -> click.Command | None:
    cmd: click.Command = get_command(app)
    for seg in path:
        if not isinstance(cmd, click.Group) or seg not in cmd.commands:
            return None
        cmd = cmd.commands[seg]
    return cmd


def test_every_registered_path_exists_in_command_tree():
    for path in EXAMPLES:
        assert _resolve(path) is not None, f"example path not in CLI: {' '.join(path)}"


def test_every_example_starts_with_dku():
    for path, examples in EXAMPLES.items():
        assert examples, f"empty example list for {' '.join(path)}"
        for ex in examples:
            assert ex.startswith("dku "), ex


# Output knobs removed in the --format unification; examples must not teach them.
_REMOVED_FLAGS = {"-o", "--output", "--quiet", "--compact", "--errors"}


def test_no_example_uses_removed_output_flags():
    for examples in EXAMPLES.values():
        for ex in examples:
            tokens = set(shlex.split(ex))
            assert not tokens & _REMOVED_FLAGS, ex


def test_format_flag_appears_before_the_noun():
    for path, examples in EXAMPLES.items():
        noun = path[0]
        for ex in examples:
            tokens = shlex.split(ex)
            if "--format" in tokens:
                assert tokens.index("--format") < tokens.index(noun), ex


def test_examples_are_unique_per_command():
    for path, examples in EXAMPLES.items():
        assert len(examples) == len(set(examples)), (
            f"duplicate example for {' '.join(path)}"
        )


def test_example_flags_exist_on_their_command():
    root = get_command(app)
    global_flags = {
        o for p in root.params if isinstance(p, click.Option) for o in p.opts
    }
    for path, examples in EXAMPLES.items():
        cmd = _resolve(path)
        known = global_flags | {
            o
            for p in cmd.params
            if isinstance(p, click.Option)
            for o in (*p.opts, *p.secondary_opts)
        }
        for ex in examples:
            for token in shlex.split(ex):
                if token.startswith("-") and not token.lstrip("-").isdigit():
                    assert token in known, (
                        f"{token!r} not a flag of {' '.join(path)}: {ex}"
                    )


def test_agent_tool_example_uses_real_builtin_type():
    """Free-form enum values can't be checked by the flag-existence guard."""
    from dku_cli.commands.agent_tool import BUILTIN_TOOL_TYPES

    (example,) = EXAMPLES[("agent-tool", "create")]
    tokens = shlex.split(example)
    type_value = tokens[tokens.index("--type") + 1]
    assert type_value in BUILTIN_TOOL_TYPES


def test_examples_for_unregistered_path_is_empty():
    assert examples_for(["no-such", "command"]) == []


def test_agent_help_includes_examples_for_registered_command():
    result = runner.invoke(app, ["recipe", "create-join", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert spec["examples"] == EXAMPLES[("recipe", "create-join")]


def test_agent_help_omits_examples_when_unregistered():
    result = runner.invoke(app, ["recipe", "delete", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert "examples" not in spec


def test_group_help_does_not_include_examples():
    result = runner.invoke(app, ["recipe", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.stdout)
    assert "examples" not in spec
    assert "examples" not in json.dumps(spec["commands"])
