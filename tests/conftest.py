"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.fixtures.mock_client import create_mock_client


@pytest.fixture(autouse=True)
def _reset_output_modes():
    """Reset output modes between tests so global CLI flags do not leak.

    Compact mode matters most: any test that invokes the CLI with ``--compact``
    (e.g. the DKU_AGENT_HELP spec tests) flips a module-level global in
    ``dku_cli.output`` that would otherwise leak into later JSON-rendering
    tests and silently drop None/empty fields from their output. The reset
    itself lives in ``output.reset_output_modes`` so new output-mode globals
    get covered in one place.
    """
    from dku_cli.output import reset_output_modes

    reset_output_modes()
    yield
    reset_output_modes()


@pytest.fixture(autouse=True)
def _isolate_config_files(tmp_path, monkeypatch):
    """Redirect config + credentials files to a temp dir for EVERY test.

    Without this, tests that call ``store_api_key`` / ``set_profile_credential_store``
    (e.g. while exercising the keychain fallback) write to the developer's REAL
    ``~/.../dku/config.toml`` and ``credentials.toml``. That silently flips the
    active profile's ``credential_store`` pointer to "file" and surfaces later as
    a spurious "No API key configured" in live ``dku`` use. Isolating the paths
    keeps the suite from ever touching real credentials.
    """
    monkeypatch.setattr(
        "dku_cli.config.CONFIG_FILE", tmp_path / "config.toml", raising=False
    )
    monkeypatch.setattr(
        "dku_cli.config.CREDENTIALS_FILE", tmp_path / "credentials.toml", raising=False
    )
    monkeypatch.setattr(
        "dku_cli.auth.CREDENTIALS_FILE", tmp_path / "credentials.toml", raising=False
    )
    # Unit tests must never see ambient DSS auth: developers export
    # DKU_URL/DKU_API_KEY in their shell, and with those set the node-type
    # guard (helpers._has_auth_overrides) probes the LIVE instance and every
    # govern test fails with exit 4 (wrong_node_type on a DESIGN node).
    for var in ("DKU_URL", "DKU_API_KEY", "DKU_PROJECT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mock_client():
    """Create a mock DSSClient with common methods."""
    return create_mock_client()


@pytest.fixture
def patch_client(mock_client):
    """Patch get_client and get_govern_client everywhere they're imported.

    Also stubs resolve_node_type so the node-type guard in
    ``get_client_from_ctx`` does not block tests based on whatever profile
    the developer has configured locally.
    """
    govern_client = mock_client.get_govern_client.return_value
    with (
        patch("dku_cli.client.get_client", return_value=mock_client),
        patch("dku_cli.helpers.get_client", return_value=mock_client),
        patch("dku_cli.client.get_govern_client", return_value=govern_client),
        patch("dku_cli.helpers.get_govern_client", return_value=govern_client),
        patch("dku_cli.helpers.resolve_node_type", return_value=None),
    ):
        yield mock_client
