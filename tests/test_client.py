"""Tests for auth target resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dku_cli.auth import KeyResult, KeyStatus
from dku_cli.client import (
    AUTH_MODE_IN_POD_TICKET,
    get_client,
    resolve_auth,
    resolve_node_type,
)
from dku_cli.errors import AuthError


def _key_result(key):
    """Mirror get_api_key_with_status: found key → OK, missing → MISSING."""
    return KeyResult(key, KeyStatus.OK if key else KeyStatus.MISSING)


def test_resolve_auth_uses_dku_profile_env(monkeypatch):
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.setenv("DKU_PROFILE", "govern")

    with (
        patch("dku_cli.client.get_active_profile", return_value="default"),
        patch(
            "dku_cli.client.get_profile_config",
            side_effect=lambda profile: {
                "govern": {"url": "https://govern.example.com"},
                "default": {"url": "https://design.example.com"},
            }.get(profile, {}),
        ),
        patch(
            "dku_cli.client.get_api_key_with_status",
            side_effect=lambda profile: _key_result(
                {
                    "govern": "govern-key",
                    "default": "design-key",
                }.get(profile)
            ),
        ),
    ):
        assert resolve_auth() == ("https://govern.example.com", "govern-key")


def test_explicit_profile_overrides_dku_profile_env(monkeypatch):
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.setenv("DKU_PROFILE", "govern")

    with (
        patch(
            "dku_cli.client.get_profile_config",
            side_effect=lambda profile: {
                "govern": {"url": "https://govern.example.com"},
                "design": {"url": "https://design.example.com"},
            }.get(profile, {}),
        ),
        patch(
            "dku_cli.client.get_api_key_with_status",
            side_effect=lambda profile: _key_result(
                {
                    "govern": "govern-key",
                    "design": "design-key",
                }.get(profile)
            ),
        ),
    ):
        assert resolve_auth(profile="design") == (
            "https://design.example.com",
            "design-key",
        )


def test_resolve_node_type_uses_dku_profile_env(monkeypatch):
    monkeypatch.setenv("DKU_PROFILE", "govern")
    with (
        patch("dku_cli.client.get_active_profile", return_value="default"),
        patch(
            "dku_cli.client.get_profile_node_type",
            side_effect=lambda profile: {
                "govern": "govern",
                "default": "design",
            }.get(profile),
        ),
    ):
        assert resolve_node_type() == "GOVERN"


def test_get_client_in_pod_ticket_mode(monkeypatch):
    """A profile with auth_mode=in_pod_ticket builds a ticket-auth DSSClient
    from DKU_API_TICKET + DKU_BACKEND_HOST/PORT, ignoring profile URL/key."""
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.setenv("DKU_API_TICKET", "tkt-xyz")
    monkeypatch.setenv("DKU_BACKEND_HOST", "10.0.0.5")
    monkeypatch.setenv("DKU_BACKEND_PORT", "9000")

    sentinel = MagicMock(name="dssclient")
    with (
        patch(
            "dku_cli.client.get_profile_config",
            return_value={"auth_mode": AUTH_MODE_IN_POD_TICKET, "node_type": "DESIGN"},
        ),
        patch("dku_cli.client.get_active_profile", return_value="design"),
        patch("dataikuapi.DSSClient", return_value=sentinel) as mk,
    ):
        client = get_client()

    assert client is sentinel
    mk.assert_called_once_with("http://10.0.0.5:9000", internal_ticket="tkt-xyz")


def test_get_client_in_pod_ticket_mode_https(monkeypatch):
    """On a TLS instance DSS injects DKU_BACKEND_PROTOCOL=https. The client
    must target https:// (not http://) and skip verification of the backend's
    self-signed internal RPC cert — hardcoding http broke ticket auth on every
    TLS instance (gis2) with a TLS-alert BadStatusLine."""
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.setenv("DKU_API_TICKET", "tkt-xyz")
    monkeypatch.setenv("DKU_BACKEND_HOST", "10.0.0.5")
    monkeypatch.setenv("DKU_BACKEND_PORT", "9000")
    monkeypatch.setenv("DKU_BACKEND_PROTOCOL", "https")

    sentinel = MagicMock(name="dssclient")
    with (
        patch(
            "dku_cli.client.get_profile_config",
            return_value={"auth_mode": AUTH_MODE_IN_POD_TICKET, "node_type": "DESIGN"},
        ),
        patch("dku_cli.client.get_active_profile", return_value="design"),
        patch("dataikuapi.DSSClient", return_value=sentinel) as mk,
    ):
        client = get_client()

    assert client is sentinel
    mk.assert_called_once_with(
        "https://10.0.0.5:9000", internal_ticket="tkt-xyz", no_check_certificate=True
    )
    # REQUESTS_CA_BUNDLE (set by the Replicate startup script from the base
    # cert) must not be able to re-enable verification against the wrong CA.
    assert sentinel._session.trust_env is False
    assert sentinel._session.verify is False


def test_get_client_in_pod_ticket_mode_http_default(monkeypatch):
    """Without DKU_BACKEND_PROTOCOL the scheme defaults to http (local DSS),
    and no cert kwargs/overrides are applied."""
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.delenv("DKU_BACKEND_PROTOCOL", raising=False)
    monkeypatch.setenv("DKU_API_TICKET", "tkt-xyz")
    monkeypatch.setenv("DKU_BACKEND_HOST", "10.0.0.5")
    monkeypatch.setenv("DKU_BACKEND_PORT", "9000")

    sentinel = MagicMock(name="dssclient")
    with (
        patch(
            "dku_cli.client.get_profile_config",
            return_value={"auth_mode": AUTH_MODE_IN_POD_TICKET},
        ),
        patch("dku_cli.client.get_active_profile", return_value="design"),
        patch("dataikuapi.DSSClient", return_value=sentinel) as mk,
    ):
        client = get_client()

    assert client is sentinel
    mk.assert_called_once_with("http://10.0.0.5:9000", internal_ticket="tkt-xyz")


def test_get_client_ticket_mode_missing_env_raises(monkeypatch):
    """Ticket-mode profile with no DSS-injected env fails fast with a
    prescriptive AuthError — running outside a DSS-launched container."""
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.delenv("DKU_API_TICKET", raising=False)
    monkeypatch.delenv("DKU_BACKEND_HOST", raising=False)
    monkeypatch.delenv("DKU_BACKEND_PORT", raising=False)

    with (
        patch(
            "dku_cli.client.get_profile_config",
            return_value={"auth_mode": AUTH_MODE_IN_POD_TICKET, "node_type": "DESIGN"},
        ),
        patch("dku_cli.client.get_active_profile", return_value="design"),
    ):
        with pytest.raises(AuthError) as exc:
            get_client()
    msg = str(exc.value)
    assert "in_pod_ticket" in msg
    assert "DKU_API_TICKET" in msg


def test_get_client_explicit_url_overrides_ticket_mode(monkeypatch):
    """Passing --url should bypass ticket auth even if the profile is in
    ticket mode — the caller is intentionally targeting another host."""
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.setenv("DKU_API_TICKET", "tkt-xyz")
    monkeypatch.setenv("DKU_BACKEND_HOST", "10.0.0.5")
    monkeypatch.setenv("DKU_BACKEND_PORT", "9000")

    sentinel = MagicMock(name="dssclient")
    with (
        patch(
            "dku_cli.client.get_profile_config",
            return_value={"auth_mode": AUTH_MODE_IN_POD_TICKET},
        ),
        patch("dku_cli.client.get_active_profile", return_value="design"),
        patch(
            "dku_cli.client.get_api_key_with_status",
            return_value=_key_result("explicit-key-from-keychain"),
        ),
        patch("dataikuapi.DSSClient", return_value=sentinel) as mk,
    ):
        # Only URL passed explicitly — falls through to API-key resolution.
        client = get_client(url="https://other.example.com", api_key="other-key")

    assert client is sentinel
    mk.assert_called_once_with("https://other.example.com", api_key="other-key")


def test_get_client_api_key_mode_unaffected(monkeypatch):
    """A profile WITHOUT auth_mode falls through to the original
    API-key code path even when ticket env vars happen to be set."""
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_API_KEY", raising=False)
    monkeypatch.setenv("DKU_API_TICKET", "tkt-xyz")
    monkeypatch.setenv("DKU_BACKEND_HOST", "10.0.0.5")
    monkeypatch.setenv("DKU_BACKEND_PORT", "9000")

    sentinel = MagicMock(name="dssclient")
    with (
        patch(
            "dku_cli.client.get_profile_config",
            return_value={"url": "https://design.example.com"},
        ),
        patch("dku_cli.client.get_active_profile", return_value="design"),
        patch(
            "dku_cli.client.get_api_key_with_status",
            return_value=_key_result("design-key"),
        ),
        patch("dataikuapi.DSSClient", return_value=sentinel) as mk,
    ):
        client = get_client()

    assert client is sentinel
    mk.assert_called_once_with("https://design.example.com", api_key="design-key")
