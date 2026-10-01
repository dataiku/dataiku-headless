# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the current instance tool's Dataiku version reporting."""

import asyncio
import json
from dataclasses import replace

import pytest

from dataiku_mcp.config import request
from dataiku_mcp.config.models import DSSInstance
from dataiku_mcp.tools import instances

from tests.utils.fakes import FakeContext

API_KEY = "super-secret-key"


class _FakeInstanceInfo:
    def __init__(self, raw: dict):
        self.raw = raw


class _FakeClient:
    def __init__(self, raw: dict):
        self.raw = raw
        self.info_calls = 0

    def get_instance_info(self) -> _FakeInstanceInfo:
        self.info_calls += 1
        return _FakeInstanceInfo(self.raw)


def _instance(name: str) -> DSSInstance:
    return DSSInstance(
        name,
        f"https://{name}.example",
        API_KEY,
        False,
        "config",
        "design",
        f"{name} desc",
    )


def _install(monkeypatch, instance_names: list[str], client: _FakeClient, active: str):
    configured = {name: _instance(name) for name in instance_names}
    monkeypatch.setattr(request, "get_pinned_instance", lambda: configured[active])
    monkeypatch.setattr(instances, "get_dss_client", lambda: client)


def _current(monkeypatch, client: _FakeClient) -> dict:
    _install(monkeypatch, ["primary"], client, "primary")
    return json.loads(asyncio.run(instances.get_current_instance(FakeContext())))


@pytest.mark.parametrize(
    "instance_type", ["design", "automation", "deployer", "agent-management"]
)
def test_instance_tools_report_configured_type(monkeypatch, instance_type):
    configured = replace(_instance("primary"), instance_type=instance_type)
    monkeypatch.setattr(request, "get_instances", lambda: {"primary": configured})
    monkeypatch.setattr(request, "get_pinned_instance", lambda: configured)

    def unexpected_client():
        pytest.fail("Listing and switching must not construct a DSS client")

    monkeypatch.setattr(instances, "get_dss_client", unexpected_client)
    monkeypatch.setattr(
        "dataiku_mcp.config.stdio.set_current_instance", lambda inst: None
    )
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    listing = asyncio.run(instances.list_instances(FakeContext()))
    switching = asyncio.run(instances.switch_instance("primary", FakeContext()))
    table = json.loads(listing)
    assert table["columns"] == ["name", "url", "description", "active", "instance_type"]
    assert table["rows"][0][-1] == instance_type
    assert json.loads(switching)["instance_type"] == instance_type

    # API information is observational; it must not replace the configured type.
    client = _FakeClient({"dssVersion": "14.7.2", "nodeType": "AUTOMATION"})
    monkeypatch.setattr(instances, "get_dss_client", lambda: client)
    current = asyncio.run(instances.get_current_instance(FakeContext()))
    assert json.loads(current)["instance_type"] == instance_type
    assert client.info_calls == 1
    for response in (listing, switching, current):
        assert API_KEY not in response
        assert "api_key" not in response


def test_get_current_instance_reports_the_dataiku_version(monkeypatch):
    client = _FakeClient({"dssVersion": "14.7.2", "nodeType": "DESIGN"})
    result = _current(monkeypatch, client)

    assert result["dataiku_version"] == "14.7.2"
    assert result["connection_status"] == "connected"
    assert client.info_calls == 1


def test_get_current_instance_omits_the_dataiku_version_without_credentials(
    monkeypatch,
):
    _install(monkeypatch, ["primary"], _FakeClient({}), "primary")

    def missing_client():
        raise ValueError("missing API key")

    monkeypatch.setattr(
        instances,
        "get_dss_client",
        missing_client,
    )

    result = json.loads(asyncio.run(instances.get_current_instance(FakeContext())))

    assert "dataiku_version" not in result
    assert result["connection_status"] == "failed"
    assert result["name"] == "primary"
    assert result["instance_type"] == "design"


def test_get_current_instance_reports_failed_connection(monkeypatch):
    client = _FakeClient({})

    def unavailable_instance_info():
        raise ConnectionError("connection failed")

    client.get_instance_info = unavailable_instance_info
    result = _current(monkeypatch, client)

    assert result["connection_status"] == "failed"
    assert "dataiku_version" not in result
    assert client.info_calls == 0
