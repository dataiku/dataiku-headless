"""Surf-cluster tests for recipe fixes #181, #188, #189, #195.

Focus on the pure, DSS-free helpers plus CLI signature/help assertions. The
end-to-end wiring is covered by the live_test commands in the IMPL report.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from dku_cli.commands.recipe import app
from dku_cli.commands.recipe._common import (
    _input_connection_name,
    _resolve_managed_output_connection,
)
from dku_cli.commands.recipe.core import (
    _declared_role_names,
    _resolve_plugin_role,
)
from dku_cli.commands.recipe.genai_embed import _files_in_folder_backing

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeDataset:
    def __init__(self, definition):
        self._definition = definition

    def get_definition(self):
        if self._definition is None:
            raise Exception("NotFoundException: dataset does not exist")
        return self._definition


class _FakeProj:
    def __init__(self, datasets):
        self._datasets = datasets

    def get_dataset(self, name):
        return _FakeDataset(self._datasets.get(name))


class _FakeClient:
    def __init__(self, connections, raise_on_list=False):
        self._connections = connections
        self._raise = raise_on_list

    def list_connections(self):
        if self._raise:
            raise Exception("admin only")
        return self._connections


# --------------------------------------------------------------------------- #
# #189 — plugin role resolution
# --------------------------------------------------------------------------- #
def test_declared_role_names_extracts_names():
    roles = [{"name": "dataset_a"}, {"name": "dataset_b"}, {"label": "no name"}]
    assert _declared_role_names(roles) == ["dataset_a", "dataset_b"]


def test_declared_role_names_handles_non_list():
    assert _declared_role_names(None) == []
    assert _declared_role_names({}) == []


def test_resolve_plugin_role_autoresolves_single_role():
    # Role omitted + exactly one declared role -> auto-resolve to it.
    assert (
        _resolve_plugin_role(None, ["dataset_a"], "input", True, "r", "CustomCode_x")
        == "dataset_a"
    )


def test_resolve_plugin_role_errors_when_default_main_not_declared():
    # Role omitted, multiple declared roles, no 'main' -> prescriptive error.
    with pytest.raises(SystemExit):
        _resolve_plugin_role(
            None,
            ["dataset_a", "dataset_b"],
            "input",
            True,
            "r",
            "CustomCode_dataset-diff",
        )


def test_resolve_plugin_role_accepts_valid_explicit_role():
    assert (
        _resolve_plugin_role(
            "dataset_a",
            ["dataset_a", "dataset_b"],
            "input",
            True,
            "r",
            "CustomCode_x",
        )
        == "dataset_a"
    )


def test_resolve_plugin_role_errors_on_invalid_explicit_role():
    with pytest.raises(SystemExit):
        _resolve_plugin_role(
            "bogus", ["dataset_a"], "output", True, "r", "CustomCode_x"
        )


def test_resolve_plugin_role_unreadable_manifest_falls_back_to_main():
    # Manifest unreadable (installed plugin) -> keep 'main' fallback, no error.
    assert _resolve_plugin_role(None, [], "input", False, "r", "CustomCode_x") == "main"
    assert (
        _resolve_plugin_role("custom", [], "input", False, "r", "CustomCode_x")
        == "custom"
    )


# --------------------------------------------------------------------------- #
# #195 — FilesInFolder backing folder resolution
# --------------------------------------------------------------------------- #
def test_files_in_folder_backing_returns_folder_id():
    proj = _FakeProj(
        {"docs_ds": {"type": "FilesInFolder", "params": {"folderSmartId": "FID123"}}}
    )
    assert _files_in_folder_backing(proj, "docs_ds") == "FID123"


def test_files_in_folder_backing_none_for_other_types():
    proj = _FakeProj({"sql_ds": {"type": "PostgreSQL", "params": {}}})
    assert _files_in_folder_backing(proj, "sql_ds") is None


def test_files_in_folder_backing_none_on_missing():
    proj = _FakeProj({})
    assert _files_in_folder_backing(proj, "nope") is None


# --------------------------------------------------------------------------- #
# #181 — output connection inheritance
# --------------------------------------------------------------------------- #
def test_input_connection_name_returns_managed_connection():
    proj = _FakeProj(
        {"src_pg": {"type": "PostgreSQL", "params": {"connection": "pg_conn"}}}
    )
    assert _input_connection_name(proj, "src_pg") == "pg_conn"


def test_input_connection_name_skips_non_managed_types():
    proj = _FakeProj(
        {"up": {"type": "UploadedFiles", "params": {"connection": "uploaded"}}}
    )
    assert _input_connection_name(proj, "up") is None


def test_input_connection_name_none_when_no_ref():
    assert _input_connection_name(_FakeProj({}), None) is None


def test_resolve_connection_prefers_input_when_allows_managed():
    proj = _FakeProj(
        {"src_pg": {"type": "PostgreSQL", "params": {"connection": "pg_conn"}}}
    )
    client = _FakeClient(
        {
            "pg_conn": {"allowManagedDatasets": True},
            "filesystem_managed": {"allowManagedDatasets": True},
        }
    )
    assert _resolve_managed_output_connection(client, proj, "src_pg") == "pg_conn"


def test_resolve_connection_falls_back_when_input_not_managed():
    # Input connection exists but does NOT allow managed datasets.
    proj = _FakeProj(
        {"src": {"type": "PostgreSQL", "params": {"connection": "ro_conn"}}}
    )
    client = _FakeClient(
        {
            "ro_conn": {"allowManagedDatasets": False},
            "filesystem_managed": {"allowManagedDatasets": True},
        }
    )
    assert (
        _resolve_managed_output_connection(client, proj, "src") == "filesystem_managed"
    )


def test_resolve_connection_falls_back_without_input():
    proj = _FakeProj({})
    client = _FakeClient({"filesystem_managed": {"allowManagedDatasets": True}})
    assert (
        _resolve_managed_output_connection(client, proj, None) == "filesystem_managed"
    )


def test_resolve_connection_admin_only_returns_input_conn():
    # list_connections raises (admin-only); input lives on a connection -> use it.
    proj = _FakeProj(
        {"src_pg": {"type": "Snowflake", "params": {"connection": "sf_conn"}}}
    )
    client = _FakeClient({}, raise_on_list=True)
    assert _resolve_managed_output_connection(client, proj, "src_pg") == "sf_conn"


# --------------------------------------------------------------------------- #
# CLI signature / help
# --------------------------------------------------------------------------- #
def test_create_embed_docs_help_drops_legacy_framing():
    result = runner.invoke(app, ["create-embed-docs", "--help"])
    assert result.exit_code == 0
    assert "DSS 14.4" not in result.output


def test_create_help_mentions_role_autoresolve():
    result = runner.invoke(app, ["create", "--help"])
    assert result.exit_code == 0
    assert "--input-role" in result.output
    assert "--output-role" in result.output
