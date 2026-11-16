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

"""Configured dataset locations across storage families and safe omissions."""

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
        *[
            (
                kind,
                {
                    "connection": "sql",
                    "catalog": "db",
                    "schema": "schema",
                    "table": "${projectKey}_output",
                    "mode": "table",
                },
            )
            for kind in (
                "Snowflake",
                "BigQuery",
                "Databricks",
                "PostgreSQL",
                "Redshift",
                "Synapse",
                "Netezza",
                "MySQL",
                "SQLServer",
                "Oracle",
                "JDBC",
            )
        ],
        ("Filesystem", {"connection": "fs", "path": "/${projectKey}/data"}),
        (
            "S3",
            {
                "connection": "object_store",
                "bucket": "bucket",
                "path": "${env}/${projectKey}/output",
                "metastoreDatabaseName": "database",
                "metastoreTableName": "${projectKey}_output",
                "metastoreSynchronizationEnabled": False,
            },
        ),
        ("GCS", {"connection": "object_store", "bucket": "bucket", "path": "data/"}),
        (
            "Azure",
            {"connection": "object_store", "container": "container", "path": "data/"},
        ),
        (
            "HDFS",
            {"connection": "hdfs", "path": "/data", "hiveTableName": "hive_table"},
        ),
        ("FilesInFolder", {"folderSmartId": "SOURCE.folder"}),
        (
            "SharePointOnline",
            {
                "connection": "documents",
                "site": "site",
                "siteId": "site-id",
                "drive": "drive",
                "driveId": "drive-id",
                "path": "/documents",
            },
        ),
        ("Inline", {"uploadBoxId": "box", "importDatasetSmartName": "SOURCE.input"}),
        (
            "Labels",
            {"labelingTaskId": "task", "labelingTaskType": "IMAGE", "view": "labels"},
        ),
        (
            "JobsDB",
            {
                "scope": "SINGLE_OBJECT",
                "smartName": "SOURCE.input",
                "partition": "NP",
                "view": "METRICS_LAST",
            },
        ),
        (
            "ExperimentsDB",
            {"scope": "PROJECT", "viewType": "RUNS", "experimentIds": ["experiment"]},
        ),
        (
            "Sample_fixture-samples_example",
            {"pluginId": "fixture-samples", "sampleName": "example", "version": "1"},
        ),
    ],
)
def test_storage_families_keep_location_expressions(backend, kind, params):
    settings, _ = backend
    settings.update(
        type=kind,
        managed=True,
        params={
            **params,
            "password": SECRET,
            "customPreWriteStatements": "DELETE FROM ${target_schema}.orders",
        },
    )
    result = call()
    assert result["type"] == kind
    assert result["managed"] is True
    assert result["location"] == {
        "parameters": {
            **params,
            "password": "__DATAIKU_REDACTED__",
            "customPreWriteStatements": "DELETE FROM ${target_schema}.orders",
        },
        "resolution": "configured",
    }
    assert SECRET not in json.dumps(result)


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


def test_file_selection_partitioning_and_variable_dependencies_are_preserved(backend):
    settings, _ = backend
    settings["params"].update(
        filesSelectionRules={
            "mode": "RULES",
            "explicitFiles": ["reference.csv"],
            "includeRules": [
                {
                    "mode": "INCLUDE",
                    "matchingMode": "GLOB",
                    "expr": "*.csv",
                    "password": SECRET,
                }
            ],
            "excludeRules": [],
            "credentials": SECRET,
        },
        variablesExpansionLoopConfig={
            "enabled": True,
            "mode": "ZIP",
            "datasetRef": "SOURCE.mapping",
            "replacements": [{"variableName": "output_root", "column": "root"}],
        },
    )
    settings["partitioning"] = {
        "filePathPattern": "/%Y/%M/%D/.*",
        "dimensions": [
            {
                "name": "date",
                "type": "time",
                "params": {"period": "DAY", "token": SECRET},
            }
        ],
        "secret": SECRET,
    }
    result = call()["location"]
    assert result["parameters"]["filesSelectionRules"] == {
        "mode": "RULES",
        "explicitFiles": ["reference.csv"],
        "includeRules": [
            {
                "mode": "INCLUDE",
                "matchingMode": "GLOB",
                "expr": "*.csv",
                "password": "__DATAIKU_REDACTED__",
            }
        ],
        "excludeRules": [],
        "credentials": "__DATAIKU_REDACTED__",
    }
    assert result["parameters"]["variablesExpansionLoopConfig"] == {
        "enabled": True,
        "mode": "ZIP",
        "datasetRef": "SOURCE.mapping",
        "replacements": [{"variableName": "output_root", "column": "root"}],
    }
    assert result["partitioning"] == {
        "filePathPattern": "/%Y/%M/%D/.*",
        "dimensions": [
            {
                "name": "date",
                "type": "time",
                "params": {"period": "DAY", "token": "__DATAIKU_REDACTED__"},
            }
        ],
        "secret": "__DATAIKU_REDACTED__",
    }
    assert SECRET not in json.dumps(result)


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


@pytest.mark.parametrize(
    "kind,key",
    [
        ("CustomPython_fixture_source", "customConfig"),
        ("fsprovider_fixture_provider", "config"),
    ],
)
def test_plugin_config_is_preserved_with_shared_credential_redaction(
    backend, kind, key
):
    settings, _ = backend
    settings.update(
        type=kind,
        params={
            key: {"collection": "${env}_orders", "inlinedConfig": {"key": SECRET}},
            "path": "/configured",
        },
    )
    result = call()["location"]
    assert result == {
        "parameters": {
            key: {
                "collection": "${env}_orders",
                "inlinedConfig": {"key": "__DATAIKU_REDACTED__"},
            },
            "path": "/configured",
        },
        "resolution": "configured",
    }
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            f"https://user:{SECRET}@example.com/data?token={SECRET}&page=2#section",
            "https://example.com/data?token=__DATAIKU_REDACTED__&page=2#section",
        ),
        (
            "https://example.com/data?page=2#section",
            "https://example.com/data?page=2#section",
        ),
        (f"https://[broken?token={SECRET}", "__DATAIKU_REDACTED__"),
    ],
)
def test_http_source_urls_use_shared_connection_redaction(backend, url, expected):
    settings, _ = backend
    settings.update(
        type="HTTP",
        params={
            "sources": [
                {
                    "url": url,
                    "headers": {"Authorization": SECRET},
                    "body": "request-body",
                }
            ]
        },
    )
    result = call()["location"]
    assert result["parameters"] == {
        "sources": [
            {
                "url": expected,
                "headers": {"Authorization": "__DATAIKU_REDACTED__"},
                "body": "request-body",
            }
        ]
    }
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("scheme", ["abfs", "abfss", "wasb", "wasbs"])
def test_azure_uri_container_authority_is_not_treated_as_a_username(scheme):
    uri = f"{scheme}://container@account.dfs.core.windows.net/${{projectKey}}/data"
    result = _dataset_location({"params": {"path": uri}})
    assert result["parameters"]["path"] == uri


@pytest.mark.parametrize(
    "kind,params",
    [
        ("MongoDB", {"connection": "documents", "collection": "${env}_items"}),
        (
            "ElasticSearch",
            {
                "connection": "search",
                "index": "${env}-items",
                "partitioningIndexPattern": "items-*",
            },
        ),
        (
            "Iceberg",
            {
                "connection": "lake",
                "namespace": "${env}",
                "table": "items",
                "location": "/${env}/items",
            },
        ),
        (
            "DatabricksVolume",
            {
                "connection": "volumes",
                "volume": "catalog.schema.volume",
                "path": "${env}/items",
            },
        ),
        (
            "SharePointOnlineList",
            {
                "connection": "lists",
                "sharePointSite": "site",
                "sharePointList": "items",
                "siteId": "site-id",
                "listId": "list-id",
            },
        ),
        (
            "Cassandra",
            {
                "connection": "wide_columns",
                "table": "${env}_items",
                "deleteBeforeWrite": True,
            },
        ),
        (
            "DynamoDB",
            {
                "connection": "kv",
                "table": "${env}_items",
                "partitioningColumn": "region",
            },
        ),
        (
            "FutureStorage",
            {
                "futureLocation": {
                    "namespace": ["${env}", "items"],
                    "enabled": True,
                    "inheritRoot": None,
                }
            },
        ),
    ],
)
def test_unobserved_storage_types_and_parameters_are_preserved(kind, params):
    assert _dataset_location({"type": kind, "params": params}) == {
        "parameters": params,
        "resolution": "configured",
    }


def test_internal_statistics_source_filters_are_not_lost():
    result = _dataset_location(
        {
            "params": {
                "view": "JOBS",
                "jobs": {"projectKey": "PROJECT", "credentials": SECRET},
                "commits": {},
                "orderByDate": True,
            }
        }
    )
    assert result["parameters"] == {
        "view": "JOBS",
        "jobs": {"projectKey": "PROJECT", "credentials": "__DATAIKU_REDACTED__"},
        "commits": {},
        "orderByDate": True,
    }
    assert SECRET not in json.dumps(result)


def test_dataset_info_uses_pinned_instance_after_selection_changes(
    backend, monkeypatch
):
    original = datasets.get_dss_client

    def switch():
        stdio._current_instance = _instance("automation")
        return original()

    monkeypatch.setattr(datasets, "get_dss_client", switch)
    assert call()["location"]["parameters"]["path"] == "/reference"


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "client_secret",
        "api-key",
        "accessKeyId",
        "privateKey",
        "sasToken",
        "credentials",
        "Authorization",
        "keyBase64Data",
        "keyJsonData",
    ],
)
def test_shared_redaction_applies_to_unfamiliar_nested_parameters(field):
    result = _dataset_location(
        {
            "params": {
                "futureLocation": {
                    "namespace": "${env}",
                    "options": [{field: SECRET, "region": "region"}],
                },
            }
        }
    )
    assert result["parameters"] == {
        "futureLocation": {
            "namespace": "${env}",
            "options": [{field: "__DATAIKU_REDACTED__", "region": "region"}],
        },
    }
    assert "omitted_parameters" not in result
    assert SECRET not in json.dumps(result)


def test_free_form_text_is_included_with_shared_redaction():
    result = _dataset_location(
        {
            "params": {
                "uploadedConfig": {
                    "path": "/${projectKey}/uploads",
                    "customConfig": {"password": SECRET},
                    "partitionsQuery": "SELECT DISTINCT region FROM ${schema}.orders",
                    "customQueryDsl": '{"query": {"match_all": {}}}',
                    "code": "print('example')",
                    "variablesExpansionLoopConfig": {
                        "replacements": [{"values": [{"password": SECRET}]}]
                    },
                }
            }
        }
    )
    config = result["parameters"]["uploadedConfig"]
    assert config["path"] == "/${projectKey}/uploads"
    assert config["partitionsQuery"] == "SELECT DISTINCT region FROM ${schema}.orders"
    assert config["customQueryDsl"] == '{"query": {"match_all": {}}}'
    assert config["code"] == "print('example')"
    assert "omitted_parameters" not in result
    assert SECRET not in json.dumps(result)
