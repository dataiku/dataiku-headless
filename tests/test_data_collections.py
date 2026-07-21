"""Data Collection object reads expose a bounded stable identity contract."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import data_collections


class FakeCtx:
    async def info(self, message, **kwargs):
        return None


class FakeCollection:
    def __init__(self, items):
        self.items = items
        self.as_type = None

    def list_objects(self, as_type="objects"):
        self.as_type = as_type
        return self.items


class FakeClient:
    def __init__(self, collection):
        self.collection = collection
        self.requested_id = None

    def get_data_collection(self, collection_id):
        self.requested_id = collection_id
        return self.collection


def run(coro):
    return asyncio.run(coro)


def bind(monkeypatch, items):
    collection = FakeCollection(items)
    client = FakeClient(collection)
    monkeypatch.setattr(data_collections, "get_dss_client", lambda: client)
    return client, collection


def test_returns_only_stable_identity_fields_without_mutating_sdk_payload(monkeypatch):
    items = [
        {
            "type": "DATASET",
            "projectKey": "PROJECT",
            "id": "customers",
            "displayName": "Customers",
            "futureUnstableField": {"secret": "not returned"},
        }
    ]
    original = items[0].copy()
    client, collection = bind(monkeypatch, items)

    result = json.loads(
        run(data_collections.list_data_collection_objects("COLL", FakeCtx()))
    )

    assert client.requested_id == "COLL"
    assert collection.as_type == "dict"
    assert items[0] == original
    assert result == {
        "collection_id": "COLL",
        "objects": {
            "columns": ["type", "project_key", "id"],
            "rows": [["DATASET", "PROJECT", "customers"]],
        },
        "returned_items": 1,
        "total_items": 1,
        "truncated": False,
    }


def test_max_items_bounds_rows_and_reports_total(monkeypatch):
    items = [
        {"type": "DATASET", "projectKey": "P", "id": f"ds_{index}"}
        for index in range(4)
    ]
    bind(monkeypatch, items)

    result = json.loads(
        run(
            data_collections.list_data_collection_objects(
                "COLL", FakeCtx(), max_items=2
            )
        )
    )

    assert result["objects"]["rows"] == [
        ["DATASET", "P", "ds_0"],
        ["DATASET", "P", "ds_1"],
    ]
    assert result["returned_items"] == 2
    assert result["total_items"] == 4
    assert result["truncated"] is True


@pytest.mark.parametrize("max_items", [0, -1, 1001, True])
def test_max_items_rejects_invalid_or_silently_clamped_values(monkeypatch, max_items):
    bind(monkeypatch, [])

    with pytest.raises(ValueError, match="max_items"):
        run(
            data_collections.list_data_collection_objects(
                "COLL", FakeCtx(), max_items=max_items
            )
        )


def test_final_serialized_response_has_a_hard_utf8_ceiling(monkeypatch):
    huge_id = "é" * 600_000
    bind(monkeypatch, [{"type": "DATASET", "projectKey": "P", "id": huge_id}])

    result = json.loads(
        run(
            data_collections.list_data_collection_objects(
                "COLL", FakeCtx(), max_items=1
            )
        )
    )

    assert result["truncated"] is True
    assert result["truncation_reason"] == "max_response_bytes"
    assert result["returned_bytes"] <= 1_000_000
    assert result["total_bytes"] > 1_000_000
