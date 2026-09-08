"""Runtime tests for MCP server startup."""

from pathlib import Path

import dataiku_mcp
import dataiku_mcp.server as server
from dataiku_mcp.config import http, stdio
from dataiku_mcp.config.models import (
    EntraAuthConfig,
    GenericOIDCAuthConfig,
    GenericOIDCDelegationConfig,
    GenericOIDCInteractiveLoginConfig,
    HTTPServerConfig,
)


def _server_settings():
    return HTTPServerConfig(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        public_url="https://mcp.example",
    )


def _generic_auth_settings(interactive_login=None):
    return GenericOIDCAuthConfig(
        provider="generic_oidc",
        issuer="https://idp.example",
        jwks_uri="https://idp.example/jwks",
        required_audience="dataiku-mcp",
        required_scope="mcp.access",
        interactive_login=interactive_login,
        delegation=GenericOIDCDelegationConfig(
            token_endpoint="https://idp.example/token",
            client_id="exchange-client",
            client_secret="exchange-secret",
        ),
    )


def test_run_stdio_server_uses_stdio(monkeypatch):
    calls = []
    paths = []
    monkeypatch.setattr(stdio, "set_settings_path", lambda path: paths.append(path))
    monkeypatch.setattr(
        stdio,
        "initialize_config",
        lambda: calls.append("initialize_stdio"),
    )
    monkeypatch.setattr(
        dataiku_mcp.mcp,
        "run",
        lambda **kwargs: calls.append(("run", kwargs)),
    )

    dataiku_mcp.run_stdio_server(Path("/tmp/stdio-config.json"))

    assert paths == [Path("/tmp/stdio-config.json")]
    assert calls == ["initialize_stdio", ("run", {"transport": "stdio"})]


def test_run_http_server_uses_streamable_http(monkeypatch):
    calls = []
    paths = []
    stdio_initializations = []
    monkeypatch.setattr(
        stdio,
        "initialize_config",
        lambda: stdio_initializations.append(True),
    )
    monkeypatch.setattr(
        http, "initialize_config", lambda: calls.append("initialize_http")
    )
    monkeypatch.setattr(
        http,
        "get_server_settings",
        _server_settings,
    )
    auth = object()
    monkeypatch.setattr(server, "_http_auth", lambda: auth)
    monkeypatch.setattr(http, "set_settings_path", lambda path: paths.append(path))
    monkeypatch.setattr(dataiku_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    dataiku_mcp.run_http_server(Path("/tmp/http.json"))

    assert calls == [
        "initialize_http",
        {
            "transport": "streamable-http",
            "host": "127.0.0.1",
            "port": 8000,
            "path": "/mcp",
        },
    ]
    assert dataiku_mcp.mcp.auth is auth
    assert paths == [Path("/tmp/http.json")]
    assert stdio_initializations == []


def test_http_auth_uses_direct_token_verifier_without_interactive_login(monkeypatch):
    calls = []
    verifier = object()
    monkeypatch.setattr(
        http,
        "get_auth_settings",
        _generic_auth_settings,
    )
    monkeypatch.setattr(
        http,
        "get_server_settings",
        lambda: calls.append("server settings must not be loaded"),
    )
    monkeypatch.setattr(server, "JWTVerifier", lambda **kwargs: verifier)
    monkeypatch.setattr(
        server,
        "OIDCProxy",
        lambda **kwargs: calls.append("OIDC proxy must not be created"),
    )
    monkeypatch.setattr(
        server,
        "AzureProvider",
        lambda **kwargs: calls.append("Azure provider must not be created"),
    )
    monkeypatch.setattr(
        server,
        "MultiAuth",
        lambda **kwargs: calls.append("MultiAuth must not be created"),
    )

    assert server._http_auth() is verifier
    assert calls == []


def test_http_auth_uses_entra_direct_token_verifier_without_interactive_login(
    monkeypatch,
):
    calls = {}
    verifier = object()
    monkeypatch.setattr(
        http,
        "get_auth_settings",
        lambda: EntraAuthConfig(
            provider="entra",
            tenant_id="tenant-id",
            client_id="mcp-client",
            client_secret="mcp-secret",
            required_scope="mcp.access",
        ),
    )
    monkeypatch.setattr(
        http,
        "get_server_settings",
        lambda: calls.update(server="server settings must not be loaded"),
    )
    monkeypatch.setattr(
        server,
        "JWTVerifier",
        lambda **kwargs: calls.update(verifier=kwargs) or verifier,
    )
    monkeypatch.setattr(
        server,
        "OIDCProxy",
        lambda **kwargs: calls.update(oidc="OIDC proxy must not be created"),
    )
    monkeypatch.setattr(
        server,
        "AzureProvider",
        lambda **kwargs: calls.update(azure="Azure provider must not be created"),
    )
    monkeypatch.setattr(
        server,
        "MultiAuth",
        lambda **kwargs: calls.update(multi="MultiAuth must not be created"),
    )

    assert server._http_auth() is verifier
    assert calls == {
        "verifier": {
            "jwks_uri": (
                "https://login.microsoftonline.com/tenant-id/discovery/v2.0/keys"
            ),
            "issuer": "https://login.microsoftonline.com/tenant-id/v2.0",
            "audience": "mcp-client",
            "required_scopes": ["mcp.access"],
        }
    }


def test_http_auth_combines_oidc_login_with_direct_token_verification(
    monkeypatch,
):
    calls = {}
    verifier = object()
    interactive = object()
    combined = object()
    monkeypatch.setattr(
        http,
        "get_auth_settings",
        lambda: GenericOIDCAuthConfig(
            provider="generic_oidc",
            issuer="https://example.okta.com/oauth2/default",
            jwks_uri="https://example.okta.com/oauth2/default/v1/keys",
            required_audience="dataiku-mcp",
            required_scope="mcp.access",
            interactive_login=GenericOIDCInteractiveLoginConfig(
                client_id="interactive-client",
                client_secret="interactive-secret",
            ),
            delegation=GenericOIDCDelegationConfig(
                token_endpoint="https://idp.example/token",
                client_id="exchange-client",
                client_secret="exchange-secret",
            ),
        ),
    )
    monkeypatch.setattr(http, "get_server_settings", _server_settings)
    monkeypatch.setattr(
        server,
        "JWTVerifier",
        lambda **kwargs: calls.update(verifier=kwargs) or verifier,
    )
    monkeypatch.setattr(
        server,
        "OIDCProxy",
        lambda **kwargs: calls.update(interactive=kwargs) or interactive,
    )
    monkeypatch.setattr(
        server,
        "MultiAuth",
        lambda **kwargs: calls.update(combined=kwargs) or combined,
    )

    assert server._http_auth() is combined
    assert calls["verifier"] == {
        "jwks_uri": "https://example.okta.com/oauth2/default/v1/keys",
        "issuer": "https://example.okta.com/oauth2/default",
        "audience": "dataiku-mcp",
        "required_scopes": ["mcp.access"],
    }
    assert calls["interactive"] == {
        "config_url": (
            "https://example.okta.com/oauth2/default/.well-known/openid-configuration"
        ),
        "client_id": "interactive-client",
        "client_secret": "interactive-secret",
        "token_verifier": verifier,
        "base_url": "https://mcp.example",
        "forward_resource": False,
    }
    assert calls["combined"] == {
        "server": interactive,
        "verifiers": verifier,
    }


def test_http_auth_combines_entra_login_with_direct_token_verification(monkeypatch):
    calls = {}
    verifier = object()
    interactive = object()
    combined = object()
    monkeypatch.setattr(
        http,
        "get_auth_settings",
        lambda: EntraAuthConfig(
            provider="entra",
            tenant_id="tenant-id",
            client_id="mcp-client",
            client_secret="mcp-secret",
            required_scope="mcp.access",
            interactive_login=True,
        ),
    )
    monkeypatch.setattr(http, "get_server_settings", _server_settings)
    monkeypatch.setattr(
        server,
        "JWTVerifier",
        lambda **kwargs: calls.update(verifier=kwargs) or verifier,
    )
    monkeypatch.setattr(
        server,
        "AzureProvider",
        lambda **kwargs: calls.update(interactive=kwargs) or interactive,
    )
    monkeypatch.setattr(
        server,
        "MultiAuth",
        lambda **kwargs: calls.update(combined=kwargs) or combined,
    )

    assert server._http_auth() is combined
    assert calls["verifier"]["audience"] == "mcp-client"
    assert calls["interactive"] == {
        "client_id": "mcp-client",
        "client_secret": "mcp-secret",
        "tenant_id": "tenant-id",
        "required_scopes": ["mcp.access"],
        "base_url": "https://mcp.example",
        "token_issuer": "https://login.microsoftonline.com/tenant-id/v2.0",
    }
    assert calls["combined"] == {
        "server": interactive,
        "verifiers": verifier,
    }
