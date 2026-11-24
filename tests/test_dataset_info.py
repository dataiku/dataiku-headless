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

"""Opt-in configured dataset locations and dataset-specific response behavior."""

import asyncio
import copy
import json
import threading
from types import SimpleNamespace

import pytest
from dataikuapi.dss.project import DSSProject
from fastmcp import Client

from dataiku_mcp import mcp
from dataiku_mcp.config import stdio, request
from dataiku_mcp.tools import datasets
from dataiku_mcp.tools.datasets import _dataset_location
from tests.test_instance_policy import _instance

SECRET = "DO_NOT_RETURN_LOCATION_SECRET"


@pytest.fixture
def backend(monkeypatch):
    owner = threading.get_ident()
    settings = {
        "type": "Filesystem",
        "managed": False,
        "params": {"connection": "storage", "path": "/reference"},
    }
    calls = []

    def perform(method, path, **kwargs):
        assert threading.get_ident() != owner, "SDK work on event loop"
        assert method == "GET"
        calls.append(path)
        if path.endswith("/schema"):
            return {
                "columns": [
                    {
                        "name": "value",
                        "type": "string",
                        "meaning": "Text",
                        "comment": "Value",
                    }
                ]
            }
        assert path == "/projects/PROJECT/datasets/dataset"
        return copy.deepcopy(settings)

    fake_client = SimpleNamespace(_perform_json=perform)
    fake_client.get_project = lambda key: DSSProject(fake_client, key)

    def client():
        assert threading.get_ident() != owner
        assert request.get_pinned_instance().name == "design"
        return fake_client

    monkeypatch.setattr(datasets, "get_dss_client", client)
    monkeypatch.setattr(stdio, "_current_instance", _instance("design"))
    return settings, calls


async def _call(**options):
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_dataset_info",
            {"project_key": "PROJECT", "dataset_name": "dataset", **options},
        )
        return json.loads(result.content[0].text)


def call():
    return asyncio.run(_call(include_location=True))


@pytest.mark.parametrize("options", [{}, {"include_location": False}])
def test_location_is_opt_in_and_does_not_get_processed(backend, monkeypatch, options):
    def unexpected(settings):
        pytest.fail("Location processing should be skipped")

    monkeypatch.setattr(datasets, "_dataset_location", unexpected)
    result = asyncio.run(_call(**options))
    assert result == {
        "type": "Filesystem",
        "connection": "storage",
        "managed": False,
        "columns": {
            "columns": ["name", "type", "meaning", "comment"],
            "rows": [["value", "string", "Text", "Value"]],
        },
    }


def test_info_preserves_existing_fields_and_adds_configured_location(backend):
    result = call()
    assert result == {
        "type": "Filesystem",
        "connection": "storage",
        "managed": False,
        "location": {
            "parameters": {"connection": "storage", "path": "/reference"},
            "resolution": "configured",
        },
        "columns": {
            "columns": ["name", "type", "meaning", "comment"],
            "rows": [["value", "string", "Text", "Value"]],
        },
    }
    assert backend[1] == [
        "/projects/PROJECT/datasets/dataset/schema",
        "/projects/PROJECT/datasets/dataset",
    ]


@pytest.mark.parametrize(
    "kind,params",
    [
        (
            "SQL",
            {
                "connection": "sql",
                "schema": "${env}",
                "table": "${projectKey}_output",
                "mode": "table",
                "customPreWriteStatements": "DELETE FROM ${target_schema}.orders",
            },
        ),
        ("Filesystem", {"connection": "fs", "path": "/${projectKey}/data"}),
    ],
)
def test_configured_storage_expressions_are_preserved(backend, kind, params):
    settings, _ = backend
    settings.update(type=kind, managed=True, params=params)
    result = call()
    assert result["type"] == kind
    assert result["managed"] is True
    assert result["location"] == {
        "parameters": params,
        "resolution": "configured",
    }


@pytest.mark.parametrize(
    "connection_fields",
    [
        {"uploadConnection": "uploads"},
        {
            "uploadedConfig": {
                "connection": "uploads",
                "bucket": "bucket",
                "path": "/${projectKey}/uploads",
            }
        },
    ],
)
def test_uploaded_files_expose_backing_location_and_connection(
    backend, connection_fields
):
    settings, _ = backend
    params = {
        "uploadBoxId": "box",
        "uploadFSProviderType": "S3",
        "files": ["source.csv"],
        **connection_fields,
    }
    settings.update(type="UploadedFiles", params=params)
    result = call()
    assert result["connection"] == "uploads"
    assert result["location"]["parameters"] == params


def test_partitioning_is_included_only_when_configured():
    partitioning = {
        "filePathPattern": "/%Y/%M/%D/.*",
        "dimensions": [{"name": "date", "type": "time"}],
    }
    assert _dataset_location({"partitioning": partitioning}) == {
        "parameters": {},
        "resolution": "configured",
        "partitioning": partitioning,
    }
    assert "partitioning" not in _dataset_location({"partitioning": {"dimensions": []}})


def test_query_does_not_report_a_stale_table_as_its_source(backend):
    settings, _ = backend
    settings.update(
        type="Snowflake",
        params={
            "connection": "sql",
            "mode": "query",
            "table": "old_table",
            "query": "SELECT * FROM ${source_schema}.orders",
        },
    )
    result = call()["location"]
    assert result == {
        "parameters": {
            "connection": "sql",
            "mode": "query",
            "query": "SELECT * FROM ${source_schema}.orders",
        },
        "resolution": "configured",
        "omitted_parameters": ["table"],
    }
    assert SECRET not in json.dumps(result)


def test_unfamiliar_nested_parameters_are_preserved_and_redacted():
    params = {
        "futureLocation": {
            "namespace": ["${env}", "items"],
            "enabled": True,
            "inheritRoot": None,
            "options": [{"password": SECRET, "region": "region"}],
        },
        "customConfig": {
            "query": "SELECT * FROM ${schema}.orders",
            "code": "print('example')",
        },
        "filesSelectionRules": {"includeRules": [{"expr": "*.csv"}]},
    }
    expected = copy.deepcopy(params)
    expected["futureLocation"]["options"][0]["password"] = "__DATAIKU_REDACTED__"
    assert _dataset_location({"type": "FutureStorage", "params": params}) == {
        "parameters": expected,
        "resolution": "configured",
    }
    assert params["futureLocation"]["options"][0]["password"] == SECRET


def test_dataset_info_uses_pinned_instance_after_selection_changes(
    backend, monkeypatch
):
    original = datasets.get_dss_client

    def switch():
        stdio._current_instance = _instance("automation")
        return original()

    monkeypatch.setattr(datasets, "get_dss_client", switch)
    assert call()["location"]["parameters"]["path"] == "/reference"
