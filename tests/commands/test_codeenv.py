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


def test_codeenv_create_basic(patch_client):
    """Create without any packages — no set_definition or rebuild calls."""
    result = runner.invoke(app, ["code-env", "create", "new_env"])
    assert result.exit_code == 0
    assert "Created code environment" in result.output
    patch_client.create_code_env.assert_called_once()
    # No packages specified → set_definition and update_packages should NOT be called
    env = patch_client.get_code_env.return_value
    env.set_definition.assert_not_called()
    env.update_packages.assert_not_called()


def test_codeenv_create_with_packages(patch_client):
    """--package flag triggers a post-create set_definition + rebuild."""
    result = runner.invoke(
        app,
        [
            "code-env",
            "create",
            "new_env",
            "--package",
            "pandas>=2.0",
            "--package",
            "pdfplumber",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created code environment" in result.output
    assert "Set 2 package(s)" in result.output
    assert "Rebuild complete" in result.output

    patch_client.create_code_env.assert_called_once()
    env = patch_client.get_code_env.return_value
    env.set_definition.assert_called_once()
    # Inspect the package list that was written
    written_def = env.set_definition.call_args[0][0]
    assert "pandas>=2.0" in written_def["specPackageList"]
    assert "pdfplumber" in written_def["specPackageList"]
    env.update_packages.assert_called_once()


def test_codeenv_create_with_requirements_literal(patch_client):
    """--requirements accepts a literal multi-line string."""
    result = runner.invoke(
        app,
        [
            "code-env",
            "create",
            "new_env",
            "--requirements",
            "pandas>=2.0\nnumpy>=1.22",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Set 2 package(s)" in result.output
    env = patch_client.get_code_env.return_value
    written_def = env.set_definition.call_args[0][0]
    assert "pandas>=2.0" in written_def["specPackageList"]
    assert "numpy>=1.22" in written_def["specPackageList"]


def test_codeenv_create_with_requirements_file(patch_client, tmp_path):
    """--requirements @file.txt reads the file contents."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("pdfplumber\nopenpyxl\nrequests>=2.28\n")
    result = runner.invoke(
        app,
        [
            "code-env",
            "create",
            "new_env",
            "--requirements",
            f"@{req_file}",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Set 3 package(s)" in result.output
    env = patch_client.get_code_env.return_value
    written_def = env.set_definition.call_args[0][0]
    assert "pdfplumber" in written_def["specPackageList"]
    assert "openpyxl" in written_def["specPackageList"]
    assert "requests>=2.28" in written_def["specPackageList"]


def test_codeenv_create_combines_requirements_and_packages(patch_client):
    """--requirements and --package combine into a single package list."""
    result = runner.invoke(
        app,
        [
            "code-env",
            "create",
            "new_env",
            "--requirements",
            "pandas>=2.0",
            "--package",
            "pdfplumber",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Set 2 package(s)" in result.output
    env = patch_client.get_code_env.return_value
    written_def = env.set_definition.call_args[0][0]
    assert "pandas>=2.0" in written_def["specPackageList"]
    assert "pdfplumber" in written_def["specPackageList"]
