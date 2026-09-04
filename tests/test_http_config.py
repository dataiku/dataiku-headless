"""HTTP instance selection is a preference, not an authorization allow-list."""

import asyncio
import json
from pathlib import Path

import pytest

import dataiku_mcp.auth as auth
from dataiku_mcp.config import http, request
from dataiku_mcp.config.models import (
    DSSInstance,
    EntraAuthConfig,
    GenericOIDCAuthConfig,
    GenericOIDCDelegationConfig,
    GenericOIDCInteractiveLoginConfig,
    HTTPConfig,
    HTTPServerConfig,
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
                "auth": {
                    "provider": "generic_oidc",
                    "issuer": "https://idp.example",
                    "jwks_uri": "https://idp.example/jwks",
                    "required_audience": "dataiku-mcp",
                    "required_scope": "mcp.access",
                    "interactive_login": {
                        "client_id": "interactive-client",
                        "client_secret": "interactive-secret",
                    },
                    "delegation": {
                        "token_endpoint": "https://idp.example/token",
                        "client_id": "exchange-client",
                        "client_secret": "exchange-secret",
                    },
                },
                "dss_instances": {
                    "sandbox": {
                        "url": "https://sandbox.example",
                        "delegated_audience": "dss-sandbox",
                        "delegated_scope": "dss.api",
                    },
                    "prod": {
                        "url": "https://prod.example",
                        "delegated_audience": "dss-prod",
                        "delegated_scope": "dss.api",
                    },
                },
                "user_selections": {},
            }
        )
    )
    http.set_settings_path(path)
    yield path
    http.set_settings_path(None)


def _convert_to_entra(document):
    document["auth"] = {
        "provider": "entra",
        "tenant_id": "tenant-id",
        "client_id": "mcp-client",
        "client_secret": "mcp-secret",
        "required_scope": "mcp.access",
        "interactive_login": True,
    }
    for instance in document["dss_instances"].values():
        instance.pop("delegated_audience")


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

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        http.get_server_settings()


def test_http_config_rejects_obsolete_user_defaults_key(http_config):
    document = json.loads(http_config.read_text())
    document["user_defaults"] = document.pop("user_selections")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="user_defaults"):
        http.get_server_settings()


def test_http_config_validates_the_complete_document(http_config):
    document = json.loads(http_config.read_text())
    document.pop("auth")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="Field required"):
        http.get_server_settings()


def test_http_config_rejects_previous_authentication_sections(http_config):
    document = json.loads(http_config.read_text())
    document["oidc"] = document.pop("auth")
    document["delegation"] = document["oidc"].pop("delegation")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="auth"):
        http.get_server_settings()


@pytest.mark.parametrize(
    "public_url",
    ["https://mcp.example/", "mcp.example", "/mcp", "ftp://mcp.example"],
)
def test_direct_bearer_config_preserves_public_url(http_config, public_url):
    document = json.loads(http_config.read_text())
    document["server"]["public_url"] = public_url
    document["auth"].pop("interactive_login")
    http_config.write_text(json.dumps(document))

    assert http.get_server_settings().public_url == public_url


def test_http_config_allows_direct_bearer_only(http_config):
    document = json.loads(http_config.read_text())
    document["server"].pop("public_url")
    document["auth"].pop("interactive_login")
    http_config.write_text(json.dumps(document))

    assert http.get_server_settings().public_url == ""
    assert http.get_auth_settings().interactive_login is None


def test_http_config_requires_public_url_for_interactive_login(http_config):
    document = json.loads(http_config.read_text())
    document["server"].pop("public_url")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="server.public_url is required"):
        http.get_auth_settings()


def test_http_config_rejects_entra_tenant_for_generic_oidc(http_config):
    document = json.loads(http_config.read_text())
    document["auth"]["interactive_login"]["tenant_id"] = "tenant-id"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="tenant_id"):
        http.get_auth_settings()


def test_http_config_validates_entra_specific_settings(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    http_config.write_text(json.dumps(document))

    settings = http.get_auth_settings()

    assert settings.provider == "entra"
    assert settings.interactive_login is True
    assert settings.issuer == "https://login.microsoftonline.com/tenant-id/v2.0"
    assert settings.jwks_uri == (
        "https://login.microsoftonline.com/tenant-id/discovery/v2.0/keys"
    )
    assert settings.required_audience == "mcp-client"
    assert settings.token_endpoint == (
        "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/token"
    )


def test_http_config_requires_entra_tenant(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    document["auth"].pop("tenant_id")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="tenant_id"):
        http.get_auth_settings()


def test_http_config_rejects_entra_audience(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    document["auth"]["required_audience"] = "dataiku-mcp"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="required_audience"):
        http.get_auth_settings()


def test_http_config_rejects_entra_dss_audience(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    document["auth"]["interactive_login"] = False
    document["dss_instances"]["prod"]["delegated_audience"] = "unused"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="delegated_audience must be omitted"):
        http.get_auth_settings()


def test_http_config_requires_oidc_audience(http_config):
    document = json.loads(http_config.read_text())
    document["auth"].pop("required_audience")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="required_audience"):
        http.get_auth_settings()


def test_http_config_requires_generic_oidc_dss_audience(http_config):
    document = json.loads(http_config.read_text())
    document["dss_instances"]["prod"].pop("delegated_audience")
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="delegated_audience is required"):
        http.get_auth_settings()


def test_http_config_requires_boolean_entra_interactive_login(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    document["auth"]["interactive_login"] = {"enabled": True}
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="valid boolean"):
        http.get_auth_settings()


def test_http_config_rejects_empty_generic_oidc_interactive_login(http_config):
    document = json.loads(http_config.read_text())
    document["auth"]["interactive_login"] = {}
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="Field required"):
        http.get_auth_settings()


def test_http_config_allows_entra_direct_bearer_mode(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    document["auth"].pop("interactive_login")
    http_config.write_text(json.dumps(document))

    settings = http.get_auth_settings()

    assert settings.interactive_login is False


@pytest.mark.parametrize("missing", ["client_id", "client_secret"])
def test_http_config_rejects_partial_oidc_interactive_client(http_config, missing):
    document = json.loads(http_config.read_text())
    document["auth"]["interactive_login"].pop(missing)
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="Field required"):
        http.get_auth_settings()


def test_http_config_rejects_invalid_provider(http_config):
    document = json.loads(http_config.read_text())
    document["auth"]["provider"] = "unknown"
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError):
        http.get_auth_settings()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("server", "port"), "8000"),
        (("dss_instances", "prod", "no_check_certificate"), "false"),
    ],
)
def test_http_config_does_not_coerce_types(http_config, path, value):
    document = json.loads(http_config.read_text())
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError):
        http.get_server_settings()


def test_http_config_validation_errors_do_not_expose_secrets(http_config):
    document = json.loads(http_config.read_text())
    secret = "do-not-print-this-secret"
    document["auth"]["delegation"]["client_secret"] = [secret]
    http_config.write_text(json.dumps(document))

    with pytest.raises(ValueError) as exc_info:
        http.get_server_settings()

    assert secret not in str(exc_info.value)


def test_generic_oidc_http_config_example_is_valid(monkeypatch):
    example_path = (
        Path(__file__).parents[1] / ".dataiku" / "http-config.json.generic_oidc-example"
    )
    monkeypatch.setattr(http, "_settings_path", example_path)

    assert http.get_server_settings() == HTTPServerConfig(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        public_url="https://mcp.example",
    )
    assert http.get_auth_settings() == GenericOIDCAuthConfig(
        provider="generic_oidc",
        issuer="https://example.okta.com/oauth2/mcp",
        jwks_uri="https://example.okta.com/oauth2/mcp/v1/keys",
        required_audience="dataiku-mcp",
        required_scope="mcp.access",
        interactive_login=GenericOIDCInteractiveLoginConfig(
            client_id="dataiku-mcp",
            client_secret="replace-with-secret",
        ),
        delegation=GenericOIDCDelegationConfig(
            token_endpoint="https://example.okta.com/oauth2/dss/v1/token",
            client_id="dataiku-mcp-exchange",
            client_secret="replace-with-exchange-secret",
        ),
    )
    instances, selections = http.get_instances_and_selections()
    assert isinstance(http._load_config(), HTTPConfig)
    assert set(instances) == {"prod"}
    assert instances["prod"].url == "https://dss.example"
    assert instances["prod"].delegated_audience == "dss-prod"
    assert instances["prod"].delegated_scope == "dss.api"
    assert selections == {}


def test_entra_http_config_example_is_valid(monkeypatch):
    example_path = (
        Path(__file__).parents[1] / ".dataiku" / "http-config.json.entra-example"
    )
    monkeypatch.setattr(http, "_settings_path", example_path)

    settings = http.get_auth_settings()
    assert settings == EntraAuthConfig(
        provider="entra",
        tenant_id="replace-with-tenant-id",
        client_id="replace-with-mcp-app-client-id",
        client_secret="replace-with-secret",
        required_scope="mcp.access",
        interactive_login=True,
    )
    assert settings.issuer == (
        "https://login.microsoftonline.com/replace-with-tenant-id/v2.0"
    )
    instances, selections = http.get_instances_and_selections()
    assert instances["prod"].delegated_audience == ""
    assert instances["prod"].delegated_scope == (
        "api://replace-with-dss-app-id/dss.access"
    )
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


@pytest.mark.parametrize(
    ("issuer", "subject", "field_name"),
    [
        ("", "alice", "issuer"),
        (None, "alice", "issuer"),
        ("https://idp.example", "", "subject"),
        ("https://idp.example", None, "subject"),
    ],
)
def test_http_user_selection_rejects_invalid_identity_without_saving(
    http_config,
    issuer,
    subject,
    field_name,
):
    original = http_config.read_text()

    with pytest.raises(ValueError, match=f"non-empty {field_name}"):
        http.set_user_selection(issuer, subject, "prod")

    assert http_config.read_text() == original


def test_direct_bearer_config_remains_minimal_when_selection_is_saved(http_config):
    document = json.loads(http_config.read_text())
    document["server"].pop("public_url")
    document["auth"].pop("interactive_login")
    http_config.write_text(json.dumps(document))

    identity = request.bind_http_identity("https://idp.example", "alice")
    try:
        request.set_current_instance("prod")
    finally:
        request.reset_http_identity(identity)

    saved = json.loads(http_config.read_text())
    assert "public_url" not in saved["server"]
    assert "interactive_login" not in saved["auth"]


def test_entra_config_remains_minimal_when_selection_is_saved(http_config):
    document = json.loads(http_config.read_text())
    _convert_to_entra(document)
    http_config.write_text(json.dumps(document))

    identity = request.bind_http_identity("https://idp.example", "alice")
    try:
        request.set_current_instance("prod")
    finally:
        request.reset_http_identity(identity)

    saved = json.loads(http_config.read_text())
    assert "required_audience" not in saved["auth"]
    assert saved["auth"]["interactive_login"] is True
    assert "issuer" not in saved["auth"]
    assert "jwks_uri" not in saved["auth"]
    assert "token_endpoint" not in saved["auth"]
    assert "delegated_audience" not in saved["dss_instances"]["prod"]


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
            "generic_oidc",
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
        lambda: (
            EntraAuthConfig(
                provider="entra",
                tenant_id="tenant-id",
                client_id="client",
                client_secret="secret",
                required_scope="mcp.access",
            )
            if provider == "entra"
            else GenericOIDCAuthConfig(
                provider="generic_oidc",
                issuer="https://idp.example",
                jwks_uri="https://idp.example/jwks",
                required_audience="dataiku-mcp",
                required_scope="mcp.access",
                delegation=GenericOIDCDelegationConfig(
                    token_endpoint="https://idp.example/token",
                    client_id="client",
                    client_secret="secret",
                ),
            )
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
            delegated_audience="dss-prod",
            delegated_scope="dss.api",
        ),
    )
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda url, **kwargs: captured.update(url=url, **kwargs) or Response(),
    )

    assert asyncio.run(auth.exchange_http_token("mcp-token")) == "dss-token"
    assert captured == {
        "url": (
            "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/token"
            if provider == "entra"
            else "https://idp.example/token"
        ),
        "data": expected_data,
        "auth": ("client", "secret") if provider == "generic_oidc" else None,
        "timeout": 10,
    }


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("request", "DSS token exchange failed"),
        ("network", "DSS token exchange failed"),
        ("json", "DSS token exchange returned an invalid response"),
        ("non_object", "DSS token exchange returned an invalid response"),
        ("missing", "DSS token exchange returned no access token"),
    ],
)
def test_token_exchange_reports_sanitized_failures(
    monkeypatch, caplog, failure, message
):
    class Response:
        status_code = 400 if failure == "request" else 200
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            if failure == "request":
                raise auth.requests.HTTPError("sensitive response", response=self)

        def json(self):
            if failure == "json":
                raise ValueError("sensitive response")
            if failure == "request":
                return {
                    "error": "invalid_grant",
                    "error_description": (
                        "AADSTS65001 mcp-subject-token exchange-client-secret"
                    ),
                    "correlation_id": "correlation-id",
                    "trace_id": "trace-id",
                }
            if failure == "non_object":
                return []
            return {}

    monkeypatch.setattr(
        http,
        "get_auth_settings",
        lambda: GenericOIDCAuthConfig(
            provider="generic_oidc",
            issuer="https://idp.example",
            jwks_uri="https://idp.example/jwks",
            required_audience="dataiku-mcp",
            required_scope="mcp.access",
            delegation=GenericOIDCDelegationConfig(
                token_endpoint="https://idp.example/token",
                client_id="client",
                client_secret="exchange-client-secret",
            ),
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
            delegated_audience="dss-prod",
            delegated_scope="dss.api",
        ),
    )

    def post(*args, **kwargs):
        if failure == "network":
            raise auth.requests.RequestException("sensitive response")
        return Response()

    monkeypatch.setattr(auth.requests, "post", post)
    caplog.set_level("WARNING", logger="dataiku-mcp")

    with pytest.raises(PermissionError, match=message) as exc_info:
        asyncio.run(auth.exchange_http_token("mcp-subject-token"))

    assert "sensitive response" not in str(exc_info.value)
    assert "mcp-subject-token" not in caplog.text
    assert "exchange-client-secret" not in caplog.text
    assert "sensitive response" not in caplog.text

    if failure == "request":
        assert "status=400 exception=HTTPError error=invalid_grant" in caplog.text
        assert "description=AADSTS65001 <redacted> <redacted>" in caplog.text
        assert "correlation_id=correlation-id trace_id=trace-id" in caplog.text
    elif failure == "network":
        assert "status=None exception=RequestException error=None" in caplog.text
    elif failure == "json":
        assert "returned invalid JSON" in caplog.text
    elif failure == "non_object":
        assert "returned a non-object response" in caplog.text
    else:
        assert "contained no access token" in caplog.text
