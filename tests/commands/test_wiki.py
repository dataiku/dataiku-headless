"""Tests for wiki commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_wiki_list(patch_client):
    result = runner.invoke(app, ["wiki", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "article1" in result.output


def test_wiki_list_json(patch_client):
    result = runner.invoke(app, ["wiki", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "article1"
    assert parsed[0]["title"] == "Home"


def test_wiki_create(patch_client):
    result = runner.invoke(
        app, ["wiki", "create", "My Article", "--body", "Hello world", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    wiki.create_article.assert_called_once_with("My Article", "Hello world")


def test_wiki_create_from_file(tmp_path, patch_client):
    md_file = tmp_path / "content.md"
    md_file.write_text("# From File\nBody text here.")

    result = runner.invoke(
        app,
        ["wiki", "create", "File Article", "--body", f"@{md_file}", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    wiki.create_article.assert_called_once_with("File Article", "# From File\nBody text here.")


def test_wiki_get(patch_client):
    result = runner.invoke(app, ["wiki", "get", "article1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Home" in result.output
    assert "# Welcome" in result.output


def test_wiki_get_json(patch_client):
    result = runner.invoke(
        app, ["wiki", "get", "article1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["body"] == "# Welcome"
    assert parsed["article"]["name"] == "Home"
