"""HTTP instance selection is a preference, not an authorization allow-list."""

import asyncio
import json
from pathlib import Path

import pytest

import dataiku_mcp.auth as auth
from dataiku_mcp.config import http, request
from dataiku_mcp.config.models import DSSInstance


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
                "user_defaults": {},
            }
        )
    )
    http.set_settings_path(path)
    yield path
    http.set_settings_path(None)


def test_http_config_uses_canonical_default(monkeypatch):
    default_path = Path.home() / ".dataiku" / "http.json"
    monkeypatch.setattr(http, "_settings_path", None)

    assert http.DEFAULT_SETTINGS_PATH == default_path
    assert http.get_settings_path() == default_path


def test_http_config_example_is_valid(monkeypatch):
    example_path = Path(__file__).parents[1] / ".dataiku" / "http.json.example"
    monkeypatch.setattr(http, "_settings_path", example_path)

    assert http.get_server_settings() == {
        "host": "127.0.0.1",
        "port": 8000,
        "path": "/mcp",
    }
    assert http.get_auth_settings() == {
        "issuer": "https://idp.example",
        "jwks_uri": "https://idp.example/jwks",
        "audience": "dataiku-mcp",
        "scope": "mcp.access",
        "token_exchange_url": "https://idp.example/token",
        "client_id": "dataiku-mcp",
        "client_secret": "replace-with-secret",
    }
    instances, defaults = http.get_instances_and_defaults()
    assert set(instances) == {"prod"}
    assert instances["prod"].url == "https://dss.example"
    assert instances["prod"].jwt_audience == "dss-prod"
    assert instances["prod"].jwt_scope == "dss.api"
    assert defaults == {}


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
    assert document["user_defaults"] == {"https://idp.example": {"alice": "prod"}}


def test_stale_http_default_can_be_replaced(http_config):
    document = json.loads(http_config.read_text())
    document["dss_instances"].pop("prod")
    document["user_defaults"] = {
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
    assert document["user_defaults"] == {
        "https://idp.example": {"alice": "sandbox", "bob": "sandbox"}
    }


def test_http_settings_are_read_from_the_settings_file(http_config):
    assert http.get_server_settings() == {
        "host": "127.0.0.1",
        "port": 8000,
        "path": "/mcp",
    }
    assert http.get_auth_settings()["issuer"] == "https://idp.example"


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
        lambda: {
            "token_exchange_url": "https://idp.example/token",
            "client_id": "client",
            "client_secret": "secret",
        },
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
