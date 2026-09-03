# Copyright 2026 Dataiku
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

from dataiku_mcp import config
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


def test_get_current_instance_reports_the_dataiku_version(monkeypatch):
    client = _FakeClient({"dssVersion": "14.7.2", "nodeType": "DESIGN"})
    result = _current(monkeypatch, client)

    assert result["dataiku_version"] == "14.7.2"
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
    assert result["name"] == "primary"
