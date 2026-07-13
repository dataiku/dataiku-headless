# Connection Type Filters

Read this reference only when `list_connections` returns restricted name-only discovery or when filtering by connection family will make discovery more precise.

## Choosing a Filter

Use `connection_type` when the required connection type is already known. Use `connection_category` when the broader family is known but the exact type is not. Never provide both in the same call.

```text
list_connections(connection_type="Snowflake")
list_connections(connection_type="Filesystem")
list_connections(connection_type="EC2")
list_connections(connection_category="sql_dbs")
list_connections(connection_category="llm_providers")
list_connections(connection_category="object_storage")
```

For a broad pass followed by a narrow pass, first filter by `connection_category`, then filter by `connection_type` after identifying the required family.

## Supported Categories and Types

| Category | Types |
| --- | --- |
| `object_storage` | `EC2` (S3), `GCS`, `Azure` (Blob), `HDFS` |
| `local_server` | `Filesystem`, `FTP`, `SSH` |
| `sql_dbs` | `Snowflake`, `BigQuery`, `Redshift`, `Synapse`, `Athena`, `Databricks`, `FabricWarehouse`, `PostgreSQL`, `MySQL`, `SQLServer`, `Oracle`, `Teradata`, `Vertica`, `Greenplum`, `Trino`, `JDBC`, `AlloyDB`, `SAPHANA`, `Netezza`, `Denodo` |
| `nosql_search` | `MongoDB`, `ElasticSearch`, `Cassandra` |
| `llm_providers` | `OpenAI`, `AzureOpenAI`, `AzureLLM`, `Bedrock`, `VertexAILLM`, `DatabricksLLM`, `SnowflakeCortex`, `MistralAI`, `Anthropic`, `Cohere`, `SageMaker-GenericLLM`, `CustomLLM`, `AzureAIFoundry`, `HuggingFaceLocal`, `NVIDIA-NIM`, `StabilityAI` |
| `external_ml_model_providers` | `SageMaker`, `VertexAIModelDeployment`, `DatabricksModelDeployment`, `AzureML` |
| `vector_stores` | `AzureAISearch`, `Pinecone`, `MilvusRemote` |
| `other` | `RemoteMCP`, `iceberg`, `SharePointOnline`, `TreasureData` |
