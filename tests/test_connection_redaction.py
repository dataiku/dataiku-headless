"""Connection reads share redaction policy and stay bound to one DSS client."""

import asyncio
import json

from dataiku_mcp.tools import connections


class FakeCtx:
    async def info(self, message, **kwargs):
        return None


class FakeConnection:
    def __init__(self, payload):
        self.payload = payload

    def get_info(self, **kwargs):
        return self.payload

    def test(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def get_connection(self, name):
        return FakeConnection(self.payload)


def test_connection_info_masks_inline_secret_and_preserves_metadata(monkeypatch):
    payload = {
        "params": [
            {"key": "api_key", "value": "sk-live", "secret": True},
            {"key": "maxTokens", "value": 4000, "secret": False},
        ]
    }
    monkeypatch.setattr(connections, "get_dss_client", lambda: FakeClient(payload))

    result = json.loads(
        asyncio.run(connections.get_connection_info("llm", FakeCtx()))
    )

    assert result["info"]["params"] == [
        {
            "key": "api_key",
            "value": connections.CONNECTION_REDACTION,
            "secret": True,
        },
        {"key": "maxTokens", "value": 4000, "secret": False},
    ]


def test_connection_read_captures_client_before_first_await(monkeypatch):
    calls = []
    clients = [FakeClient({"name": "first"}), FakeClient({"name": "second"})]

    def current_client():
        calls.append(True)
        return clients[min(len(calls) - 1, 1)]

    monkeypatch.setattr(connections, "get_dss_client", current_client)

    result = json.loads(
        asyncio.run(connections.get_connection_info("warehouse", FakeCtx()))
    )

    assert result["info"] == {"name": "first"}
    assert len(calls) == 1


def test_connection_test_uses_the_same_redactor(monkeypatch):
    payload = {"accessToken": "secret", "tokenCount": 17}
    monkeypatch.setattr(connections, "get_dss_client", lambda: FakeClient(payload))

    result = json.loads(asyncio.run(connections.test_connection("api", FakeCtx())))

    assert result["test"] == {
        "accessToken": connections.CONNECTION_REDACTION,
        "tokenCount": 17,
    }
