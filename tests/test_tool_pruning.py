"""Regression evidence for the deliberately pruned tool families."""

import asyncio
import json

from dataiku_mcp.tools import datasets


class FakeCtx:
    async def info(self, message, **kwargs):
        return None


class FakeSettings:
    def get_raw(self):
        return {"params": {"connection": "warehouse"}}


class FakeDataset:
    def get_schema(self):
        return {
            "columns": [
                {
                    "name": "customer_id",
                    "type": "string",
                    "meaning": "Text",
                    "comment": "Stable source-system identifier",
                }
            ]
        }

    def get_settings(self):
        return FakeSettings()


class FakeProject:
    def get_dataset(self, name):
        return FakeDataset()

    def list_datasets(self):
        return [{"name": "customers", "type": "PostgreSQL"}]


class FakeClient:
    def get_project(self, project_key):
        return FakeProject()


def test_dataset_info_strictly_supersets_removed_column_description_tool(monkeypatch):
    """The replacement retains comments and adds type, meaning, and connection."""
    monkeypatch.setattr(datasets, "get_dss_client", lambda: FakeClient())

    result = json.loads(
        asyncio.run(datasets.get_dataset_info("PROJ", "customers", FakeCtx()))
    )

    assert result == {
        "type": "PostgreSQL",
        "connection": "warehouse",
        "columns": {
            "columns": ["name", "type", "meaning", "comment"],
            "rows": [
                [
                    "customer_id",
                    "string",
                    "Text",
                    "Stable source-system identifier",
                ]
            ],
        },
        "total_columns": 1,
        "returned_columns": 1,
        "truncated": False,
    }


def test_dataset_info_preserves_removed_tools_column_selection(monkeypatch):
    monkeypatch.setattr(datasets, "get_dss_client", lambda: FakeClient())

    result = json.loads(
        asyncio.run(
            datasets.get_dataset_info(
                "PROJ", "customers", FakeCtx(), columns=["customer_id"]
            )
        )
    )

    assert result["columns"]["rows"] == [
        ["customer_id", "string", "Text", "Stable source-system identifier"]
    ]


def test_dataset_info_final_serialized_response_has_a_hard_ceiling(monkeypatch):
    monkeypatch.setattr(datasets, "get_dss_client", lambda: FakeClient())
    monkeypatch.setattr(datasets, "_MAX_DATASET_INFO_RESPONSE_BYTES", 500)
    monkeypatch.setattr(
        FakeDataset,
        "get_schema",
        lambda self: {
            "columns": [
                {
                    "name": "large",
                    "type": "string",
                    "comment": "é" * 1_000,
                }
            ]
        },
    )

    raw = asyncio.run(datasets.get_dataset_info("PROJ", "customers", FakeCtx()))
    result = json.loads(raw)

    assert len(raw.encode("utf-8")) <= 500
    assert result["truncated"] is True
    assert result["truncation_reason"] == "max_response_bytes"
