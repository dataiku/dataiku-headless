"""Tests for dku eal (Enterprise Asset Library prompts)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _eal_mock(patch_client):
    eal = patch_client.get_enterprise_asset_library.return_value
    eal.list_collections.return_value = [
        {"id": "DATAIKU", "name": "Dataiku Collection", "description": ""},
        {"id": "MY_ASSETS", "name": "My Assets", "description": "Team prompts"},
    ]
    eal.list_prompts.return_value = [
        {
            "id": "p1",
            "name": "Error Logger",
            "collectionId": "DATAIKU",
            "description": "Formats errors",
            "tags": ["Formatting"],
        }
    ]
    collection = MagicMock()
    prompt = MagicMock()
    prompt.id = "p_new"
    prompt.get_raw.return_value = {
        "id": "p_new",
        "name": "FB Test",
        "content": "Summarize {{topic}}.",
    }
    collection.get_prompt.return_value = prompt
    collection.create_prompt.return_value = prompt
    eal.get_collection.return_value = collection
    return eal, collection, prompt


def test_eal_list_collections(patch_client):
    _eal_mock(patch_client)
    result = runner.invoke(app, ["eal", "list-collections", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [c["id"] for c in parsed] == ["DATAIKU", "MY_ASSETS"]


def test_eal_list_prompts_restricts_collections(patch_client):
    eal, _, _ = _eal_mock(patch_client)
    result = runner.invoke(app, ["eal", "list-prompts", "-c", "DATAIKU", "-o", "json"])
    assert result.exit_code == 0
    eal.list_prompts.assert_called_once_with(restrict_collections=["DATAIKU"])
    parsed = json.loads(result.output)
    assert parsed[0]["collection"] == "DATAIKU"
    assert parsed[0]["tags"] == "Formatting"


def test_eal_get_prompt(patch_client):
    eal, collection, _ = _eal_mock(patch_client)
    result = runner.invoke(
        app, ["eal", "get-prompt", "MY_ASSETS", "p_new", "-o", "json"]
    )
    assert result.exit_code == 0
    eal.get_collection.assert_called_once_with("MY_ASSETS")
    collection.get_prompt.assert_called_once_with("p_new")
    assert json.loads(result.output)["content"] == "Summarize {{topic}}."


def test_eal_create_prompt_from_file(patch_client, tmp_path):
    _, collection, _ = _eal_mock(patch_client)
    content_file = tmp_path / "prompt.txt"
    content_file.write_text("Summarize {{topic}} in bullets.")
    result = runner.invoke(
        app,
        [
            "eal",
            "create-prompt",
            "MY_ASSETS",
            "-n",
            "FB Test",
            "--content",
            f"@{content_file}",
            "--tags",
            "test, cli",
        ],
    )
    assert result.exit_code == 0
    collection.create_prompt.assert_called_once_with(
        name="FB Test",
        description=None,
        content="Summarize {{topic}} in bullets.",
        tags=["test", "cli"],
    )


def test_eal_create_prompt_filters_empty_tags(patch_client):
    """Empty/whitespace tag tokens ('a,,b', trailing comma) must be dropped so
    no blank tags persist on the governed prompt."""
    _, collection, _ = _eal_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "eal",
            "create-prompt",
            "MY_ASSETS",
            "-n",
            "FB Test",
            "--content",
            "hi",
            "--tags",
            "a, ,b,",
        ],
    )
    assert result.exit_code == 0
    assert collection.create_prompt.call_args.kwargs["tags"] == ["a", "b"]


def test_eal_delete_prompt_guarded(patch_client):
    _, _, prompt = _eal_mock(patch_client)
    blocked = runner.invoke(app, ["eal", "delete-prompt", "MY_ASSETS", "p_new"])
    assert blocked.exit_code == 77
    prompt.delete.assert_not_called()

    ok = runner.invoke(app, ["eal", "delete-prompt", "MY_ASSETS", "p_new", "-y"])
    assert ok.exit_code == 0
    prompt.delete.assert_called_once()
