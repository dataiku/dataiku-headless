# Macros (Runnables) Guide

> Complete reference for building one-click utilities and automation tools as Dataiku plugin components.

---

## Overview

Macros (also called "runnables") are executable utilities that:
- Run on-demand from the UI or via API
- Can operate on specific objects (datasets, folders, models) or project-wide
- Return results as HTML, tables, files, or URLs
- Integrate with scenarios for automation

---

## Folder Structure

```
python-runnables/
└── my-macro/
    ├── runnable.json    # Macro descriptor (REQUIRED)
    └── runnable.py      # Python implementation (REQUIRED)
```

---

## runnable.json Reference

### Complete Template

```json
{
  "meta": {
    "label": "My Utility Macro",
    "description": "Performs automated operations on datasets",
    "icon": "icon-magic"
  },
  "impersonate": false,
  "resultType": "HTML",
  "resultLabel": "Operation Results",
  "macroRoles": [
    {
      "type": "DATASET",
      "targetParamsKey": "dataset_id"
    }
  ],
  "params": [
    {
      "name": "dataset_id",
      "type": "DATASET",
      "label": "Target Dataset",
      "description": "Dataset to operate on",
      "mandatory": true
    },
    {
      "name": "operation_type",
      "type": "SELECT",
      "label": "Operation Type",
      "selectChoices": [
        {"value": "analyze", "label": "Analyze Schema"},
        {"value": "validate", "label": "Validate Data"},
        {"value": "profile", "label": "Generate Profile"}
      ],
      "defaultValue": "analyze"
    },
    {
      "name": "include_samples",
      "type": "BOOLEAN",
      "label": "Include Sample Data",
      "defaultValue": true
    },
    {
      "name": "sample_size",
      "type": "INT",
      "label": "Sample Size",
      "defaultValue": 100,
      "visibilityCondition": "model.include_samples == true"
    }
  ]
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `meta.label` | string | Display name in Macro menu |
| `meta.description` | string | Help text |
| `meta.icon` | string | FontAwesome 3.2.1 icon |
| `impersonate` | boolean | Run as the calling user (requires setup) |
| `resultType` | string | Output format (see below) |
| `resultLabel` | string | Label for result output |
| `macroRoles` | array | Where macro appears in UI |
| `params` | array | User parameters |

### resultType Options

| Type | Description | Return Value in Python |
|------|-------------|----------------------|
| `HTML` | Formatted HTML report | `str` (HTML content) |
| `RESULT_TABLE` | Tabular data | `str` (JSON table) |
| `FILE` | Raw file/binary data | `bytes` |
| `URL` | Redirect to URL | `str` (URL) |
| `NONE` | No output | `None` |

### macroRoles Configuration

| type | Description | Usage |
|------|-------------|-------|
| `DATASET` | Single dataset | Appears in dataset's action menu |
| `DATASETS` | Multiple datasets | Appears when datasets are selected |
| `MANAGED_FOLDER` | Single folder | Appears in folder's action menu |
| `SAVED_MODEL` | Single model | Appears in model's action menu |
| `API_SERVICE` | API service | Appears in API service menu |
| `API_SERVICE_VERSION` | API version | Appears in version menu |
| `PROJECT_MACROS` | Project-level | Appears in project Macros menu |
| `PROJECT_CREATOR` | Special | Appears in project creation flow |

---

## runnable.py Implementation

### Standard Template

```python
"""
My Utility Macro

Performs automated operations on Dataiku objects.
"""
import json
import logging
from datetime import datetime

import dataiku
from dataiku.runnables import Runnable, ResultTable

logger = logging.getLogger(__name__)


class MyMacro(Runnable):
    """
    Custom macro implementation.

    Inherits from Runnable and implements required methods.
    """

    def __init__(self, project_key, config, plugin_config):
        """
        Initialize the macro.

        Args:
            project_key: Current project key
            config: User-specified parameters
            plugin_config: Plugin-level configuration
        """
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config

        # Extract parameters
        self.dataset_id = config.get("dataset_id")
        self.operation_type = config.get("operation_type", "analyze")
        self.include_samples = config.get("include_samples", True)
        self.sample_size = config.get("sample_size", 100)

        # Initialize API client
        self.client = dataiku.api_client()
        self.project = self.client.get_project(project_key)

    def get_progress_target(self):
        """
        Return progress tracking info.

        Returns:
            tuple: (target_count, unit_type)
            unit_type: NONE, SIZE, FILES, RECORDS, or custom string
        """
        if self.operation_type == "analyze":
            return (3, "NONE")  # 3 steps
        elif self.operation_type == "validate":
            return (100, "RECORDS")
        else:
            return (None, "NONE")  # Indeterminate

    def run(self, progress_callback):
        """
        Execute the macro.

        Args:
            progress_callback: Function to report progress

        Returns:
            Result based on resultType in runnable.json
        """
        logger.info(f"Starting macro: {self.operation_type} on {self.dataset_id}")

        try:
            if self.operation_type == "analyze":
                return self._analyze_schema(progress_callback)
            elif self.operation_type == "validate":
                return self._validate_data(progress_callback)
            elif self.operation_type == "profile":
                return self._generate_profile(progress_callback)
            else:
                raise ValueError(f"Unknown operation: {self.operation_type}")
        except Exception as e:
            logger.error(f"Macro failed: {e}")
            return self._error_html(str(e))

    def _analyze_schema(self, progress_callback):
        """Analyze dataset schema and return HTML report."""
        progress_callback(0)

        # Get dataset
        ds = dataiku.Dataset(self.dataset_id)
        schema = ds.read_schema()
        progress_callback(1)

        # Build analysis
        analysis = {
            "column_count": len(schema),
            "columns": [
                {
                    "name": col["name"],
                    "type": col.get("type", "unknown"),
                    "meaning": col.get("meaning", "")
                }
                for col in schema
            ]
        }
        progress_callback(2)

        # Generate HTML
        html = self._build_html_report(analysis)
        progress_callback(3)

        return html

    def _validate_data(self, progress_callback):
        """Validate data and return HTML report."""
        ds = dataiku.Dataset(self.dataset_id)
        df = ds.get_dataframe()

        total_rows = len(df)
        issues = []

        for i, (_, row) in enumerate(df.iterrows()):
            # Check for nulls
            null_cols = row[row.isna()].index.tolist()
            if null_cols:
                issues.append({
                    "row": i,
                    "type": "null_values",
                    "columns": null_cols
                })

            # Report progress
            if i % 10 == 0:
                progress_callback(min(i, 100))

        progress_callback(100)

        return self._build_validation_html(total_rows, issues)

    def _generate_profile(self, progress_callback):
        """Generate data profile as HTML."""
        ds = dataiku.Dataset(self.dataset_id)
        df = ds.get_dataframe()

        profile = {
            "row_count": len(df),
            "columns": []
        }

        for col in df.columns:
            col_profile = {
                "name": col,
                "dtype": str(df[col].dtype),
                "null_count": df[col].isna().sum(),
                "unique_count": df[col].nunique()
            }

            if df[col].dtype in ['int64', 'float64']:
                col_profile.update({
                    "min": df[col].min(),
                    "max": df[col].max(),
                    "mean": df[col].mean()
                })

            profile["columns"].append(col_profile)

        return self._build_profile_html(profile)

    def _build_html_report(self, analysis):
        """Build HTML for schema analysis."""
        rows = ""
        for col in analysis["columns"]:
            rows += f"""
            <tr>
                <td>{col['name']}</td>
                <td>{col['type']}</td>
                <td>{col['meaning']}</td>
            </tr>
            """

        return f"""
        <div class="macro-result">
            <h2>Schema Analysis: {self.dataset_id}</h2>
            <p><strong>Total Columns:</strong> {analysis['column_count']}</p>
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Column</th>
                        <th>Type</th>
                        <th>Meaning</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            <p><em>Generated at {datetime.now().isoformat()}</em></p>
        </div>
        """

    def _build_validation_html(self, total_rows, issues):
        """Build HTML for validation results."""
        issue_summary = {}
        for issue in issues:
            issue_type = issue["type"]
            issue_summary[issue_type] = issue_summary.get(issue_type, 0) + 1

        status = "success" if not issues else "warning"
        status_text = "PASSED" if not issues else f"{len(issues)} ISSUES FOUND"

        return f"""
        <div class="macro-result">
            <h2>Validation Results: {self.dataset_id}</h2>
            <div class="alert alert-{status}">
                <strong>Status:</strong> {status_text}
            </div>
            <p><strong>Total Rows:</strong> {total_rows}</p>
            <p><strong>Issues Found:</strong> {len(issues)}</p>
            <ul>
                {''.join(f'<li>{k}: {v}</li>' for k, v in issue_summary.items())}
            </ul>
        </div>
        """

    def _build_profile_html(self, profile):
        """Build HTML for data profile."""
        rows = ""
        for col in profile["columns"]:
            stats = ""
            if "mean" in col:
                stats = f"Min: {col['min']:.2f}, Max: {col['max']:.2f}, Mean: {col['mean']:.2f}"

            rows += f"""
            <tr>
                <td>{col['name']}</td>
                <td>{col['dtype']}</td>
                <td>{col['null_count']}</td>
                <td>{col['unique_count']}</td>
                <td>{stats}</td>
            </tr>
            """

        return f"""
        <div class="macro-result">
            <h2>Data Profile: {self.dataset_id}</h2>
            <p><strong>Total Rows:</strong> {profile['row_count']}</p>
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Column</th>
                        <th>Type</th>
                        <th>Nulls</th>
                        <th>Unique</th>
                        <th>Statistics</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """

    def _error_html(self, message):
        """Build error HTML."""
        return f"""
        <div class="macro-result">
            <div class="alert alert-danger">
                <strong>Error:</strong> {message}
            </div>
        </div>
        """
```

### Returning Different Result Types

#### RESULT_TABLE

```python
from dataiku.runnables import ResultTable

def run(self, progress_callback):
    """Return tabular results."""
    table = ResultTable()

    # Add columns
    table.add_column("name", "Name", "STRING")
    table.add_column("value", "Value", "DOUBLE")
    table.add_column("status", "Status", "STRING")

    # Add rows
    table.add_record(["Item 1", 100.5, "OK"])
    table.add_record(["Item 2", 200.0, "Warning"])
    table.add_record(["Item 3", 50.25, "OK"])

    return table
```

#### FILE

```python
import io
import csv

def run(self, progress_callback):
    """Return file download."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Write CSV
    writer.writerow(["Column1", "Column2", "Column3"])
    writer.writerow(["Value1", "Value2", "Value3"])

    # Return as bytes
    return output.getvalue().encode("utf-8")
```

#### URL

```python
def run(self, progress_callback):
    """Return redirect URL."""
    # Process something
    report_id = self._generate_report()

    # Return URL to redirect to
    return f"/projects/{self.project_key}/reports/{report_id}"
```

---

## Project-Level Macros

Macros without `macroRoles` appear in the project's Macros menu.

### runnable.json

```json
{
  "meta": {
    "label": "Project Health Check",
    "description": "Analyze all datasets in the project",
    "icon": "icon-heartbeat"
  },
  "resultType": "HTML",
  "params": [
    {
      "name": "include_managed_folders",
      "type": "BOOLEAN",
      "label": "Include Managed Folders",
      "defaultValue": false
    }
  ]
}
```

### runnable.py

```python
class ProjectHealthCheck(Runnable):
    """Project-wide health check macro."""

    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.client = dataiku.api_client()
        self.project = self.client.get_project(project_key)

    def get_progress_target(self):
        # Count datasets for progress
        datasets = self.project.list_datasets()
        return (len(datasets), "FILES")

    def run(self, progress_callback):
        """Check all datasets in project."""
        datasets = self.project.list_datasets()
        results = []

        for i, ds_info in enumerate(datasets):
            try:
                ds = dataiku.Dataset(ds_info["name"])
                schema = ds.read_schema()

                results.append({
                    "name": ds_info["name"],
                    "type": ds_info.get("type", "unknown"),
                    "columns": len(schema),
                    "status": "OK"
                })
            except Exception as e:
                results.append({
                    "name": ds_info["name"],
                    "type": ds_info.get("type", "unknown"),
                    "columns": 0,
                    "status": f"Error: {e}"
                })

            progress_callback(i + 1)

        return self._build_html(results)
```

---

## Multi-Object Macros

Operate on multiple selected objects at once.

### runnable.json

```json
{
  "meta": {
    "label": "Bulk Tag Datasets",
    "description": "Add tags to multiple datasets",
    "icon": "icon-tags"
  },
  "resultType": "HTML",
  "macroRoles": [
    {
      "type": "DATASETS",
      "targetParamsKey": "dataset_ids"
    }
  ],
  "params": [
    {
      "name": "dataset_ids",
      "type": "DATASETS",
      "label": "Target Datasets",
      "mandatory": true
    },
    {
      "name": "tags",
      "type": "STRINGS",
      "label": "Tags to Add"
    }
  ]
}
```

### runnable.py

```python
class BulkTagDatasets(Runnable):
    """Add tags to multiple datasets."""

    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.dataset_ids = config.get("dataset_ids", [])
        self.tags = config.get("tags", [])
        self.client = dataiku.api_client()
        self.project = self.client.get_project(project_key)

    def get_progress_target(self):
        return (len(self.dataset_ids), "FILES")

    def run(self, progress_callback):
        results = []

        for i, ds_id in enumerate(self.dataset_ids):
            try:
                ds = self.project.get_dataset(ds_id)
                settings = ds.get_settings()

                # Add tags
                current_tags = settings.get_raw().get("tags", [])
                new_tags = list(set(current_tags + self.tags))
                settings.get_raw()["tags"] = new_tags
                settings.save()

                results.append({"dataset": ds_id, "status": "Tagged"})
            except Exception as e:
                results.append({"dataset": ds_id, "status": f"Error: {e}"})

            progress_callback(i + 1)

        return self._build_summary_html(results)
```

---

## Scenario Integration

Macros can be triggered from scenarios for automation.

### Triggering from Scenario Steps

1. Add a "Run DSS plugin" step in the scenario
2. Select the plugin and macro
3. Configure parameters

### Programmatic Execution

```python
import dataiku

client = dataiku.api_client()
project = client.get_project("MY_PROJECT")

# Get macro handle
macro = project.get_runnable("my-plugin_my-macro")

# Execute with parameters
result = macro.run(
    params={
        "dataset_id": "my_dataset",
        "operation_type": "analyze"
    }
)

# Check result
print(result.get_output())
```

---

## Best Practices

### Progress Reporting

```python
def run(self, progress_callback):
    """Always report meaningful progress."""
    total_items = len(self.items)

    for i, item in enumerate(self.items):
        # Process item
        self._process(item)

        # Report progress (0 to target)
        progress_callback(i + 1)

    # Or for percentage-based:
    # progress_callback(int((i + 1) / total_items * 100))
```

### Error Handling

```python
def run(self, progress_callback):
    """Handle errors gracefully."""
    try:
        result = self._do_work(progress_callback)
        return result
    except dataiku.DataikuException as e:
        # Dataiku-specific error
        return self._error_html(f"Dataiku error: {e}")
    except Exception as e:
        # Generic error
        logger.exception("Macro failed")
        return self._error_html(f"Unexpected error: {e}")
```

### Long-Running Operations

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run(self, progress_callback):
    """Parallelize long operations."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(self._process_item, item): item
            for item in self.items
        }

        completed = 0
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            progress_callback(completed)
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Macro not appearing | Check `macroRoles` matches object type, reload plugin |
| Progress not updating | Ensure `get_progress_target()` returns correct values |
| HTML not rendering | Use valid HTML, check for unclosed tags |
| Timeout errors | Optimize processing, use progress callbacks for long operations |
| Permission errors | Check `impersonate` setting, verify user permissions |
