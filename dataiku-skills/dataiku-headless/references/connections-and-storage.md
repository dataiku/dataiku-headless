# Connections and storage

Choosing a connection for a Cobuild build, running the uploaded-files bootstrap
path, and knowing which store a thing belongs in. Object identity and read tools are
in `object-model.md`.

## Connections

Connections are shared config providing access to storage, databases, LLM
providers, and remote services. **Available on the instance ≠ usable for a
project** — a connection can exist but lack the storage mode, write access, or
project-level permission a task needs.

- Discover exact names with `list_connections`; never infer a name from a default or
  from memory.
- Inspect candidates with `get_connection_info` before naming one in a prompt; pass
  the contextual project when project variables or permissions affect usability.
- `test_connection` only when actively diagnosing connectivity — not routine
  discovery, and don't repeat it unless debugging.
- Never choose a connection just because it's the configured default; inspect real
  candidates. Never surface secret-bearing fields — use the redacted summaries.

**Families and example types** (for matching a task to a connection kind):

| Family | Example types |
|---|---|
| Object storage | `EC2` (S3), `GCS`, `Azure` (Blob), `HDFS` |
| Local server | `Filesystem`, `FTP`, `SSH` |
| SQL databases | `Snowflake`, `BigQuery`, `Redshift`, `Synapse`, `Athena`, `Databricks`, `PostgreSQL`, `MySQL`, `SQLServer`, `Oracle`, `Teradata`, `Trino`, `JDBC` |
| NoSQL / search | `MongoDB`, `ElasticSearch`, `Cassandra` |
| LLM providers | `OpenAI`, `AzureOpenAI`, `Bedrock`, `VertexAILLM`, `SnowflakeCortex`, `MistralAI`, `Anthropic`, `Cohere`, `AzureAIFoundry`, `HuggingFaceLocal` |
| External ML models | `SageMaker`, `VertexAIModelDeployment`, `DatabricksModelDeployment`, `AzureML` |
| Vector stores | `AzureAISearch`, `Pinecone`, `MilvusRemote` |
| Other | `RemoteMCP`, `iceberg`, `SharePointOnline`, `TreasureData` |

## Where a thing belongs (storage routing)

Pick the store by content type, not convenience:

- **Dataset** — tabular data. Managed/external datasets are built through Cobuild.
- **Managed folder** — arbitrary/binary files: documents, exports, model artifacts,
  job outputs. Not tabular.
- **Project library** — source code and small code-supporting resources (Python/R
  modules, SQL templates, JSON fixtures). Not a general file store, and never a home
  for credentials, tokens, or secrets.

## Uploaded-files bootstrap path

Creating a new Uploaded Files dataset is a direct bootstrap exception. Use it
only to bring user-supplied data into a project — not to replace an existing dataset
and not as a substitute for a managed/external dataset.

1. Pick a file-compatible connection (discover its exact name first; use the
   surrounding flow's storage context when clear, else ask the user).
2. Create with `create_upload_dataset` (a local file path visible to the server;
   tabular files, not arbitrary binaries). Keep overwrite off unless the user
   authorized replacement.
3. Validate with `get_dataset_info` and `get_dataset_profile`. Autodetection leaves
   numeric/date/boolean/categorical values as STRING — inspect samples and profile,
   then route any retype through Cobuild. Never infer a storage type from a column
   name.

The local-file placement into an existing managed folder
(`upload_file_to_managed_folder`) is the parallel bootstrap exception — confirm the
target path first, and don't replace a file at an existing path without explicit
user intent.
