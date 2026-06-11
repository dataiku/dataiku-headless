"""Tests for discussion commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_discussion_list(patch_client):
    result = runner.invoke(
        app,
        [
            "discussion",
            "list",
            "--type",
            "dataset",
            "--name",
            "ds1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "disc1" in result.output
    assert "Data quality issue" in result.output


def test_discussion_list_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "discussion",
            "list",
            "--type",
            "dataset",
            "--name",
            "ds1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "disc1"
    assert parsed[0]["topic"] == "Data quality issue"


def test_discussion_list_recipe(patch_client):
    """Discussions work across object types — test with recipe."""
    result = runner.invoke(
        app,
        [
            "discussion",
            "list",
            "--type",
            "recipe",
            "--name",
            "recipe1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "disc1" in result.output


def test_discussion_get(patch_client):
    result = runner.invoke(
        app,
        [
            "discussion",
            "get",
            "disc1",
            "--type",
            "dataset",
            "--name",
            "ds1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Data quality issue" in result.output


def test_discussion_get_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "discussion",
            "get",
            "disc1",
            "--type",
            "dataset",
            "--name",
            "ds1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "disc1"
    assert parsed["topic"] == "Data quality issue"
    assert len(parsed["replies"]) == 1
    assert parsed["replies"][0]["author"] == "admin"
    assert parsed["replies"][0]["text"] == "Fixed in v2"


def test_discussion_create(patch_client):
    result = runner.invoke(
        app,
        [
            "discussion",
            "create",
            "--type",
            "dataset",
            "--name",
            "ds1",
            "--topic",
            "Schema change",
            "--message",
            "Should we add a new column?",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    assert "Schema change" in result.output
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ds.get_object_discussions().create_discussion.assert_called_once_with(
        "Schema change", "Should we add a new column?"
    )


def test_discussion_reply(patch_client):
    result = runner.invoke(
        app,
        [
            "discussion",
            "reply",
            "disc1",
            "--type",
            "dataset",
            "--name",
            "ds1",
            "--message",
            "Looks good to me",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Replied" in result.output
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    disc = ds.get_object_discussions().get_discussion("disc1")
    disc.add_reply.assert_called_once_with("Looks good to me")


def test_discussion_unknown_type(patch_client):
    result = runner.invoke(
        app,
        [
            "discussion",
            "list",
            "--type",
            "unknown_thing",
            "--name",
            "foo",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown object type" in result.output
