"""Tests for code-env commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_codeenv_list(patch_client):
    result = runner.invoke(app, ["code-env", "list"])
    assert result.exit_code == 0
    assert "py39" in result.output


def test_codeenv_list_json(patch_client):
    result = runner.invoke(app, ["code-env", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "py39"


def test_codeenv_get(patch_client):
    result = runner.invoke(app, ["code-env", "get", "py39"])
    assert result.exit_code == 0
    assert "py39" in result.output


def test_codeenv_get_json(patch_client):
    result = runner.invoke(app, ["code-env", "get", "py39", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["envName"] == "py39"


def test_codeenv_delete(patch_client):
    result = runner.invoke(app, ["code-env", "delete", "py39"])
    assert result.exit_code == 0


def test_codeenv_update(patch_client):
    result = runner.invoke(app, ["code-env", "update", "py39"])
    assert result.exit_code == 0


# =============================================================================
# codeenv jupyter / update-images / update (with new flags)
# =============================================================================


def test_codeenv_jupyter_enable(patch_client):
    result = runner.invoke(app, ["code-env", "jupyter", "py39", "--enable"])
    assert result.exit_code == 0
    patch_client.get_code_env.return_value.set_jupyter_support.assert_called_once()
    _, kwargs = patch_client.get_code_env.return_value.set_jupyter_support.call_args
    assert kwargs["active"] is True


def test_codeenv_jupyter_disable(patch_client):
    result = runner.invoke(app, ["code-env", "jupyter", "py39", "--disable"])
    assert result.exit_code == 0
    _, kwargs = patch_client.get_code_env.return_value.set_jupyter_support.call_args
    assert kwargs["active"] is False


def test_codeenv_update_images(patch_client):
    result = runner.invoke(app, ["code-env", "update-images", "py39"])
    assert result.exit_code == 0
    patch_client.get_code_env.return_value.update_images.assert_called_once()


def test_codeenv_update_force_rebuild(patch_client):
    result = runner.invoke(app, ["code-env", "update", "py39", "--force-rebuild"])
    assert result.exit_code == 0
    _, kwargs = patch_client.get_code_env.return_value.update_packages.call_args
    assert kwargs["force_rebuild_env"] is True
