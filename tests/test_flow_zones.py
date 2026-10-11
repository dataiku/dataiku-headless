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

"""Unit tests for flow zone listing."""

import asyncio
import json

from dataiku_mcp.tools import flow

from tests.utils.fakes import FakeContext, FakeDSSClient


class _FakeZoneSettings:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_raw(self) -> dict:
        return self.raw


class _FakeZone:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_settings(self) -> _FakeZoneSettings:
        return _FakeZoneSettings(self.raw)


class _FakeFlow:
    def __init__(self, zones: list[dict]):
        self.zones = zones

    def list_zones(self) -> list[_FakeZone]:
        return [_FakeZone(raw) for raw in self.zones]


class _FakeProject:
    def __init__(self, zones: list[dict]):
        self.flow = _FakeFlow(zones)

    def get_flow(self) -> _FakeFlow:
        return self.flow


def test_list_flow_zones_returns_short_desc_and_color(monkeypatch):
    zones = [
        {
            "id": "default",
            "name": "Inputs",
            "shortDesc": "Rows as received.",
            "color": "#4E79A7",
            "items": [{"objectType": "DATASET", "objectId": "orders"}],
        },
        {"id": "z1", "name": "Outputs", "color": "#59A14F", "items": []},
    ]
    monkeypatch.setattr(
        flow, "get_dss_client", lambda: FakeDSSClient({"PROJ": _FakeProject(zones)})
    )

    result = json.loads(asyncio.run(flow.list_flow_zones("PROJ", FakeContext())))

    table = result["zones"]
    assert table["columns"] == [
        "zone_id",
        "name",
        "short_desc",
        "description",
        "color",
        "items",
    ]
    assert table["rows"] == [
        [
            "default",
            "Inputs",
            "Rows as received.",
            None,
            "#4E79A7",
            [{"object_type": "DATASET", "object_id": "orders"}],
        ],
        ["z1", "Outputs", None, None, "#59A14F", []],
    ]
