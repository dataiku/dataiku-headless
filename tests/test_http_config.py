"""HTTP instance selection is a preference, not an authorization allow-list."""

import json

import pytest

from dataiku_mcp import config
from dataiku_mcp.tools.utils import auth


@pytest.fixture
def http_config(monkeypatch, tmp_path):
    path = tmp_path / "http-config.json"
    path.write_text(
        json.dumps(
            {
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
    monkeypatch.setenv("DKU_MCP_HTTP_CONFIG_FILE", str(path))
    monkeypatch.setattr(config, "_http_config_file", None)
    return path


def test_http_user_can_select_any_catalog_instance(http_config):
    identity = config.bind_http_identity("https://idp.example", "alice")
    try:
        assert set(config.get_instances()) == {"sandbox", "prod"}
        pinned = config.pin_current_instance()
        try:
            with pytest.raises(config.NoActiveInstanceError):
                config.get_current_instance()
        finally:
            config.reset_pinned_instance(pinned)

        config.set_current_instance("prod")
        pinned = config.pin_current_instance()
        try:
            assert config.get_current_instance().name == "prod"
        finally:
            config.reset_pinned_instance(pinned)
    finally:
        config.reset_http_identity(identity)

    document = json.loads(http_config.read_text())
    assert document["user_defaults"] == {"https://idp.example": {"alice": "prod"}}


def test_token_exchange_uses_selected_instance_audience(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "dss-token"}

    monkeypatch.setattr(
        config,
        "get_http_auth_settings",
        lambda **_: {
            "token_exchange_url": "https://idp.example/token",
            "client_id": "client",
            "client_secret": "secret",
        },
    )
    monkeypatch.setattr(
        auth,
        "get_current_instance_for_tool",
        lambda: config.DSSInstance(
            "prod", "https://prod.example", "", False, "http", jwt_audience="dss-prod", jwt_scope="dss.api"
        ),
    )
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda url, **kwargs: captured.update(url=url, **kwargs) or Response(),
    )

    assert auth.exchange_http_token("mcp-token") == "dss-token"
    assert captured["data"]["audience"] == "dss-prod"
    assert captured["data"]["scope"] == "dss.api"
    assert captured["data"]["subject_token"] == "mcp-token"
