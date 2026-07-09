"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.fixtures.mock_client import create_mock_client


@pytest.fixture(autouse=True)
def _reset_output_modes():
    """Reset output modes between tests so global CLI flags do not leak.

    Agent/format mode matters most: any test that invokes the CLI with
    ``--format`` or agent help flips module-level globals in
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
    # Settings-mutation commands take a per-object write lock — keep the lock
    # files out of the developer's real cache dir.
    monkeypatch.setattr("dku_cli.helpers.LOCK_DIR", tmp_path / "locks", raising=False)
    # Unit tests must never see ambient DSS auth: developers export
    # DKU_URL/DKU_API_KEY in their shell, and with those set the node-type
    # guard (helpers._has_auth_overrides) probes the LIVE instance and every
    # govern test fails with exit 4 (wrong_node_type on a DESIGN node).
    for var in (
        "DKU_URL",
        "DKU_API_KEY",
        "DKU_PROJECT",
        "DKU_FORMAT",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def real_keyring():
    """Opt back in to the real ``_keyring_available`` probe.

    The autouse ``_neutralize_keyring`` fixture below forces
    ``dku_cli.auth._keyring_available`` to return False for EVERY test so a
    stray auth test can never reach the developer's real macOS Keychain.
    A test that genuinely needs the real detection logic (or wants to drive
    it itself) requests this fixture; it runs first, restores the original
    callable, and the autouse fixture then sees the opt-in and skips its
    patch. Tests that patch ``_keyring_available`` per-test (as
    ``tests/test_auth.py`` does) don't need this — their ``with patch(...)``
    simply overrides the autouse default inside their own context.
    """
    return True


@pytest.fixture(autouse=True)
def _neutralize_keyring(request, monkeypatch):
    """Globally stub keyring detection to False unless a test opts out.

    ``store_api_key`` / ``get_api_key_with_status`` call
    ``dku_cli.auth._keyring_available()`` and, when it returns True, hit the
    OS keyring backend — on macOS that is the developer's real Keychain. The
    per-test isolation in ``_isolate_config_files`` redirects the config and
    credentials FILES, but nothing stops a future test that forgets to patch
    ``_keyring_available`` from touching the real Keychain. This fixture
    closes that gap for the whole suite by defaulting the probe to False.

    Opt out by requesting the ``real_keyring`` fixture (restores the original
    detection). Per-test ``patch("dku_cli.auth._keyring_available", ...)``
    calls compose fine: they override this default within their context.
    """
    if "real_keyring" in request.fixturenames:
        return
    monkeypatch.setattr("dku_cli.auth._keyring_available", lambda: False, raising=False)


@pytest.fixture
def mock_client():
    """Create a mock DSSClient with common methods."""
    client = create_mock_client()
    return client


@pytest.fixture
def patch_client(mock_client):
    """Patch get_client + get_govern_client everywhere they're imported.

    Also stubs resolve_node_type so the node-type guard in
    ``get_client_from_ctx`` does not block tests based on whatever profile
    the developer has configured locally.

    Govern commands invoke the standalone ``get_govern_client`` factory
    (not ``client.get_govern_client()``), so the mock_client's prebuilt
    govern stub at ``mock_client.get_govern_client()`` has to be wired
    through both the client and helpers import paths — otherwise govern
    tests hit the real DSS server and fail with a 404 on
    ``/dip/publicapi/admin/...``.
    """
    govern_client = mock_client.get_govern_client()
    with (
        patch("dku_cli.client.get_client", return_value=mock_client),
        patch("dku_cli.helpers.get_client", return_value=mock_client),
        patch("dku_cli.client.get_govern_client", return_value=govern_client),
        patch("dku_cli.helpers.get_govern_client", return_value=govern_client),
        patch("dku_cli.helpers.resolve_node_type", return_value=None),
    ):
        yield mock_client
