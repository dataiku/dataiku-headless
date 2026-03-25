# Recipe Development Guide

> Complete reference for building custom Dataiku recipes that transform data, integrate LLMs, and process Knowledge Banks.

---

## Overview

Recipes are the core data transformation components in Dataiku. A custom recipe:
- Takes datasets, folders, models, or Knowledge Banks as inputs
- Produces datasets, folders, or models as outputs
- Executes Python, R, Spark, or SQL code
- Appears in the Flow alongside built-in recipes

---

## Folder Structure

```
custom-recipes/
└── my-recipe/
    ├── recipe.json      # Recipe descriptor (REQUIRED)
    ├── recipe.py        # Python implementation (REQUIRED for Python recipes)
    └── select_llms.py   # Optional: dynamic parameter choices
```

---

## recipe.json Reference

### Complete Template

```json
{
  "meta": {
    "label": "My Custom Recipe",
    "description": "Detailed description of what this recipe does",
    "icon": "icon-cogs",
    "iconColor": "blue"
  },
  "kind": "PYTHON",
  "inputRoles": [
    {
      "name": "input_dataset",
      "label": "Input Dataset",
      "description": "Primary dataset to process",
      "arity": "UNARY",
      "required": true,
      "acceptsDataset": true
    },
    {
      "name": "reference_data",
      "label": "Reference Data (optional)",
      "description": "Optional reference dataset",
      "arity": "NARY",
      "required": false,
      "acceptsDataset": true,
      "acceptsManagedFolder": true
    },
    {
      "name": "knowledge_bank",
      "label": "Knowledge Bank",
      "description": "Vector store for RAG",
      "arity": "UNARY",
      "required": false,
      "acceptsKnowledgeBank": true
    }
  ],
  "outputRoles": [
    {
      "name": "output_dataset",
      "label": "Output Dataset",
      "description": "Processed results",
      "arity": "UNARY",
      "required": true,
      "acceptsDataset": true
    },
    {
      "name": "metrics_folder",
      "label": "Metrics Folder",
      "description": "JSON metrics output",
      "arity": "UNARY",
      "required": false,
      "acceptsManagedFolder": true
    }
  ],
  "params": [
    {
      "type": "SEPARATOR",
      "name": "sep_model",
      "label": "Model Settings"
    },
    {
      "name": "llm_id",
      "type": "LLM",
      "label": "LLM Model",
      "description": "Select the LLM to use",
      "mandatory": true,
      "llmUsagePurpose": "GENERIC_COMPLETION"
    },
    {
      "name": "temperature",
      "type": "DOUBLE",
      "label": "Temperature",
      "defaultValue": 0.7,
      "minD": 0.0,
      "maxD": 2.0
    },
    {
      "type": "SEPARATOR",
      "name": "sep_processing",
      "label": "Processing Settings"
    },
    {
      "name": "batch_size",
      "type": "INT",
      "label": "Batch Size",
      "defaultValue": 10,
      "minI": 1,
      "maxI": 100
    },
    {
      "name": "max_concurrent",
      "type": "INT",
      "label": "Max Concurrent Workers",
      "defaultValue": 4,
      "minI": 1,
      "maxI": 16
    },
    {
      "name": "categories",
      "type": "MULTISELECT",
      "label": "Categories to Process",
      "selectChoices": [
        {"value": "category_a", "label": "Category A"},
        {"value": "category_b", "label": "Category B"},
        {"value": "category_c", "label": "Category C"}
      ],
      "defaultValue": ["category_a", "category_b"]
    },
    {
      "name": "enable_logging",
      "type": "BOOLEAN",
      "label": "Enable Detailed Logging",
      "defaultValue": false
    },
    {
      "name": "custom_prompt",
      "type": "TEXTAREA",
      "label": "Custom Prompt Template",
      "description": "Use {input} as placeholder"
    }
  ],
  "selectableFromDataset": "input_dataset",
  "selectableFromKnowledgeBank": "knowledge_bank",
  "paramsPythonSetup": "select_llms.py"
}
```

### Field Reference

#### Meta Section

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Display name in recipe menu |
| `description` | string | Tooltip/help text |
| `icon` | string | FontAwesome 3.2.1 icon |
| `iconColor` | string | red, pink, purple, blue, green, sky, yellow, orange, brown, gray |

#### Kind (Execution Engine)

| Value | Description |
|-------|-------------|
| `PYTHON` | Python recipe |
| `R` | R recipe |
| `SPARK` | PySpark recipe |
| `SQL` | SQL query recipe |
| `IMPALA` | Impala SQL |
| `HIVE` | Hive SQL |

#### Input/Output Roles

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Identifier used in code |
| `label` | string | Display name in UI |
| `description` | string | Help text |
| `arity` | string | `UNARY` (single) or `NARY` (multiple) |
| `required` | boolean | Whether input/output is mandatory |
| `acceptsDataset` | boolean | Can accept dataset |
| `acceptsManagedFolder` | boolean | Can accept managed folder |
| `acceptsSavedModel` | boolean | Can accept saved model |
| `acceptsKnowledgeBank` | boolean | Can accept Knowledge Bank (DSS 14.1+) |

#### Selectable From Flow

| Field | Description |
|-------|-------------|
| `selectableFromDataset` | Role name - recipe appears when dataset is right-clicked |
| `selectableFromFolder` | Role name - recipe appears when folder is right-clicked |
| `selectableFromSavedModel` | Role name - recipe appears when model is right-clicked |
| `selectableFromKnowledgeBank` | Role name - recipe appears when KB is right-clicked |

---

## recipe.py Implementation

### Standard Template

```python
"""
My Custom Recipe

Processes input datasets and produces output with LLM assistance.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import dataiku
import pandas as pd
from dataiku.customrecipe import (
    get_input_names_for_role,
    get_output_names_for_role,
    get_recipe_config,
    get_plugin_config,
)
from dataiku import Dataset

# Import shared library
from my_plugin_id.utils import call_llm, extract_json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

config = get_recipe_config()
plugin_config = get_plugin_config()

# Get parameters
llm_id = config.get("llm_id")
temperature = config.get("temperature", 0.7)
batch_size = config.get("batch_size", 10)
max_concurrent = config.get("max_concurrent", 4)
categories = config.get("categories", [])
enable_logging = config.get("enable_logging", False)
custom_prompt = config.get("custom_prompt", "")

# ============================================================================
# Input/Output Setup
# ============================================================================

# Get input dataset
input_names = get_input_names_for_role("input_dataset")
if not input_names:
    raise ValueError("Input dataset is required")
input_dataset = Dataset(input_names[0])

# Get optional reference data
reference_names = get_input_names_for_role("reference_data")
reference_datasets = [Dataset(name) for name in reference_names] if reference_names else []

# Get optional Knowledge Bank
kb_names = get_input_names_for_role("knowledge_bank")
knowledge_bank = None
if kb_names:
    client = dataiku.api_client()
    project = client.get_default_project()
    kb = project.get_knowledge_bank(kb_names[0])
    knowledge_bank = kb.as_core_knowledge_bank()

# Get output dataset
output_names = get_output_names_for_role("output_dataset")
if not output_names:
    raise ValueError("Output dataset is required")
output_dataset = Dataset(output_names[0])

# ============================================================================
# Processing Logic
# ============================================================================

def process_row(row: dict, llm, kb=None) -> dict:
    """Process a single row with LLM."""
    try:
        # Build context from Knowledge Bank if available
        context = ""
        if kb:
            docs = kb.search_vectors(query=row.get("text", ""), k=3)
            context = "\n".join([doc["content"] for doc in docs])

        # Call LLM
        prompt = custom_prompt.format(
            input=row.get("text", ""),
            context=context
        ) if custom_prompt else f"Process: {row.get('text', '')}"

        response = call_llm(llm, prompt, temperature=temperature)

        return {
            **row,
            "llm_response": response,
            "processed": True,
            "error": None
        }
    except Exception as e:
        logger.error(f"Error processing row: {e}")
        return {
            **row,
            "llm_response": None,
            "processed": False,
            "error": str(e)
        }

def main():
    """Main recipe execution."""
    logger.info("Starting recipe execution")

    # Load input data
    df = input_dataset.get_dataframe()
    records = df.to_dict("records")
    logger.info(f"Loaded {len(records)} records")

    # Filter by categories if specified
    if categories:
        records = [r for r in records if r.get("category") in categories]
        logger.info(f"Filtered to {len(records)} records by category")

    # Get LLM
    client = dataiku.api_client()
    project = client.get_default_project()
    llm = project.get_llm(llm_id)

    # Process in parallel
    results = []
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_row = {
            executor.submit(process_row, row, llm, knowledge_bank): row
            for row in records
        }

        for i, future in enumerate(as_completed(future_to_row)):
            result = future.result()
            results.append(result)

            if enable_logging or (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(records)} records")

    # Write output
    output_df = pd.DataFrame(results)
    output_dataset.write_with_schema(output_df)
    logger.info(f"Wrote {len(results)} records to output")

if __name__ == "__main__":
    main()
```

### API Reference

#### Input/Output Functions

```python
from dataiku.customrecipe import (
    get_input_names_for_role,    # Returns list of input names for a role
    get_output_names_for_role,   # Returns list of output names for a role
    get_recipe_config,           # Returns recipe parameters as dict
    get_plugin_config,           # Returns plugin-level config as dict
)
```

#### Dataset Operations

```python
from dataiku import Dataset

# Reading
dataset = Dataset("dataset_name")
df = dataset.get_dataframe()                    # Full DataFrame
df = dataset.get_dataframe(limit=1000)          # Limited rows
schema = dataset.read_schema()                  # Get column definitions

# Streaming read (for large datasets)
for chunk in dataset.iter_dataframes(chunksize=10000):
    process(chunk)

# Writing
dataset.write_with_schema(df)                   # Write with automatic schema
dataset.write_dataframe(df)                     # Write without schema update

# Writing with explicit schema
dataset.write_schema([
    {"name": "col1", "type": "string"},
    {"name": "col2", "type": "int"},
])
dataset.write_dataframe(df)
```

#### Knowledge Bank Operations (DSS 14.1+)

```python
import dataiku

# Get Knowledge Bank handle
client = dataiku.api_client()
project = client.get_default_project()
kb = project.get_knowledge_bank("kb_name")
core_kb = kb.as_core_knowledge_bank()

# Vector search
results = core_kb.search_vectors(
    query="search query",
    k=5,                          # Top K results
    filter={"category": "docs"}   # Optional metadata filter
)

for doc in results:
    print(doc["content"])         # Document content
    print(doc["metadata"])        # Document metadata
    print(doc["score"])           # Similarity score
```

#### Embedding Recipe Sync Modes

When using `create-embed` or `create-embed-docs` to build Knowledge Banks, the sync mode controls how updates are applied:

| Mode | Behavior | Use When |
|------|----------|----------|
| **Smart sync** | Only processes new/changed documents | Incremental KB updates (default) |
| **Upsert** | Inserts new, updates existing by ID | Controlled document updates |
| **Overwrite** | Replaces entire KB contents | Full rebuild from source |
| **Append** | Adds documents without dedup | Accumulating from multiple sources |

Configure via recipe settings after build: `settings.obj_payload["syncMode"] = "SMART_SYNC"`.

#### LLM Operations

```python
import dataiku

client = dataiku.api_client()
project = client.get_default_project()

# List available LLMs
llms = project.list_llms()

# Get specific LLM
llm = project.get_llm("llm_id")

# Create completion
completion = llm.new_completion()
completion.with_message("User prompt here", role="user")
completion.with_message("System instructions", role="system")

# Execute
response = completion.execute()
text = response.text

# With streaming
for chunk in completion.execute_streamed():
    print(chunk.text, end="")
```

---

## Common Patterns

### Error-Resilient Processing

```python
def build_error_result(row: dict, error: str) -> dict:
    """Create standardized error result matching output schema."""
    return {
        **row,
        "result": None,
        "success": False,
        "error": error,
        "processed_at": datetime.now().isoformat()
    }

def process_with_retry(row: dict, llm, max_retries: int = 3) -> dict:
    """Process with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return process_row(row, llm)
        except Exception as e:
            if attempt == max_retries - 1:
                return build_error_result(row, str(e))
            time.sleep(2 ** attempt)  # Exponential backoff
```

### Batch Processing for Large Datasets

```python
def process_in_batches(input_dataset, output_dataset, batch_size=1000):
    """Process large datasets in chunks to manage memory."""
    schema = None

    for chunk in input_dataset.iter_dataframes(chunksize=batch_size):
        processed = process_dataframe(chunk)

        if schema is None:
            schema = [{"name": col, "type": "string"} for col in processed.columns]
            output_dataset.write_schema(schema)

    # Write all batches with a single writer
    with output_dataset.get_writer() as writer:
        for chunk in input_dataset.iter_dataframes(chunksize=batch_size):
            processed = process_dataframe(chunk)
            for _, row in processed.iterrows():
                writer.write_row_dict(row.to_dict())
```

### Progress Reporting

```python
import sys

def process_with_progress(records, process_fn):
    """Process records with progress output."""
    total = len(records)
    results = []

    for i, record in enumerate(records):
        result = process_fn(record)
        results.append(result)

        # Progress to stderr (visible in job logs)
        if (i + 1) % 100 == 0 or (i + 1) == total:
            progress = (i + 1) / total * 100
            print(f"Progress: {i + 1}/{total} ({progress:.1f}%)", file=sys.stderr)

    return results
```

### Dynamic Schema Based on Processing

```python
def process_and_write_dynamic_schema(input_ds, output_ds, process_fn):
    """Write output with schema inferred from first result."""
    df = input_ds.get_dataframe()
    records = df.to_dict("records")

    if not records:
        output_ds.write_with_schema(pd.DataFrame())
        return

    # Process first record to infer schema
    first_result = process_fn(records[0])
    schema = infer_schema(first_result)
    output_ds.write_schema(schema)

    # Process remaining
    results = [first_result]
    results.extend([process_fn(r) for r in records[1:]])

    output_ds.write_dataframe(pd.DataFrame(results))

def infer_schema(record: dict) -> list:
    """Infer Dataiku schema from a record."""
    type_map = {
        str: "string",
        int: "bigint",
        float: "double",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return [
        {"name": k, "type": type_map.get(type(v), "string")}
        for k, v in record.items()
    ]
```

---

## Parameter Patterns

### LLM Selection with Dynamic Choices

```json
{
  "name": "llm_id",
  "type": "SELECT",
  "label": "LLM Model",
  "getChoicesFromPython": true,
  "triggerParameters": ["llm_purpose"]
}
```

```python
# _resource/select_llms.py
def do(payload, config, plugin_config, inputs):
    if payload.get("parameterName") == "llm_id":
        from dataiku import api_client
        client = api_client()
        project = client.get_default_project()

        # Filter by purpose if specified
        purpose = config.get("llm_purpose", "GENERIC_COMPLETION")
        llms = [
            llm for llm in project.list_llms()
            if purpose in llm.get("usagePurposes", [])
        ]

        return {
            "choices": [
                {"value": llm["id"], "label": llm.get("friendlyName", llm["id"])}
                for llm in llms
            ]
        }
    return {"choices": []}
```

### Conditional Parameter Visibility

```json
{
  "name": "advanced_mode",
  "type": "BOOLEAN",
  "label": "Enable Advanced Options",
  "defaultValue": false
},
{
  "name": "chunk_size",
  "type": "INT",
  "label": "Chunk Size",
  "defaultValue": 512,
  "visibilityCondition": "model.advanced_mode == true"
},
{
  "name": "overlap",
  "type": "INT",
  "label": "Chunk Overlap",
  "defaultValue": 50,
  "visibilityCondition": "model.advanced_mode == true"
}
```

### Column Selection from Input

```json
{
  "name": "text_column",
  "type": "COLUMN",
  "label": "Text Column",
  "description": "Column containing text to process",
  "columnRole": "input_dataset",
  "allowedColumnTypes": ["string"]
},
{
  "name": "metadata_columns",
  "type": "COLUMNS",
  "label": "Metadata Columns",
  "description": "Additional columns to preserve",
  "columnRole": "input_dataset",
  "mandatory": false
}
```

---

## Testing Recipes

### Unit Test Pattern

```python
# tests/test_recipe.py
import pytest
from unittest.mock import Mock, patch
import pandas as pd

# Import recipe functions
from custom_recipes.my_recipe.recipe import process_row

class TestProcessRow:
    def test_successful_processing(self):
        """Test successful row processing."""
        mock_llm = Mock()
        mock_llm.new_completion.return_value.execute.return_value.text = "Response"

        row = {"text": "Test input", "id": 1}
        result = process_row(row, mock_llm)

        assert result["processed"] == True
        assert result["llm_response"] == "Response"
        assert result["error"] is None

    def test_error_handling(self):
        """Test error handling in processing."""
        mock_llm = Mock()
        mock_llm.new_completion.side_effect = Exception("API Error")

        row = {"text": "Test input", "id": 1}
        result = process_row(row, mock_llm)

        assert result["processed"] == False
        assert "API Error" in result["error"]
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "No input dataset" | Check `get_input_names_for_role()` returns non-empty list |
| Schema mismatch | Use `write_with_schema()` or explicitly set schema before writing |
| Memory errors | Use `iter_dataframes()` for chunked processing |
| LLM not found | Verify LLM ID exists in project with `project.list_llms()` |
| Parallel processing failures | Add proper exception handling in worker functions |

### Debug Logging

```python
import logging
import sys

# Configure for Dataiku job logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Log configuration
logger.info(f"Config: {config}")
logger.debug(f"Processing {len(records)} records")
```
