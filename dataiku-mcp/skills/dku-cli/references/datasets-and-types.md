# Datasets, Schema & Plugin Parameter Types

Durable payload shapes for dataset definitions, schema/partitioning, and plugin/recipe parameter
definitions. Exact CLI flags via `--help`. `dku dataset create` exposes only `--type`/`--connection`
as typed flags; everything else goes through `--definition @file.json`. Keep the JSON minimal — DSS
auto-fills defaults; pass only keys you intend to override.

## Built-in dataset `--type` catalog

Prefer a built-in type over a custom Python connector. Format-level params live under `formatParams`.

| Type | Storage | Notable params |
|---|---|---|
| `Filesystem` | local managed files | `connection`, `path`, `formatType`, `filesSelectionRules.{mode,includeRules[],excludeRules[],explicitFiles[]}` |
| `UploadedFiles` | DSS-managed uploads (or cloud-backed) | `uploadFSProviderType`, `uploadedConfig.{bucket,connection,path}`, `formatParams.{parseHeaderRow,style}` |
| `FilesInFolder` | reads via sibling managed folder | `folderSmartId`, `explicitFiles[]`, `formatType` |
| `S3`/`Azure`/`GCS`/`HDFS` | object/file-store cloud | Filesystem format params + `bucket`(S3/GCS)/`container`(Azure), `metastoreSynchronizationEnabled`, `metastoreDatabaseName`, `metastoreTableName`, `filesSelectionRules`, `variablesExpansionLoopConfig` |
| `Inline` | editable in-UI grid (canonical small lookup table) | `keepTrackOfChanges`, `importSourceType: NONE\|CLIPBOARD\|CSV`, `formatType:"json"`, `featureGroup` |
| `PostgreSQL`/`Snowflake`/`Redshift`/`BigQuery`/`Synapse`/`SQLServer`/`MySQL`/`Oracle` | SQL | `connection`, `table`, `mode:"table"\|"query"`, `query`, `schema`, **`catalog`** (Snowflake/Databricks 3-level namespace), `tableCreationMode`, `writeJDBCBadDataBehavior: NOVERIFY_ERROR\|VERIFY\|DISCARD_ROW`, `normalizeBooleans`, `normalizeDoubles` |
| `JobsDB` | live view of metrics/checks/jobs history | `view: METRICS_HISTORY\|CHECK_HISTORY\|JOBS_HISTORY`, `scope: SINGLE_OBJECT\|PROJECT`, `smartName`, `partition`, `filter` |
| `CustomPython_<plugin-recipe-id>` | plugin connector dataset | `params.customConfig.<plugin>.inlinedConfig.*` |

BigQuery adds `useBigQueryPartitioning`, `bigQueryPartitioningType/Period`, `bigQueryRequirePartitionFilter`.
SQL table names interpolate DSS variables: `"EAD_${TENANT}_${projectKey}"`.

**Secret leak:** plugin-connector dataset definitions with `mode: INLINE` credentials expose the secret
verbatim in `dku --format json dataset get-definition`. Treat plugin-typed definitions as sensitive.

### Format-specific knobs (`formatParams`)

- **CSV** (`formatType:"csv"`): `parseHeaderRow`, `separator`, `quoteChar`, `escapeChar`, `charset`, `style:"excel"|"unix"`, `compress:"gz"`, and strict-read knobs `readAdditionalColumnsBehavior`/`readMissingColumnsBehavior`/`readDataTypeMismatchBehavior`/`fileReadFailureBehavior` (set all to `FAIL` for SQL-strict semantics), `skipRowsBeforeHeader`/`AfterHeader`.
- **Parquet** (`"parquet"`): `parquetCompressionMethod` (`snappy`/`gzip`/`zstd`), `parquetFlavor`, `parquetBlockSizeMB`, `parquetLowerCaseIdentifiers`, `readTemporalMode`.
- **Excel** (`"excel"`): `sheets`, `sheetSelectionMode: NAMES\|INDICES\|REGEX`, `parseHeaderRow`, `parseDatesToISO`, `rowOverflowStrategy: NEW_SHEET\|FAIL\|TRUNCATE`.
- **JSON** (e.g. `Inline`): `maxExpansionDepth`, `nestedArraysHandling`, `extractFromSingleElement`, `headerRow`.

### Envelope fields (any type)

`customFields.*`; `flowOptions.{virtualizable, rebuildBehavior: NORMAL\|WRITE_PROTECT\|EXPLICIT_REBUILD, ignoreErrorStatusOnBuild}`; `metrics`/`checks` (see dq); `partitioning.{dimensions[], filePathPattern}`.

### S3 + metastore + glob filter (example)

```json
{"type":"S3","params":{"connection":"s3_lake","bucket":"data-prod","path":"/curated/orders/",
  "metastoreSynchronizationEnabled":true,"metastoreDatabaseName":"analytics","metastoreTableName":"orders",
  "filesSelectionRules":{"mode":"ALL","includeRules":[{"path":"*.parquet"}],"excludeRules":[{"path":"*_tmp.parquet"}]}},
  "formatType":"parquet","formatParams":{"parquetCompressionMethod":"snappy"}}
```

`variablesExpansionLoopConfig` (one row-set per `$VAR` combo, files like `metric_${region}_${year}.csv`):
`{"enabled":true,"mode":"VARIABLE","variables":[{"name":"region","values":["us","eu"]},{"name":"year","values":["2024","2025"]}]}`.

**Upload trap:** `dku dataset upload` resolves a local-FS path and fails for `UploadedFiles` backed by
S3/Azure/GCS — use the UI Upload tile or `folder upload` + `folder create-dataset`.

## Schema

Column storage types: `string`, `int` (32-bit), `bigint` (64-bit), `float` (32-bit), `double` (64-bit),
`boolean`, `date` (ISO string), `array` (→list), `object` (→dict). Schema shape:

```json
{"columns":[{"name":"id","type":"string"},{"name":"ts","type":"date"},{"name":"meta","type":"object"}]}
```

## Partitioning

Dimension spec (in dataset `partitioning` or a connector's `get_partitioning`):

```json
{"dimensions":[{"name":"date","type":"time","params":{"period":"DAY"}},{"name":"region","type":"value"}]}
```

`type:"time"` (`period: DAY|HOUR|MONTH|YEAR`) or `type:"value"` (discrete). Partition IDs concatenate
dimension values (e.g. `2024-01-01|us`). File-based datasets also carry `filePathPattern`.

## Python connector (custom dataset type)

Use only when no built-in type fits (REST APIs, proprietary formats). Folder: `python-connectors/<id>/`
with `connector.json` (descriptor) + `connector.py` (`Connector` subclass).

`connector.json`: `{"meta":{label,description,icon},"readable":bool,"writable":bool,"params":[…],"partitioning":{"supported":bool,"fileBasedPartitioning":bool}}`.

`connector.py` key methods:
- `__init__(self, config, plugin_config)` — read params via `config.get(...)`.
- `get_read_schema(self)` → `{"columns":[…]}` (explicit) or `None` (DSS infers from first rows).
- `generate_rows(self, dataset_schema=None, dataset_partitioning=None, partition_id=None, records_limit=-1)` — **yield** dicts keyed by column name (generators, not lists, to avoid OOM); honor `records_limit`.
- `get_records_count(self)` → int or None.
- Writable: `get_writer(...)` returns a `CustomDatasetWriter` whose `write_row(row)` receives a **tuple in schema order** and `close()` flushes.
- Partitioned: implement `get_partitioning()` + `list_partitions(partitioning)`; branch on `partition_id` in `generate_rows`.

Common: retry on 429 (honor `Retry-After`) / 5xx; cursor/offset/page pagination; cache schema in a
class attr. Test by mocking `requests.Session.get` and asserting the yielded row dicts.

## Plugin / recipe parameter definitions

Every parameter shares: `{name, label, type, mandatory?, description?, defaultValue?, visibilityCondition?}`.
`name` is the stable config key; read in Python via `get_recipe_config()` / `get_plugin_config()` /
`get_webapp_config()`. Below: `type` → JSON-extra fields → Python deserialization.

### Core types

| `type` | Extra fields | Python |
|---|---|---|
| `STRING` / `TEXTAREA` / `PASSWORD` | — | `str` |
| `INT` | `minI`, `maxI` | `int` |
| `DOUBLE` | `minD`, `maxD` | `float` |
| `BOOLEAN` | — | `bool` |
| `DATE` | — | `str` (Zulu) |
| `STRINGS` / `INTS` / `DOUBLES` | `allowDuplicates` (STRINGS) | `list` |
| `SELECT` | `selectChoices:[{value,label}]` OR `getChoicesFromPython:true` | `str` |
| `MULTISELECT` | `selectChoices` | `list[str]` |

### Complex / object types

| `type` | Extra fields | Python |
|---|---|---|
| `MAP` | — | `dict` (unordered) |
| `KEY_VALUE_LIST` | — | `list[dict]` (`[{from,to}]`, ordered) |
| `OBJECT_LIST` | `subParams:[…]` (param defs) | `list[dict]` |
| `DATASET` / `DATASETS` | `canSelectForeign` | `str` / `list[str]` |
| `COLUMN` / `COLUMNS` | `columnRole` (input role), `allowedColumnTypes:[…]` | `str` / `list[str]` |
| `DATASET_COLUMN` / `DATASET_COLUMNS` | `datasetParamName` (a DATASET param) | `str` / `list[str]` |
| `MANAGED_FOLDER` | `canSelectForeign` | `str` |
| `SAVED_MODEL` | — | `str` |

### Special / DSS-object / AI types

| `type` | Extra fields | Notes |
|---|---|---|
| `LLM` | `llmUsagePurpose: GENERIC_COMPLETION\|TEXT_EMBEDDING_EXTRACTION\|IMAGE_EMBEDDING_EXTRACTION\|IMAGE_GENERATION\|IMAGE_INPUT` | → LLM ID |
| `KNOWLEDGE_BANK` | — | RAG; → KB name |
| `CODE_ENV` / `CONNECTIONS` / `PROJECT` / `SCENARIO` | — | → ID/name |
| `API_SERVICE_VERSION` / `ML_TASK` | — | → service-version / ML-task ID |
| `SEPARATOR` | `description` (HTML) | display-only divider |
| `PRESET` | `parameterSetId` | values from a Parameter Set |
| `CREDENTIAL_REQUEST` | `credentialRequestSettings.{type: SINGLE_FIELD\|BASIC\|OAUTH2, authorizationEndpoint, tokenEndpoint, scope}` | per-user secret/OAuth |

### Dynamic params & visibility

- Dynamic SELECT: set `getChoicesFromPython:true` + component-level `paramsPythonSetup:"file.py"`. The
  `resource/<file>.py` (NOT `_resource/`) defines `do(payload, config, plugin_config, inputs)` returning
  `{"choices":[{value,label}]}`. `payload.parameterName` selects which param to populate.
- Cascading: child SELECT adds `triggerParameters:["parent_param"]` (reloads when parent changes);
  `disableAutoReload:true` reloads only on trigger, not on form open.
- `visibilityCondition` is a JS expression over `model.<param>`: e.g.
  `"model.use_custom == true && model.mode == 'advanced'"`, `"model.features.indexOf('x') >= 0"`.
