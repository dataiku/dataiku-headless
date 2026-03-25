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
        app,
        ["wiki", "create", "My Article", "--body", "Hello world", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    wiki.create_article.assert_called_once_with("My Article", content="Hello world")


def test_wiki_create_from_file(tmp_path, patch_client):
    md_file = tmp_path / "content.md"
    md_file.write_text("# From File\nBody text here.")

    result = runner.invoke(
        app,
        [
            "wiki",
            "create",
            "File Article",
            "--body",
            f"@{md_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    wiki.create_article.assert_called_once_with(
        "File Article", content="# From File\nBody text here."
    )


def test_wiki_create_if_not_exists(patch_client):
    """--if-not-exists suppresses already-exists errors."""
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    wiki.create_article.side_effect = Exception("409 Conflict: article already exists")
    result = runner.invoke(
        app,
        [
            "wiki",
            "create",
            "Existing",
            "--body",
            "Content",
            "--project",
            "PROJ1",
            "--if-not-exists",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_wiki_create_already_exists_fails(patch_client):
    """Without --if-not-exists, already-exists errors propagate."""
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    wiki.create_article.side_effect = Exception("409 Conflict: article already exists")
    result = runner.invoke(
        app,
        ["wiki", "create", "Existing", "--body", "Content", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


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
    assert parsed["name"] == "Home"


# --- wiki update ---


def test_wiki_update_body(patch_client):
    result = runner.invoke(
        app,
        ["wiki", "update", "article1", "--body", "New content", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output


def test_wiki_update_title(patch_client):
    result = runner.invoke(
        app,
        ["wiki", "update", "article1", "--title", "New Title", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output


def test_wiki_update_both(patch_client):
    result = runner.invoke(
        app,
        [
            "wiki",
            "update",
            "article1",
            "--title",
            "New",
            "--body",
            "Content",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


def test_wiki_update_no_args_fails(patch_client):
    result = runner.invoke(
        app,
        ["wiki", "update", "article1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_wiki_update_from_file(tmp_path, patch_client):
    md_file = tmp_path / "update.md"
    md_file.write_text("# Updated\nNew body.")

    result = runner.invoke(
        app,
        ["wiki", "update", "article1", "--body", f"@{md_file}", "--project", "PROJ1"],
    )
    assert result.exit_code == 0


# --- wiki delete ---


def test_wiki_delete_with_confirm(patch_client):
    result = runner.invoke(
        app, ["wiki", "delete", "article1", "--project", "PROJ1", "--confirm"]
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output
    proj = patch_client.get_project("PROJ1")
    wiki = proj.get_wiki()
    article = wiki.get_article("article1")
    article.delete.assert_called_once()


def test_wiki_delete_without_confirm(patch_client):
    result = runner.invoke(app, ["wiki", "delete", "article1", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_wiki_delete_with_yes(patch_client):
    result = runner.invoke(
        app, ["wiki", "delete", "article1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
