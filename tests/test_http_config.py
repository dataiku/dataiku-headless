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
    HTTPServerConfig,
    DSSInstance,
)


@pytest.fixture
def http_config(monkeypatch, tmp_path):
    path = tmp_path / "http-config.json"
    path.write_text(
        json.dumps(
            {
                "server": {"host": "127.0.0.1", "port": 8000, "path": "/mcp"},
                "oidc": {
                    "issuer": "https://idp.example",
                    "jwks_uri": "https://idp.example/jwks",
                    "audience": "dataiku-mcp",
                    "scope": "mcp.access",
                },
                "token_exchange": {
                    "url": "https://idp.example/token",
                    "client_id": "client",
                    "client_secret": "secret",
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


def test_http_config_example_is_valid(monkeypatch):
    example_path = Path(__file__).parents[1] / ".dataiku" / "http-config.json.example"
    monkeypatch.setattr(http, "_settings_path", example_path)

    assert http.get_server_settings() == HTTPServerConfig(
        host="127.0.0.1", port=8000, path="/mcp"
    )
    assert http.get_auth_settings() == HTTPAuthConfig(
        issuer="https://idp.example",
        jwks_uri="https://idp.example/jwks",
        audience="dataiku-mcp",
        scope="mcp.access",
        token_exchange_url="https://idp.example/token",
        client_id="dataiku-mcp",
        client_secret="replace-with-secret",
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
        host="127.0.0.1", port=8000, path="/mcp"
    )
    assert http.get_auth_settings().issuer == "https://idp.example"


def test_token_exchange_uses_selected_instance_audience(monkeypatch):
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
            issuer="https://idp.example",
            jwks_uri="https://idp.example/jwks",
            audience="dataiku-mcp",
            scope="mcp.access",
            token_exchange_url="https://idp.example/token",
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
    assert captured["data"]["audience"] == "dss-prod"
    assert captured["data"]["scope"] == "dss.api"
    assert captured["data"]["subject_token"] == "mcp-token"
