"""Regression test for issue #191.

`dku wiki create --body @path` must fail loudly when the @file is missing or
empty. `--body -` must also reject empty stdin instead of creating a blank page.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_wiki_create_missing_body_file_fails_loudly(patch_client):
    missing = "/nonexistent_dir_surf191/does_not_exist.md"
    assert not Path(missing).exists()
    result = runner.invoke(
        app, ["wiki", "create", "Surf191", "-P", "PROJ1", "--body", f"@{missing}"]
    )
    # typer.BadParameter -> exit code 2, prescriptive "File not found", no article.
    assert result.exit_code != 0
    assert "File not found" in result.output


def test_wiki_create_empty_body_file_fails_loudly(patch_client):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.flush()
        empty_path = f.name
    result = runner.invoke(
        app,
        ["wiki", "create", "Surf191Empty", "-P", "PROJ1", "--body", f"@{empty_path}"],
    )
    assert result.exit_code != 0
    assert "File is empty" in result.output


def test_wiki_create_empty_stdin_fails_loudly(patch_client):
    result = runner.invoke(
        app,
        ["wiki", "create", "Surf191Stdin", "-P", "PROJ1", "--body", "-"],
        input="",
    )
    assert result.exit_code != 0
    assert "stdin is empty" in result.output
