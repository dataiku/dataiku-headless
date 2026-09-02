"""HTTP instance selection is a preference, not an authorization allow-list."""

import asyncio
import json
from pathlib import Path

import pytest

import dataiku_mcp.auth as auth
from dataiku_mcp.config import http, request
from dataiku_mcp.config.models import (
    HTTPAuthConfig,
    HTTPConfig,
    HTTPInteractiveAuthConfig,
    HTTPServerConfig,
    HTTPTokenExchangeConfig,
    DSSInstance,
)


@pytest.fixture
def http_config(monkeypatch, tmp_path):
    path = tmp_path / "http-config.json"
    path.write_text(
        json.dumps(
            {
                "server": {
                    "host": "127.0.0.1",
                    "port": 8000,
                    "path": "/mcp",
                    "public_url": "https://mcp.example",
                },
                "oidc": {
                    "provider": "oidc",
                    "issuer": "https://idp.example",
                    "jwks_uri": "https://idp.example/jwks",
                    "audience": "dataiku-mcp",
                    "scope": "mcp.access",
                    "interactive": {
                        "client_id": "interactive-client",
                        "client_secret": "interactive-secret",
                    },
                },
                "token_exchange": {
                    "url": "https://idp.example/token",
                    "client_id": "exchange-client",
                    "client_secret": "exchange-secret",
                },
                "dss_instances": {
                    "sandbox": {
                        "url": "https://sandbox.example",
                        "audience": "dss-sandbox",
                        "scope": "dss.api",
                    },
                    "prod": {
                        "url": "https://prod.example",
                        "audience": "dss-prod",
                        "scope": "dss.api",
                    },
                },
                "user_selections": {},
            }
        )
    )
    http.set_settings_path(path)
    yield path
    http.set_settings_path(None)


def test_http_config_uses_canonical_default(monkeypatch):
    default_path = Path.home() / ".dataiku" / "http-config.json"
    monkeypatch.setattr(http, "_settings_path", None)

    assert http.DEFAULT_SETTINGS_PATH == default_path
    assert http.get_settings_path() == default_path


def test_http_config_requires_existing_settings_file(tmp_path, monkeypatch):
    path = tmp_path / "missing.json"
    monkeypatch.setattr(http, "_settings_path", path)

    with pytest.raises(
        ValueError,
        match="HTTP instance configuration was not found",
    ):
        http.get_server_settings()


def test_http_config_rejects_non_object(tmp_path, monkeypatch):
    path = tmp_path / "http-config.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(http, "_settings_path", path)

    with pytest.raises(
        ValueError,
        match="HTTP instance configuration must be a JSON object",
    ):
        http.get_server_settings()


@pytest.mark.parametrize(
    "location",
    [(), ("server",), ("dss_instances", "sandbox")],
)
def test_http_config_rejects_unknown_fields(http_config, location):
    document = json.loads(http_config.read_text())
    target = document
    for key in location:
        target = target[key]
    target["unexpected"] = True
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="unknown fields"):
        http.get_server_settings()


def test_http_config_rejects_obsolete_user_defaults_key(http_config):
    document = json.loads(http_config.read_text())
    document["user_defaults"] = document.pop("user_selections")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="unknown fields.*user_defaults"):
        http.get_server_settings()


def test_http_config_validates_the_complete_document(http_config):
    document = json.loads(http_config.read_text())
    document.pop("oidc")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="object named 'oidc'"):
        http.get_server_settings()


@pytest.mark.parametrize("public_url", ["mcp.example", "/mcp", "ftp://mcp.example"])
def test_http_config_requires_absolute_http_public_url(http_config, public_url):
    document = json.loads(http_config.read_text())
    document["server"]["public_url"] = public_url
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="absolute 'server.public_url'"):
        http.get_server_settings()


def test_http_config_allows_direct_bearer_only(http_config):
    document = json.loads(http_config.read_text())
    document["server"].pop("public_url")
    document["oidc"].pop("interactive")
    http_config.write_text(json.dumps(document))

    assert http.get_server_settings().public_url == ""
    assert http.get_auth_settings().interactive is None


def test_http_config_requires_public_url_for_interactive_login(http_config):
    document = json.loads(http_config.read_text())
    document["server"].pop("public_url")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="server.public_url.*interactive OAuth"):
        http.get_auth_settings()


def test_http_config_rejects_entra_tenant_for_generic_oidc(http_config):
    document = json.loads(http_config.read_text())
    document["oidc"]["interactive"]["tenant_id"] = "tenant-id"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="tenant_id.*only valid for Entra"):
        http.get_auth_settings()


def test_http_config_validates_entra_specific_settings(http_config):
    document = json.loads(http_config.read_text())
    document["oidc"]["provider"] = "entra"
    document["oidc"]["interactive"]["tenant_id"] = "tenant-id"
    http_config.write_text(json.dumps(document))

    settings = http.get_auth_settings()

    assert settings.provider == "entra"
    assert settings.interactive == HTTPInteractiveAuthConfig(
        client_id="interactive-client",
        client_secret="interactive-secret",
        tenant_id="tenant-id",
    )


def test_http_config_requires_entra_tenant(http_config):
    document = json.loads(http_config.read_text())
    document["oidc"]["provider"] = "entra"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="oidc.interactive.tenant_id.*Entra"):
        http.get_auth_settings()


def test_http_config_allows_separate_entra_client_ids(http_config):
    document = json.loads(http_config.read_text())
    document["oidc"]["provider"] = "entra"
    document["oidc"]["interactive"].update(
        {"client_id": "interactive-client", "tenant_id": "tenant-id"}
    )
    document["token_exchange"]["client_id"] = "middle-tier-client"
    http_config.write_text(json.dumps(document))

    assert http.get_auth_settings().interactive.client_id == "interactive-client"
    assert http.get_token_exchange_settings().client_id == "middle-tier-client"


def test_http_config_rejects_invalid_provider(http_config):
    document = json.loads(http_config.read_text())
    document["oidc"]["provider"] = "unknown"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError):
        http.get_auth_settings()


def test_http_config_example_is_valid(monkeypatch):
    example_path = Path(__file__).parents[1] / ".dataiku" / "http-config.json.example"
    monkeypatch.setattr(http, "_settings_path", example_path)

    assert http.get_server_settings() == HTTPServerConfig(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        public_url="https://mcp.example",
    )
    assert http.get_auth_settings() == HTTPAuthConfig(
        provider="oidc",
        issuer="https://example.okta.com/oauth2/mcp",
        jwks_uri="https://example.okta.com/oauth2/mcp/v1/keys",
        audience="dataiku-mcp",
        scope="mcp.access",
        interactive=HTTPInteractiveAuthConfig(
            client_id="dataiku-mcp",
            client_secret="replace-with-secret",
        ),
    )
    assert http.get_token_exchange_settings() == HTTPTokenExchangeConfig(
        url="https://example.okta.com/oauth2/dss/v1/token",
        client_id="dataiku-mcp-exchange",
        client_secret="replace-with-exchange-secret",
    )
    instances, selections = http.get_instances_and_selections()
    assert isinstance(http._load_config(), HTTPConfig)
    assert set(instances) == {"prod"}
    assert instances["prod"].url == "https://dss.example"
    assert instances["prod"].jwt_audience == "dss-prod"
    assert instances["prod"].jwt_scope == "dss.api"
    assert selections == {}


def test_http_user_can_select_any_catalog_instance(http_config):
    identity = request.bind_http_identity("https://idp.example", "alice")
    try:
        assert set(request.get_instances()) == {"sandbox", "prod"}
        pinned = request.pin_current_instance()
        try:
            with pytest.raises(ValueError, match="No active Dataiku instance"):
                request.get_pinned_instance()
        finally:
            request.reset_pinned_instance(pinned)

        request.set_current_instance("prod")
        pinned = request.pin_current_instance()
        try:
            assert request.get_pinned_instance().name == "prod"
        finally:
            request.reset_pinned_instance(pinned)
    finally:
        request.reset_http_identity(identity)

    document = json.loads(http_config.read_text())
    assert document["user_selections"] == {"https://idp.example": {"alice": "prod"}}


def test_direct_bearer_config_remains_minimal_when_selection_is_saved(http_config):
    document = json.loads(http_config.read_text())
    document["server"].pop("public_url")
    document["oidc"].pop("interactive")
    http_config.write_text(json.dumps(document))

    identity = request.bind_http_identity("https://idp.example", "alice")
    try:
        request.set_current_instance("prod")
    finally:
        request.reset_http_identity(identity)

    saved = json.loads(http_config.read_text())
    assert "public_url" not in saved["server"]
    assert "interactive" not in saved["oidc"]


def test_stale_http_selection_can_be_replaced(http_config):
    document = json.loads(http_config.read_text())
    document["dss_instances"].pop("prod")
    document["user_selections"] = {
        "https://idp.example": {"alice": "prod", "bob": "sandbox"}
    }
    http_config.write_text(json.dumps(document))

    identity = request.bind_http_identity("https://idp.example", "alice")
    try:
        assert set(request.get_instances()) == {"sandbox"}
        pinned = request.pin_current_instance()
        try:
            with pytest.raises(ValueError, match="No active Dataiku instance"):
                request.get_pinned_instance()
        finally:
            request.reset_pinned_instance(pinned)

        request.set_current_instance("sandbox")
    finally:
        request.reset_http_identity(identity)

    document = json.loads(http_config.read_text())
    assert document["user_selections"] == {
        "https://idp.example": {"alice": "sandbox", "bob": "sandbox"}
    }


def test_http_settings_are_read_from_the_settings_file(http_config):
    assert http.get_server_settings() == HTTPServerConfig(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        public_url="https://mcp.example",
    )
    assert http.get_auth_settings().issuer == "https://idp.example"


@pytest.mark.parametrize(
    ("provider", "expected_data"),
    [
        (
            "oidc",
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": "mcp-token",
                "subject_token_type": ("urn:ietf:params:oauth:token-type:access_token"),
                "audience": "dss-prod",
                "scope": "dss.api",
            },
        ),
        (
            "entra",
            {
                "client_id": "client",
                "client_secret": "secret",
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": "mcp-token",
                "scope": "dss.api",
                "requested_token_use": "on_behalf_of",
            },
        ),
    ],
)
def test_token_exchange_uses_provider_protocol(monkeypatch, provider, expected_data):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "dss-token"}

    monkeypatch.setattr(
        http,
        "get_auth_settings",
        lambda: HTTPAuthConfig(
            provider=provider,
            issuer="https://idp.example",
            jwks_uri="https://idp.example/jwks",
            audience="dataiku-mcp",
            scope="mcp.access",
        ),
    )
    monkeypatch.setattr(
        http,
        "get_token_exchange_settings",
        lambda: HTTPTokenExchangeConfig(
            url="https://idp.example/token",
            client_id="client",
            client_secret="secret",
        ),
    )
    monkeypatch.setattr(
        request,
        "get_pinned_instance",
        lambda: DSSInstance(
            "prod",
            "https://prod.example",
            "",
            False,
            "http",
            jwt_audience="dss-prod",
            jwt_scope="dss.api",
        ),
    )
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda url, **kwargs: captured.update(url=url, **kwargs) or Response(),
    )

    assert asyncio.run(auth.exchange_http_token("mcp-token")) == "dss-token"
    assert captured == {
        "url": "https://idp.example/token",
        "data": expected_data,
        "auth": ("client", "secret") if provider == "oidc" else None,
        "timeout": 10,
    }


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("request", "DSS token exchange failed"),
        ("json", "DSS token exchange returned an invalid response"),
        ("missing", "DSS token exchange returned no access token"),
    ],
)
def test_token_exchange_reports_sanitized_failures(monkeypatch, failure, message):
    class Response:
        def raise_for_status(self):
            if failure == "request":
                raise auth.requests.RequestException("sensitive response")

        def json(self):
            if failure == "json":
                raise ValueError("sensitive response")
            return {}

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
        "get_token_exchange_settings",
        lambda: HTTPTokenExchangeConfig(
            url="https://idp.example/token",
            client_id="client",
            client_secret="secret",
        ),
    )
    monkeypatch.setattr(
        request,
        "get_pinned_instance",
        lambda: DSSInstance(
            "prod",
            "https://prod.example",
            "",
            False,
            "http",
            jwt_audience="dss-prod",
            jwt_scope="dss.api",
        ),
    )
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: Response())

    with pytest.raises(PermissionError, match=message) as exc_info:
        asyncio.run(auth.exchange_http_token("mcp-token"))

    assert "sensitive response" not in str(exc_info.value)
