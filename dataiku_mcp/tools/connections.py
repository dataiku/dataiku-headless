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

"""Dataiku connection discovery and inspection tools."""

from typing import Any

from typing import Annotated, Literal

from fastmcp import Context
from pydantic import Field

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)

_CONNECTION_SECRET_REDACTION = "__DATAIKU_REDACTED__"
_SENSITIVE_SUFFIXES = (
    "apikey",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
)
_SENSITIVE_EXACT_KEYS = ("key",)
_SENSITIVE_KEY_FRAGMENTS = (
    "accesskey",
    "appsecret",
    "keybase64data",
    "keyjsondata",
    "passphrase",
    "privatekey",
    "secretkey",
    "tokenkey",
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return (
        normalized in _SENSITIVE_EXACT_KEYS
        or normalized.endswith(_SENSITIVE_SUFFIXES)
        or any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)
    )


def _redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = _CONNECTION_SECRET_REDACTION
            else:
                redacted[key] = _redact_sensitive_data(item)
        return redacted

    if isinstance(value, list):
        return [_redact_sensitive_data(item) for item in value]

    return value


_CONNECTION_TYPES_BY_CATEGORY = {
    "object_storage": ["EC2", "GCS", "Azure", "HDFS"],
    "local_server": ["Filesystem", "FTP", "SSH"],
    "sql_dbs": [
        "Snowflake",
        "BigQuery",
        "Redshift",
        "Synapse",
        "Athena",
        "Databricks",
        "FabricWarehouse",
        "PostgreSQL",
        "MySQL",
        "SQLServer",
        "Oracle",
        "Teradata",
        "Vertica",
        "Greenplum",
        "Trino",
        "JDBC",
        "AlloyDB",
        "SAPHANA",
        "Netezza",
        "Denodo",
    ],
    "nosql_search": ["MongoDB", "ElasticSearch", "Cassandra"],
    "vector_stores": ["AzureAISearch", "Pinecone", "MilvusRemote"],
    "llm_providers": [
        "OpenAI",
        "AzureOpenAI",
        "AzureLLM",
        "Bedrock",
        "VertexAILLM",
        "SnowflakeCortex",
        "MistralAI",
        "Anthropic",
        "Cohere",
        "SageMaker-GenericLLM",
        "CustomLLM",
        "AzureAIFoundry",
        "HuggingFaceLocal",
        "NVIDIA-NIM",
        "StabilityAI",
        "DatabricksLLM",
    ],
    "external_ml_model_providers": [
        "SageMaker",
        "VertexAIModelDeployment",
        "DatabricksModelDeployment",
        "AzureML",
    ],
    "other": ["RemoteMCP", "iceberg", "SharePointOnline", "TreasureData"],
}
_KNOWN_CONNECTION_TYPES = [
    connection_type
    for connection_types in _CONNECTION_TYPES_BY_CATEGORY.values()
    for connection_type in connection_types
]
ConnectionCategory = Literal[
    "all",
    "object_storage",
    "local_server",
    "sql_dbs",
    "nosql_search",
    "vector_stores",
    "llm_providers",
    "external_ml_model_providers",
    "other",
]
_KNOWN_CONNECTION_TYPES_SET = set(_KNOWN_CONNECTION_TYPES)


def _get_connection_category(connection_type: str) -> str | None:
    for category, connection_types in _CONNECTION_TYPES_BY_CATEGORY.items():
        if connection_type in connection_types:
            return category
    return None


@mcp.tool(
    title="List Connections",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_connections(
    ctx: Context,
    connection_type: Annotated[
        str,
        Field(
            description='One Dataiku connection type, e.g. "S3". Mutually exclusive with connection_category.'
        ),
    ] = "all",
    connection_category: ConnectionCategory = "all",
) -> str:
    """Discover which connections exist before choosing where a new asset should live."""
    connection_type = _require_non_empty_string(connection_type, "connection_type")
    if connection_type != "all" and connection_category != "all":
        raise ValueError(
            "Provide only one of 'connection_type' or 'connection_category', not both"
        )

    category_connection_types = (
        _CONNECTION_TYPES_BY_CATEGORY[connection_category]
        if connection_category != "all"
        else _KNOWN_CONNECTION_TYPES
    )

    await ctx.info(
        "Listing Dataiku connections "
        f"(type={connection_type}, category={connection_category})..."
    )

    def _run():
        client = get_dss_client()
        types_to_query = (
            [connection_type] if connection_type != "all" else category_connection_types
        )
        seen: set[str] = set()
        connections = []
        for t in types_to_query:
            for name in client.list_connections_names(t):
                if name not in seen:
                    seen.add(name)
                    connections.append(
                        {
                            "name": name,
                            "type": t,
                            "category": _get_connection_category(t),
                        }
                    )
        return connections

    connections = await run_blocking(_run)

    result: dict = {
        "connections": columnar(connections, ["name", "type", "category"]),
    }
    if (
        connection_type != "all"
        and not connections
        and connection_type not in _KNOWN_CONNECTION_TYPES_SET
    ):
        result["warning"] = (
            f"No connections found for type '{connection_type}', and it is not a known "
            f"Dataiku connection type. Known types: {sorted(_KNOWN_CONNECTION_TYPES_SET)}"
        )

    return compact_json(result)


@mcp.tool(
    title="Get Connection Info",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_connection_info(
    connection_name: str,
    ctx: Context,
    contextual_project_key: Annotated[
        str | None,
        Field(description="Resolves project variables in the connection's settings."),
    ] = None,
) -> str:
    """Read one connection's type and non-secret settings."""
    connection_name = _require_non_empty_string(connection_name, "connection_name")
    if contextual_project_key is not None:
        contextual_project_key = _require_non_empty_string(
            contextual_project_key, "contextual_project_key"
        )

    await ctx.info(f"Loading info for Dataiku connection '{connection_name}'...")

    raw_info = await run_blocking(
        lambda: dict(
            get_dss_client()
            .get_connection(connection_name)
            .get_info(contextual_project_key=contextual_project_key)
        )
    )

    result = {
        "info": _redact_sensitive_data(raw_info),
    }

    # Lever 4: omit top-level fields whose value carries no information
    # (None / "" / [] / {}). Keeps False and 0. Does not recurse into the
    # raw `info` blob — only drops it when the whole object is empty.
    result = omit_empty(result)

    return compact_json(result)


@mcp.tool(
    title="Test Connection",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def test_connection(connection_name: str, ctx: Context) -> str:
    """Check whether a connection can actually be reached right now."""
    connection_name = _require_non_empty_string(connection_name, "connection_name")
    await ctx.info(f"Testing Dataiku connection '{connection_name}'...")

    raw_result = await run_blocking(
        lambda: get_dss_client().get_connection(connection_name).test()
    )

    result = {
        "test": _redact_sensitive_data(raw_result),
    }

    # Lever 4: omit top-level fields whose value carries no information
    # (None / "" / [] / {}). Keeps False and 0. Does not recurse into the
    # raw `test` blob — only drops it when the whole object is empty.
    result = omit_empty(result)

    return compact_json(result)
