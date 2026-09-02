"""Runtime tests for MCP server startup."""

from pathlib import Path

import dataiku_mcp
import dataiku_mcp.server as server
from dataiku_mcp.config import http, stdio
from dataiku_mcp.config.models import (
    HTTPAuthConfig,
    HTTPInteractiveAuthConfig,
    HTTPServerConfig,
)


def _server_settings():
    return HTTPServerConfig(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        public_url="https://mcp.example",
    )


def test_run_stdio_server_uses_stdio(monkeypatch):
    calls = []
    paths = []
    monkeypatch.setattr(stdio, "set_settings_path", lambda path: paths.append(path))
    monkeypatch.setattr(
        stdio,
        "initialize_current_instance",
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
        "initialize_current_instance",
        lambda: stdio_initializations.append(True),
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
        {
            "transport": "streamable-http",
            "host": "127.0.0.1",
            "port": 8000,
            "path": "/mcp",
        }
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
        lambda: HTTPAuthConfig(
            provider="oidc",
            issuer="https://idp.example",
            jwks_uri="https://idp.example/jwks",
            audience="dataiku-mcp",
            scope="mcp.access",
        ),
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


def test_http_auth_combines_oidc_login_with_direct_token_verification(monkeypatch):
    calls = {}
    verifier = object()
    interactive = object()
    combined = object()
    monkeypatch.setattr(
        http,
        "get_auth_settings",
        lambda: HTTPAuthConfig(
            provider="oidc",
            issuer="https://example.okta.com/oauth2/default",
            jwks_uri="https://example.okta.com/oauth2/default/v1/keys",
            audience="dataiku-mcp",
            scope="mcp.access",
            interactive=HTTPInteractiveAuthConfig(
                client_id="interactive-client",
                client_secret="interactive-secret",
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
        lambda: HTTPAuthConfig(
            provider="entra",
            issuer="https://login.microsoftonline.com/tenant-id/v2.0",
            jwks_uri="https://login.microsoftonline.com/common/discovery/v2.0/keys",
            audience="api://mcp-client",
            scope="mcp.access",
            interactive=HTTPInteractiveAuthConfig(
                client_id="interactive-client",
                client_secret="interactive-secret",
                tenant_id="tenant-id",
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
        "AzureProvider",
        lambda **kwargs: calls.update(interactive=kwargs) or interactive,
    )
    monkeypatch.setattr(
        server,
        "MultiAuth",
        lambda **kwargs: calls.update(combined=kwargs) or combined,
    )

    assert server._http_auth() is combined
    assert calls["interactive"] == {
        "client_id": "interactive-client",
        "client_secret": "interactive-secret",
        "tenant_id": "tenant-id",
        "required_scopes": ["mcp.access"],
        "base_url": "https://mcp.example",
        "identifier_uri": "api://mcp-client",
        "token_issuer": "https://login.microsoftonline.com/tenant-id/v2.0",
        "base_authority": "login.microsoftonline.com",
    }
    assert calls["combined"] == {
        "server": interactive,
        "verifiers": verifier,
    }
