---
name: connections
description: Discover and inspect Dataiku DSS connections through read-only MCP tools. Use when an agent must find exact connection names, inspect connection capabilities, or diagnose connection access/test failures.
---

# Connection Operations

Use Dataiku MCP tools to inspect DSS connections safely before using connection names in datasets, managed folders, recipes, scenarios, or agent-tool payloads.

This skill is intentionally narrow:
- it covers connection-name discovery, per-connection inspection, and cautious testing
- it does **not** cover connection creation, editing, deletion, or ACL synchronization

## Follow This Execution Pattern

1. Call `list_connections` to discover the exact DSS connection names. Never invent a connection name from memory or defaults.
2. Call `get_connection_info` on one or more candidate connections before recommending or using them.
3. Pass `contextual_project_key` to `get_connection_info` when connection usability may depend on project-level variables or permissions.
4. Use `test_connection` only when the user is diagnosing connectivity, permissions, or setup issues, or explicitly asks to validate a connection.
6. When recommending a connection, explain why it fits the task — writeability, managed-dataset/folder support, connection type, and any remaining uncertainty.

## Preferred Tools

- Discover: `list_connections`
- Inspect: `get_connection_info`
- Validate: `test_connection`

## `list_connections` — Type and Category Filters

When the API key has admin rights, `list_connections` returns `name`, `type`, and capability fields (`allow_write`, `allow_managed_datasets`, etc.) for each connection in one call.

When the API key lacks admin rights, it falls back to name-only discovery. In that case, use the filters server-side:
- `connection_type` when you know the exact DSS type you need
- `connection_category` when you know the broader family but not the exact type yet
- never provide both in the same call; choose one filtering mode

```
list_connections(connection_type="Snowflake")
list_connections(connection_type="Filesystem")
list_connections(connection_type="EC2")   # S3-backed
list_connections(connection_category="sql_dbs")
list_connections(connection_category="llm_providers")
list_connections(connection_category="object_storage")
```

If you need a broad pass first and a narrow pass second, do two calls: first by `connection_category`, then by `connection_type` after you know the exact family you want.

**Supported connection categories and types:**

| Category | Types |
|----------|-------|
| `object_storage` | `EC2` (S3), `GCS`, `Azure` (Blob), `HDFS` |
| `local_server` | `Filesystem`, `FTP`, `SSH` |
| `sql_dbs` | `Snowflake`, `BigQuery`, `Redshift`, `Synapse`, `Athena`, `Databricks`, `FabricWarehouse`, `PostgreSQL`, `MySQL`, `SQLServer`, `Oracle`, `Teradata`, `Vertica`, `Greenplum`, `Trino`, `JDBC`, `AlloyDB`, `SAPHANA`, `Netezza`, `Denodo` |
| `nosql_search` | `MongoDB`, `ElasticSearch`, `Cassandra` |
| `llm_providers` | `OpenAI`, `AzureOpenAI`, `AzureLLM`, `Bedrock`, `VertexAILLM`, `DatabricksLLM`, `SnowflakeCortex`, `MistralAI`, `Anthropic`, `Cohere`, `SageMaker-GenericLLM`, `CustomLLM`, `AzureAIFoundry`, `HuggingFaceLocal`, `NVIDIA-NIM`, `StabilityAI` |
| `external_ml_model_providers` | `SageMaker`, `VertexAIModelDeployment`, `DatabricksModelDeployment`, `AzureML` |
| `vector_stores` | `AzureAISearch`, `Pinecone`, `MilvusRemote` |
| `other` | `RemoteMCP`, `iceberg`, `SharePointOnline`, `TreasureData` |

## Safety Rules

- Treat connections as a shared DSS configuration domain even when the task is project-specific.
- Use `list_connections` first because name discovery is available without relying on the admin `/admin/connections/` API.
- Be explicit that `get_connection_info` and especially `test_connection` may still be constrained by per-connection permissions or elevated privileges.
- Do not expose or rely on secret-bearing fields; use the tool outputs as already-redacted inspection summaries.
- Do not run repeated `test_connection` calls unless the user is actively debugging a connection problem.
- Do not choose a connection solely because it is the configured default; discover and inspect the real candidate first.
