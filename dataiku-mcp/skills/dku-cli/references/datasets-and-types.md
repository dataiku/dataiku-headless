# Reference: Datasets, Schema & Partitioning

Durable payload shapes for dataset definitions and schema/partitioning. Exact CLI flags via `--help`.
`dku dataset create` exposes only `--type`/`--connection` as typed flags; everything else goes through
`--definition @file.json`. Keep the JSON minimal — DSS auto-fills defaults; pass only keys you intend
to override. Plugin/recipe parameter types: `plugin-params.md`.

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

**Upload gotcha:** `dku dataset upload` resolves a local-FS path and fails for `UploadedFiles` backed by
S3/Azure/GCS — use the UI Upload tile or `folder upload` + `folder create-dataset`.

**Uploaded-dataset typing:** `autodetect_settings()` leaves a column `string` unless the values match a
recognized pattern — python `str(datetime)` output (`2025-01-01 00:00:00+00:00`) stays string; ISO-8601-Z
(`2025-01-01T00:00:00.000Z`) detects as date. Force the intended types after autodetect with `set_schema`
(copying the source dataset's schema round-trips cleanly). A string time column makes TS-forecasting task
creation fail with an opaque NPE (`Cannot read field "per_feature" ... getPreprocessingParams() is null`)
— nothing in the error points at the column type.

## Schema

Column storage types: `string`, `tinyint`/`smallint`/`int` (32-bit)/`bigint` (64-bit), `float` (32-bit)/`double` (64-bit),
`boolean`, `date` (timezone-aware timestamp), `dateonly`, `datetimenotz`, `geopoint`, `geometry`,
`array` (→list), `object` (→dict), `map`. Schema shape:

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
