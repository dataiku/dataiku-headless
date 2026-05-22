# Dataset Connectors Guide

> Complete reference for building custom dataset connectors that integrate external data sources into Dataiku.

---

## Built-in Dataset Types (`dku dataset create --type`)

Before considering a custom Python connector, check whether one of the
built-in DSS dataset types fits. The full enumerated `--type` catalog:

### Filesystem-backed
| Type | Storage | Notable params |
|---|---|---|
| `Filesystem` | Local managed file storage | `connection`, `path`, `formatType`, `formatParams`, `filesSelectionRules.{mode, includeRules[], excludeRules[], explicitFiles[]}` |
| `UploadedFiles` | DSS-managed uploaded files (also S3/Azure/GCS-backed via `uploadFSProviderType`) | `uploadFSProviderType`, `uploadedConfig.{bucket, connection, path, metastore*}`, `formatType`, `formatParams.{parseHeaderRow, style: "excel"\|"unix"}` |
| `FilesInFolder` | Reads file content via a sibling managed folder | `folderSmartId`, `explicitFiles[]`, `formatType: "excel"\|"csv"\|"json"\|"parquet"\|...`, `formatParams` |
| `S3` / `Azure` / `GCS` / `HDFS` | Object/file-store cloud datasets | Same Filesystem-style format params plus `bucket` (S3/GCS) / `container` (Azure), `metastoreSynchronizationEnabled`, `metastoreDatabaseName`, `metastoreTableName`, `filesSelectionRules`, `variablesExpansionLoopConfig` |

### Editable / In-DSS
| Type | Storage | Notable params |
|---|---|---|
| `Inline` | Editable spreadsheet-like dataset (rows hand-typed in the UI grid) | `keepTrackOfChanges`, `enableClipboardApi`, `notReadyIfEmpty`, `importSourceType: NONE\|CLIPBOARD\|CSV`, `formatType: "json"`, `formatParams.{maxExpansionDepth, nestedArraysHandling, headerRow}`, `featureGroup` |

`Inline` is the canonical small-editable lookup-table type. Pairs with the Visual Edit plugin (which uses `keepTrackOfChanges: true` to replay edits as a flow recipe). Set `featureGroup: true` to surface it in the Feature Store UI.

### SQL connections
| Type | Notable params |
|---|---|
| `PostgreSQL` / `Snowflake` / `Redshift` / `BigQuery` / `Synapse` / `SQLServer` / `MySQL` / `Oracle` | `connection`, `table`, `mode: "table"\|"query"`, `query` (when query mode), `schema` (2-level qualifier), **`catalog`** (Snowflake / Databricks Unity Catalog — the 3-level namespace; required when the connection's default DB differs from the working DB; CLI: `--catalog`), `tableCreationMode`, `writeInsertBatchSize`, `writeJDBCBadDataBehavior: NOVERIFY_ERROR\|VERIFY\|DISCARD_ROW`, `noDropOnSchemaMismatch`, `writeDescriptionsAsSQLComment`, `numPartitions`, `sparkJdbcAccess`, `datetimenotzReadMode`, `dateonlyReadMode`, `normalizeBooleans`, `normalizeDoubles` |

BigQuery additionally carries `useBigQueryPartitioning`, `bigQueryPartitioningType`, `bigQueryPartitioningPeriod`, `bigQueryRequirePartitionFilter`, `forbidPreviewFallbackToSelect`, `forbidPartitionsWriteToNonPartitionedTable`. Snowflake/PostgreSQL/Redshift share the same write-knob set — adding `--write-bad-data-behavior` etc. flags on `dataset create` registers them on every JDBC-style connector.

Table names support DSS variable interpolation: `"EAD_${TENANT}_${NODE}_${projectKey}"` is resolved at build time from project + instance variables.

### DSS-internal "live view" types
| Type | Purpose | Notable params |
|---|---|---|
| `JobsDB` | Materialized view of another DSS object's metric/check/job history | `view: METRICS_HISTORY\|CHECK_HISTORY\|JOBS_HISTORY`, `scope: SINGLE_OBJECT\|PROJECT`, `smartName: "<object>"`, `partition`, `filter` |

Use `JobsDB` to expose data-quality results into the flow for downstream analysis (Alteryx-style data-quality dashboards).

### Plugin connector types
| Type | Purpose |
|---|---|
| `CustomPython_<plugin-recipe-id>` | Datasets sourced via a `python-connectors/` plugin component (Airtable, Salesforce, Stripe, …) |

`params.customConfig.<plugin>.inlinedConfig.*` carries connector credentials. **Plugin connector dataset definitions can leak inline secrets through `dku dataset get-definition -o json`** — if the plugin uses `mode: INLINE` for credentials (vs `PRESET` / `FILE`), the secret appears verbatim in the output. Treat plugin-typed dataset definitions as sensitive.

### Format-specific knobs

CSV (`formatType: "csv"`):
- `parseHeaderRow`, `separator`, `quoteChar`, `escapeChar`, `charset`, `style: "excel"\|"unix"`, `dateSerializationFormat`, `arrayMapFormat`
- `readAdditionalColumnsBehavior`, `readMissingColumnsBehavior`, `readDataTypeMismatchBehavior`, `writeDataTypeMismatchBehavior`, `fileReadFailureBehavior`
- `normalizeBooleans`, `normalizeDoubles`, `skipRowsBeforeHeader`, `skipRowsAfterHeader`

Parquet (`formatType: "parquet"`):
- `parquetCompressionMethod` (`snappy` / `gzip` / `zstd` / ...), `parquetFlavor`, `parquetBlockSizeMB`, `parquetLowerCaseIdentifiers`, `readTemporalMode`

Excel (`formatType: "excel"`, common on `FilesInFolder`):
- `sheets` (single sheet name OR comma-separated names — `sheetSelectionMode: NAMES\|INDICES\|REGEX`), `skipRowsBeforeHeader`, `skipRowsAfterHeader`, `parseHeaderRow`, `preserveNumberFormatting`, `parseDatesToISO`, `passwordRequired`, `rowOverflowStrategy: NEW_SHEET\|FAIL\|TRUNCATE`, `cellOverflowStrategy`, `invalidCellStrategy`, `applyColoring`, `sheetsToColumn`

JSON (e.g. used by `Inline`):
- `maxExpansionDepth`, `nestedArraysHandling`, `extractFromSingleElement`, `nestedArraysMaxElements`, `nestedArraysMaxContentSize`, `headerRow`

### Common envelope fields

Every dataset (regardless of type) can carry:
- `customFields.{gdpr_contains_personal_data, ...}` — instance-managed metadata.
- `flowOptions.{virtualizable, rebuildBehavior: NORMAL\|WRITE_PROTECT\|EXPLICIT_REBUILD, crossProjectBuildBehavior, ignoreErrorStatusOnBuild}`.
- `metrics.{probes[], engineConfig}` and `metricsChecks` / `checks` — see `dq` skill.
- `partitioning.{dimensions[], filePathPattern, ...}` — partition spec.

### Pass non-trivial params via `--definition`

`dku dataset create` exposes only `--type` and `--connection` as typed flags;
everything in the tables above is reached through `--definition @file.json`.
Keep the JSON minimal — DSS auto-fills defaults — and pass exactly the keys
you intend to override.

S3 with metastore sync, glob-filtered Parquet inputs:
```json
{
  "type": "S3",
  "params": {
    "connection": "s3_lake",
    "bucket": "data-eng-prod",
    "path": "/curated/orders/",
    "metastoreSynchronizationEnabled": true,
    "metastoreDatabaseName": "analytics",
    "metastoreTableName": "orders_curated",
    "filesSelectionRules": {
      "mode": "ALL",
      "includeRules": [{"path": "*.parquet"}],
      "excludeRules": [{"path": "*_tmp.parquet"}]
    }
  },
  "formatType": "parquet",
  "formatParams": {
    "parquetCompressionMethod": "snappy",
    "parquetLowerCaseIdentifiers": true,
    "readTemporalMode": "TIMESTAMP_LTZ"
  }
}
```
Then: `dku dataset create orders_curated -t S3 -c s3_lake -d @s3_orders.json -P PROJ`.

CSV with strict schema mismatch behavior + gzip compression:
```json
{
  "type": "S3",
  "params": {"connection": "s3_lake", "bucket": "raw", "path": "/events/"},
  "formatType": "csv",
  "formatParams": {
    "parseHeaderRow": true,
    "compress": "gz",
    "readAdditionalColumnsBehavior": "FAIL",
    "readMissingColumnsBehavior": "FAIL",
    "readDataTypeMismatchBehavior": "FAIL",
    "fileReadFailureBehavior": "FAIL"
  }
}
```
The four `read*Behavior` knobs together give SQL-strict semantics on CSV reads —
DSS errors instead of silently coercing or skipping rows.

UploadedFiles backed by S3 (vs the default local disk):
```json
{
  "type": "UploadedFiles",
  "params": {
    "uploadFSProviderType": "S3",
    "uploadedConfig": {"connection": "s3_uploads", "bucket": "uploads", "path": "/${projectKey}/"}
  }
}
```
Trap: `dku dataset upload` resolves the local-FS path and may fail when the
provider is `S3`/`Azure`/`GCS` — upload via the DSS UI's Upload tile, or use
`folder upload` + `folder create-dataset` instead.

Variables-expansion loop (one dataset row per `$VAR` substitution, useful
when a folder holds files like `metric_${region}_${year}.csv`):
```json
{
  "type": "S3",
  "params": {
    "connection": "s3_lake",
    "bucket": "metrics",
    "path": "/metric_${region}_${year}.csv",
    "variablesExpansionLoopConfig": {
      "enabled": true,
      "mode": "VARIABLE",
      "variables": [
        {"name": "region", "values": ["us", "eu", "apac"]},
        {"name": "year", "values": ["2023", "2024", "2025"]}
      ]
    }
  },
  "formatType": "csv",
  "formatParams": {"parseHeaderRow": true}
}
```

---

## Overview

Dataset connectors (also called "Python connectors") allow Dataiku to read from and write to external data sources. Use cases include:
- REST API integrations
- Proprietary file formats
- Custom databases
- External services (Salesforce, Jira, etc.)

---

## Folder Structure

```
python-connectors/
└── my-connector/
    ├── connector.json    # Connector descriptor (REQUIRED)
    └── connector.py      # Python implementation (REQUIRED)
```

---

## connector.json Reference

### Complete Template

```json
{
  "meta": {
    "label": "My API Connector",
    "description": "Connect to My API to read and write data",
    "icon": "icon-cloud"
  },
  "readable": true,
  "writable": true,
  "params": [
    {
      "name": "api_endpoint",
      "type": "STRING",
      "label": "API Endpoint",
      "description": "Base URL for the API",
      "mandatory": true,
      "defaultValue": "https://api.example.com"
    },
    {
      "name": "resource_type",
      "type": "SELECT",
      "label": "Resource Type",
      "selectChoices": [
        {"value": "users", "label": "Users"},
        {"value": "orders", "label": "Orders"},
        {"value": "products", "label": "Products"}
      ],
      "mandatory": true
    },
    {
      "name": "api_key",
      "type": "PASSWORD",
      "label": "API Key",
      "description": "Authentication key for the API"
    },
    {
      "name": "page_size",
      "type": "INT",
      "label": "Page Size",
      "defaultValue": 100,
      "minI": 1,
      "maxI": 1000
    },
    {
      "name": "include_metadata",
      "type": "BOOLEAN",
      "label": "Include Metadata",
      "defaultValue": false
    }
  ],
  "partitioning": {
    "supported": true,
    "fileBasedPartitioning": true
  }
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `meta.label` | string | Display name for the connector |
| `meta.description` | string | Help text describing the connector |
| `meta.icon` | string | FontAwesome 3.2.1 icon |
| `readable` | boolean | Whether connector can read data |
| `writable` | boolean | Whether connector can write data |
| `params` | array | User-configurable parameters |
| `partitioning` | object | Partitioning configuration (optional) |

---

## connector.py Implementation

### Read-Only Connector Template

```python
"""
My API Connector - Read data from external API.
"""
import logging
import requests
from dataiku.connector import Connector

logger = logging.getLogger(__name__)


class MyConnector(Connector):
    """
    Custom connector for My API.

    Implements read operations for external data source.
    """

    def __init__(self, config, plugin_config):
        """
        Initialize connector with configuration.

        Args:
            config: User-specified dataset parameters
            plugin_config: Plugin-level configuration
        """
        Connector.__init__(self, config, plugin_config)

        # Extract configuration
        self.api_endpoint = config.get("api_endpoint")
        self.resource_type = config.get("resource_type")
        self.api_key = config.get("api_key") or plugin_config.get("api_key")
        self.page_size = config.get("page_size", 100)
        self.include_metadata = config.get("include_metadata", False)

        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def get_read_schema(self):
        """
        Return the schema for this dataset.

        Returns:
            dict with "columns" list, or None for auto-inference
        """
        # Define explicit schema
        base_columns = [
            {"name": "id", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "created_at", "type": "date"},
            {"name": "value", "type": "double"},
            {"name": "active", "type": "boolean"},
        ]

        if self.include_metadata:
            base_columns.extend([
                {"name": "metadata", "type": "object"},
                {"name": "tags", "type": "array"},
            ])

        return {"columns": base_columns}

        # Or return None for Dataiku to infer schema from data
        # return None

    def generate_rows(self, dataset_schema=None, dataset_partitioning=None,
                      partition_id=None, records_limit=-1):
        """
        Generate rows from the data source.

        Args:
            dataset_schema: Schema definition (from get_read_schema or user override)
            dataset_partitioning: Partitioning spec if applicable
            partition_id: Specific partition to read
            records_limit: Max rows to return (-1 for unlimited)

        Yields:
            dict: Row data keyed by column name
        """
        url = f"{self.api_endpoint}/{self.resource_type}"
        page = 1
        total_yielded = 0

        while True:
            # Fetch page
            try:
                response = self.session.get(url, params={
                    "page": page,
                    "page_size": self.page_size
                })
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                logger.error(f"API request failed: {e}")
                raise

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                # Transform API response to row
                row = {
                    "id": str(item.get("id")),
                    "name": item.get("name"),
                    "created_at": item.get("created_at"),
                    "value": float(item.get("value", 0)),
                    "active": bool(item.get("active")),
                }

                if self.include_metadata:
                    row["metadata"] = item.get("metadata", {})
                    row["tags"] = item.get("tags", [])

                yield row
                total_yielded += 1

                # Check limit
                if records_limit > 0 and total_yielded >= records_limit:
                    return

            # Check for more pages
            if not data.get("has_more", False):
                break
            page += 1

    def get_records_count(self):
        """
        Return total record count if available.

        Returns:
            int: Total count, or None if unknown
        """
        try:
            url = f"{self.api_endpoint}/{self.resource_type}/count"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json().get("count")
        except Exception:
            return None
```

### Writable Connector Template

Add write capability to your connector:

```python
from dataiku.connector import Connector, CustomDatasetWriter


class MyConnector(Connector):
    """Connector with read and write support."""

    def __init__(self, config, plugin_config):
        Connector.__init__(self, config, plugin_config)
        self.api_endpoint = config.get("api_endpoint")
        self.resource_type = config.get("resource_type")
        self.api_key = config.get("api_key") or plugin_config.get("api_key")

    def get_read_schema(self):
        return {"columns": [
            {"name": "id", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "value", "type": "double"},
        ]}

    def generate_rows(self, dataset_schema=None, dataset_partitioning=None,
                      partition_id=None, records_limit=-1):
        # ... reading logic ...
        pass

    def get_writer(self, dataset_schema=None, dataset_partitioning=None,
                   partition_id=None):
        """
        Return a writer for this dataset.

        Args:
            dataset_schema: Schema for data being written
            dataset_partitioning: Partitioning spec
            partition_id: Partition being written to

        Returns:
            CustomDatasetWriter instance
        """
        return MyConnectorWriter(self, dataset_schema, partition_id)


class MyConnectorWriter(CustomDatasetWriter):
    """Writer implementation for MyConnector."""

    def __init__(self, connector, schema, partition_id):
        CustomDatasetWriter.__init__(self)
        self.connector = connector
        self.schema = schema
        self.partition_id = partition_id
        self.buffer = []
        self.batch_size = 100

    def write_row(self, row):
        """
        Write a single row.

        Args:
            row: tuple of values in schema order
        """
        # Convert tuple to dict
        row_dict = {}
        for i, col in enumerate(self.schema):
            row_dict[col["name"]] = row[i]

        self.buffer.append(row_dict)

        # Flush buffer periodically
        if len(self.buffer) >= self.batch_size:
            self._flush()

    def _flush(self):
        """Send buffered rows to API."""
        if not self.buffer:
            return

        url = f"{self.connector.api_endpoint}/{self.connector.resource_type}/bulk"
        headers = {"Authorization": f"Bearer {self.connector.api_key}"}

        response = requests.post(url, json={"items": self.buffer}, headers=headers)
        response.raise_for_status()

        self.buffer = []

    def close(self):
        """Finalize writing."""
        self._flush()
```

---

## Schema Definition

### Supported Column Types

| Type | Description | Python Type |
|------|-------------|-------------|
| `string` | Text data | `str` |
| `int` | 32-bit integer | `int` |
| `bigint` | 64-bit integer | `int` |
| `float` | 32-bit decimal | `float` |
| `double` | 64-bit decimal | `float` |
| `boolean` | True/False | `bool` |
| `date` | ISO date string | `str` |
| `array` | JSON array | `list` |
| `object` | JSON object | `dict` |

### Schema Patterns

#### Explicit Schema

```python
def get_read_schema(self):
    return {
        "columns": [
            {"name": "id", "type": "string"},
            {"name": "timestamp", "type": "date"},
            {"name": "metrics", "type": "object"},
        ]
    }
```

#### Dynamic Schema Based on Config

```python
def get_read_schema(self):
    columns = [
        {"name": "id", "type": "string"},
        {"name": "name", "type": "string"},
    ]

    if self.resource_type == "metrics":
        columns.extend([
            {"name": "value", "type": "double"},
            {"name": "unit", "type": "string"},
        ])
    elif self.resource_type == "events":
        columns.extend([
            {"name": "event_type", "type": "string"},
            {"name": "payload", "type": "object"},
        ])

    return {"columns": columns}
```

#### Auto-Inferred Schema

```python
def get_read_schema(self):
    # Return None to let Dataiku infer from first rows
    return None
```

---

## Partitioning Support

### Enable Partitioning in connector.json

```json
{
  "partitioning": {
    "supported": true,
    "fileBasedPartitioning": false
  }
}
```

### Implement Partitioning Methods

```python
class MyPartitionedConnector(Connector):

    def get_partitioning(self):
        """
        Return partitioning scheme.

        Returns:
            dict defining dimensions
        """
        return {
            "dimensions": [
                {"name": "date", "type": "time", "params": {"period": "DAY"}},
                {"name": "region", "type": "value"}
            ]
        }

    def list_partitions(self, partitioning):
        """
        List available partitions.

        Args:
            partitioning: Partitioning scheme

        Returns:
            list of partition identifiers
        """
        # Query API for available partitions
        response = self.session.get(f"{self.api_endpoint}/partitions")
        partitions = response.json()

        return [
            f"{p['date']}|{p['region']}"
            for p in partitions
        ]

    def generate_rows(self, dataset_schema=None, dataset_partitioning=None,
                      partition_id=None, records_limit=-1):
        """Read specific partition."""
        if partition_id:
            # Parse partition ID
            date, region = partition_id.split("|")

            # Fetch partition data
            response = self.session.get(
                f"{self.api_endpoint}/data",
                params={"date": date, "region": region}
            )
            for item in response.json():
                yield self._transform_item(item)
        else:
            # Read all partitions
            for partition in self.list_partitions(dataset_partitioning):
                yield from self.generate_rows(
                    partition_id=partition,
                    records_limit=records_limit
                )
```

---

## Error Handling

### Robust Connector Pattern

```python
import logging
import time
from dataiku.connector import Connector

logger = logging.getLogger(__name__)


class RobustConnector(Connector):
    """Connector with comprehensive error handling."""

    MAX_RETRIES = 3
    RETRY_DELAY = 2

    def __init__(self, config, plugin_config):
        Connector.__init__(self, config, plugin_config)
        self.config = config

        # Validate configuration
        if not config.get("api_endpoint"):
            raise ValueError("API endpoint is required")

    def _request_with_retry(self, method, url, **kwargs):
        """Make HTTP request with retry logic."""
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = int(e.response.headers.get("Retry-After", self.RETRY_DELAY))
                    logger.warning(f"Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    last_error = e
                elif e.response.status_code >= 500:
                    # Server error - retry
                    logger.warning(f"Server error (attempt {attempt + 1}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                    last_error = e
                else:
                    # Client error - don't retry
                    raise
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                time.sleep(self.RETRY_DELAY * (attempt + 1))
                last_error = e

        raise last_error or Exception("Request failed after retries")

    def generate_rows(self, dataset_schema=None, dataset_partitioning=None,
                      partition_id=None, records_limit=-1):
        try:
            data = self._request_with_retry("GET", f"{self.api_endpoint}/data")
            for item in data.get("items", []):
                yield self._transform_item(item)
        except Exception as e:
            logger.error(f"Failed to fetch data: {e}")
            raise RuntimeError(f"Connector error: {e}")
```

---

## Common Patterns

### Pagination Handling

```python
def generate_rows(self, dataset_schema=None, dataset_partitioning=None,
                  partition_id=None, records_limit=-1):
    """Handle various pagination styles."""

    # Offset-based pagination
    offset = 0
    while True:
        data = self._fetch(offset=offset, limit=self.page_size)
        if not data:
            break
        yield from data
        offset += len(data)

    # Cursor-based pagination
    cursor = None
    while True:
        data = self._fetch(cursor=cursor)
        yield from data.get("items", [])
        cursor = data.get("next_cursor")
        if not cursor:
            break

    # Page number pagination
    page = 1
    while True:
        data = self._fetch(page=page)
        items = data.get("items", [])
        if not items:
            break
        yield from items
        if page >= data.get("total_pages", 1):
            break
        page += 1
```

### Caching for Performance

```python
class CachedConnector(Connector):
    """Connector with schema caching."""

    _schema_cache = {}

    def get_read_schema(self):
        cache_key = f"{self.api_endpoint}:{self.resource_type}"

        if cache_key not in self._schema_cache:
            # Fetch schema from API
            response = self.session.get(f"{self.api_endpoint}/schema/{self.resource_type}")
            schema = self._parse_schema(response.json())
            self._schema_cache[cache_key] = schema

        return self._schema_cache[cache_key]
```

---

## Testing Connectors

### Unit Test Pattern

```python
import pytest
from unittest.mock import Mock, patch
from python_connectors.my_connector.connector import MyConnector


class TestMyConnector:

    @pytest.fixture
    def connector(self):
        config = {
            "api_endpoint": "https://api.example.com",
            "resource_type": "users",
            "page_size": 10
        }
        plugin_config = {"api_key": "test-key"}
        return MyConnector(config, plugin_config)

    def test_get_read_schema(self, connector):
        schema = connector.get_read_schema()
        assert "columns" in schema
        assert len(schema["columns"]) > 0
        assert all("name" in col and "type" in col for col in schema["columns"])

    @patch("requests.Session.get")
    def test_generate_rows(self, mock_get, connector):
        mock_response = Mock()
        mock_response.json.return_value = {
            "items": [
                {"id": "1", "name": "Test", "value": 100, "active": True}
            ],
            "has_more": False
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        rows = list(connector.generate_rows())

        assert len(rows) == 1
        assert rows[0]["id"] == "1"
        assert rows[0]["name"] == "Test"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Schema mismatch | Ensure `generate_rows` yields dicts with exact column names from schema |
| Memory errors | Use generators and yield rows instead of building large lists |
| Connection timeouts | Implement retry logic with exponential backoff |
| Rate limiting | Respect `Retry-After` headers and add delays between requests |
| Authentication errors | Check plugin_config for centralized credentials |
