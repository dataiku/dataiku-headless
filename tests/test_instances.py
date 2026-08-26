"""Unit tests for the instance tools' DSS version reporting.

The active instance's DSS version must reach the agent before it plans a build,
but `/instance-info` is permission-gated, so a credential that cannot read it
must still get a successful instance read.
"""

import asyncio
import json

from dataiku_mcp import config
from dataiku_mcp.tools import instances

from tests.utils.fakes import FakeContext

API_KEY = "super-secret-key"


class _FakeInstanceInfo:
    def __init__(self, raw: dict):
        self.raw = raw


class _FakeClient:
    def __init__(self, raw: dict | None = None, error: Exception | None = None):
        self.raw = raw
        self.error = error
        self.info_calls = 0

    def get_instance_info(self) -> _FakeInstanceInfo:
        self.info_calls += 1
        if self.error is not None:
            raise self.error
        return _FakeInstanceInfo(self.raw)


def _instance(name: str) -> config.DSSInstance:
    return config.DSSInstance(
        name, f"https://{name}.example", API_KEY, False, "config", f"{name} desc"
    )


def _install(monkeypatch, instance_names: list[str], client: _FakeClient, active: str):
    configured = {name: _instance(name) for name in instance_names}
    monkeypatch.setattr(config, "get_instances", lambda: configured)
    monkeypatch.setattr(config, "_current_instance", configured[active])
    monkeypatch.setattr(instances, "get_dss_client", lambda: client)


def _current(monkeypatch, client: _FakeClient) -> dict:
    _install(monkeypatch, ["primary"], client, "primary")
    return json.loads(asyncio.run(instances.get_current_instance(FakeContext())))


def test_get_current_instance_reports_the_dss_version(monkeypatch):
    client = _FakeClient({"dssVersion": "14.7.2", "nodeType": "DESIGN"})
    result = _current(monkeypatch, client)

    assert result["dss_version"] == "14.7.2"
    assert client.info_calls == 1


def test_get_current_instance_succeeds_when_the_version_is_forbidden(monkeypatch):
    result = _current(monkeypatch, _FakeClient(error=PermissionError("403 admin only")))

    assert "dss_version" not in result
    assert result["name"] == "primary"


def test_get_current_instance_succeeds_when_the_version_key_is_absent(monkeypatch):
    result = _current(monkeypatch, _FakeClient({"nodeType": "DESIGN"}))

    assert "dss_version" not in result


def test_get_current_instance_never_returns_the_api_key(monkeypatch):
    client = _FakeClient({"dssVersion": "14.7.2"})
    _install(monkeypatch, ["primary"], client, "primary")

    raw = asyncio.run(instances.get_current_instance(FakeContext()))

    assert API_KEY not in raw
    assert "api_key" not in json.loads(raw)


def test_list_instances_versions_only_the_active_instance(monkeypatch):
    client = _FakeClient({"dssVersion": "15.0.0"})
    _install(monkeypatch, ["primary", "secondary"], client, "secondary")

    raw = asyncio.run(instances.list_instances(FakeContext()))
    table = json.loads(raw)
    rows = [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]
    versions = {row["name"]: row["dss_version"] for row in rows}

    assert versions == {"primary": "", "secondary": "15.0.0"}
    assert client.info_calls == 1
    assert API_KEY not in raw
