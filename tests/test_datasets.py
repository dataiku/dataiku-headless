"""Response bounds on get_dataset_info.

No network: ``get_dss_client`` is replaced by a fake project. The contract under
test is that the whole schema is returned but the response is bounded to a hard
byte ceiling (clipped on a UTF-8 boundary with truncation metadata).
"""

from __future__ import annotations

import asyncio
import json

from dataiku_mcp.tools import datasets


class FakeCtx:
    async def info(self, _message, **_kwargs):
        return None


class FakeSettings:
    def __init__(self, raw):
        self._raw = raw

    def get_raw(self):
        return self._raw


class FakeDataset:
    def __init__(self, schema, settings):
        self._schema = schema
        self._settings = settings

    def get_schema(self):
        return self._schema

    def get_settings(self):
        return FakeSettings(self._settings)


class FakeProject:
    def __init__(self, name, schema, settings, dataset_type):
        self._name = name
        self._dataset = FakeDataset(schema, settings)
        self._type = dataset_type

    def list_datasets(self):
        return [{"name": self._name, "type": self._type}]

    def get_dataset(self, _name):
        return self._dataset


class FakeClient:
    def __init__(self, project):
        self._project = project

    def get_project(self, _key):
        return self._project


def _bind(monkeypatch, project):
    monkeypatch.setattr(datasets, "get_dss_client", lambda: FakeClient(project))


def run(coro):
    return asyncio.run(coro)


def _info(project_key="PROJ", dataset_name="orders"):
    return json.loads(
        run(datasets.get_dataset_info(project_key, dataset_name, FakeCtx()))
    )


def test_dataset_info_returns_full_schema_untruncated(monkeypatch):
    schema = {
        "columns": [
            {"name": "id", "type": "bigint", "meaning": "", "comment": "primary key"},
            {"name": "amount", "type": "double", "meaning": "Amount", "comment": ""},
        ]
    }
    project = FakeProject(
        "orders", schema, {"params": {"connection": "pg"}}, "PostgreSQL"
    )
    _bind(monkeypatch, project)

    res = _info()

    assert res["type"] == "PostgreSQL"
    assert res["connection"] == "pg"
    assert res["columns"]["rows"] == [
        ["id", "bigint", "", "primary key"],
        ["amount", "double", "Amount", ""],
    ]
    assert "truncated" not in res


def test_dataset_info_is_clipped_at_the_byte_ceiling(monkeypatch):
    # A wide schema with long comments; drop the ceiling so it must clip.
    monkeypatch.setattr(datasets, "_MAX_DATASET_INFO_BYTES", 500)
    schema = {
        "columns": [
            {"name": f"col_{i}", "type": "string", "meaning": "", "comment": "x" * 50}
            for i in range(100)
        ]
    }
    project = FakeProject("orders", schema, {"params": {}}, "Filesystem")
    _bind(monkeypatch, project)

    res = _info()

    assert res["truncated"] is True
    assert res["truncation_reason"] == "max_response_bytes"
    assert res["total_bytes"] > 500
    assert "dataset_info_json_truncated" in res
