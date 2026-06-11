"""`--format`/`-o` are accepted at any position in the command line.

Agents reflexively append the output flag after the subcommand
(`dku agent list -P X --format json`). Click only accepts group-level options
before the noun, so `main._extract_format_flag` lifts the flag at every parse
level. These tests pin that behavior end-to-end through the CLI.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _ids_output(result) -> list[str]:
    return [line for line in result.stdout.splitlines() if line]


def test_trailing_format_long(patch_client):
    result = runner.invoke(
        app, ["dataset", "list", "--project", "PROJ1", "--format", "json"]
    )
    assert result.exit_code == 0
    assert isinstance(json.loads(result.stdout), list)


def test_trailing_format_equals(patch_client):
    result = runner.invoke(
        app, ["dataset", "list", "--project", "PROJ1", "--format=ids"]
    )
    assert result.exit_code == 0
    for line in _ids_output(result):
        assert "\t" not in line


def test_trailing_short_o(patch_client):
    result = runner.invoke(app, ["dataset", "list", "-P", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    assert isinstance(json.loads(result.stdout), list)


def test_leading_format_still_works(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "dataset", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert isinstance(json.loads(result.stdout), list)


def test_mid_position_between_group_and_command(patch_client):
    result = runner.invoke(
        app, ["dataset", "--format", "json", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert isinstance(json.loads(result.stdout), list)


def test_invalid_format_value_fails_at_parse(patch_client):
    result = runner.invoke(app, ["dataset", "list", "-P", "PROJ1", "--format", "yaml"])
    assert result.exit_code == 2
    assert "json, csv, ids, quiet" in result.output + str(result.stderr)
    patch_client.get_project.assert_not_called()


def test_format_missing_value_fails_at_parse(patch_client):
    result = runner.invoke(app, ["dataset", "list", "-P", "PROJ1", "--format"])
    assert result.exit_code == 2
    assert "requires an argument" in result.output + str(result.stderr)


def test_tokens_after_double_dash_untouched():
    from dku_cli.main import _extract_format_flag

    args = ["query", "--", "--format", "json"]
    assert _extract_format_flag(args, None) == args


def test_command_owned_format_flag_is_not_hijacked(patch_client):
    """`folder create-dataset --format csv` means FILE format — the command owns
    the flag, so the global extraction must leave it alone."""
    from unittest.mock import MagicMock

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    ds = MagicMock()
    settings = MagicMock()
    raw: dict = {}
    settings.get_raw.return_value = raw
    ds.get_settings.return_value = settings
    folder.create_dataset_from_files.return_value = ds

    result = runner.invoke(
        app,
        [
            "folder",
            "create-dataset",
            "folder1",
            "ds",
            "--format",
            "csv",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["formatType"] == "csv"


def test_short_o_still_global_next_to_owned_format(patch_client):
    """A command that owns `--format` still honors the global `-o` spelling."""
    from unittest.mock import MagicMock

    folder = patch_client.get_project("PROJ1").get_managed_folder("folder1")
    ds = MagicMock()
    settings = MagicMock()
    settings.get_raw.return_value = {}
    ds.get_settings.return_value = settings
    folder.create_dataset_from_files.return_value = ds

    result = runner.invoke(
        app,
        [
            "folder",
            "create-dataset",
            "folder1",
            "ds",
            "--format",
            "csv",
            "-P",
            "PROJ1",
            "-o",
            "quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == ""
