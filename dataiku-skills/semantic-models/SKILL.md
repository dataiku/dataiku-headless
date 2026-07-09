---
name: semantic-models
description: Inspect, create, and edit Dataiku semantic models and their versions through MCP tools. Use when an agent must list semantic models, read version settings (entities, attributes, relationships, glossary terms, golden queries), create new models or versions, update version settings, set the active version, or trigger a distinct-values index update.
---

# Semantic Model Operations

Use Dataiku MCP tools to inspect and manage semantic models in a DSS project.

## What Is a DSS Semantic Model?

A DSS semantic model is a business-level description of data that maps datasets and their columns to named entities, attributes, metrics, and relationships. It provides the vocabulary and context that allow an LLM to generate correct SQL queries from natural language questions.

**Key concepts:**

- **Model**: A named container with an opaque ID (e.g., `z4EWrI8`), an active version, and a list of versions. The model itself stores no business logic — all content lives in its versions.
- **Version**: The substantive content of a semantic model. Versions have entities, relationships, glossary terms, golden queries, and indexing settings. One version is designated active.
- **Entity**: Maps a DSS dataset to a named business object (e.g., "Vehicle Sales" → `FACT_MONTHLY_VAR_SQL`). Each entity contains:
  - **Attributes**: Individual dataset columns with business descriptions and distinct-values indexing settings.
  - **Metrics**: Named computed expressions in pseudo-SQL (e.g., `(SUM(revenue) - SUM(costs)) / SUM(revenue)`).
  - **Filters**: Named SQL filter clauses for common subsets, with optional LLM instructions.
  - **Primary key**: The attribute(s) uniquely identifying each row.
- **Relationship**: A join condition between two entities, expressed as a pseudo-SQL column equality. Entities are referenced by display name, not ID.
- **Glossary terms**: Business vocabulary entries with synonyms, optionally bound to specific attributes or metrics.
- **Golden queries**: Curated natural-language → SQL examples that train the model's query generation.

## Follow This Execution Pattern

1. Call `list_semantic_models` to discover model IDs, names, active version IDs, and all version IDs.
2. Before any mutation, call `get_semantic_model_version_settings` to read the current version settings.
3. For edits: modify the returned `settings` dict and pass the complete modified dict to `set_semantic_model_version_settings`. Validate by re-reading with `get_semantic_model_version_settings`.
4. After adding or changing `AUTO_INDEX` attributes, call `update_semantic_model_distinct_values` to rebuild the index.
6. To create a new version: call `create_semantic_model_version` (optionally with `duplicate_of` to copy an existing version), then populate it with `set_semantic_model_version_settings`.

## Tool Reference

| Goal | Tool |
| --- | --- |
| Discover models in a project | `list_semantic_models` |
| Read a version's full settings | `get_semantic_model_version_settings` |
| Create a new semantic model | `create_semantic_model` |
| Create a new version (empty or duplicated from another) | `create_semantic_model_version` |
| Replace a version's full settings | `set_semantic_model_version_settings` |
| Set which version is active | `set_semantic_model_active_version` |
| Rebuild the distinct-values index after attribute changes | `update_semantic_model_distinct_values` |
| Delete a semantic model | `delete_semantic_model` |

## Version Settings Structure

`get_semantic_model_version_settings` returns a `settings` dict. Pass the full modified dict back to `set_semantic_model_version_settings` — it is a full replace. Top-level keys:

```json
{
  "id": "<version_id>",
  "description": "<string>",
  "entities": [ ... ],
  "relationships": [ ... ],
  "goldenQueries": [ ... ],
  "glossaryTerms": [ ... ],
  "glossaryBindings": [ ... ],
  "indexingSettings": {
    "maxDistinctValuesPerAttribute": 1000,
    "maxScannedRowsForSQLDatasets": -1,
    "maxScannedRowsForNonSQLDatasets": 1000000
  },
  "privateEditorData": { ... },
  "sqlGenerationConfig": {}
}
```

### Entity structure

`datasetRef` format is always `"PROJECT_KEY.DATASET_NAME"` — use `list_datasets` to discover valid names.

```json
{
  "name": "Vehicle Sales",
  "description": "Business description of what this entity represents",
  "type": "DATASET",
  "datasetRef": "PROJECT_KEY.DATASET_NAME",
  "tags": [],
  "attributes": [
    {
      "name": "column_name",
      "description": "Business description of the column",
      "dssType": "string",
      "type": "COLUMN",
      "column": "column_name",
      "distinctValuesHandlingMode": "NONE",
      "indexDistinctValues": false,
      "resolveInUserRequests": false,
      "manualValues": [],
      "sqlGenerationConfig": {}
    }
  ],
  "metrics": [
    {
      "name": "Net Profit Margin",
      "description": "Profit margin percentage",
      "pseudoSQLExpression": "(SUM(mass_TO_EU) - SUM(mass_COGS_VIN) - SUM(masse_VME_EU)) / SUM(mass_TO_EU)",
      "created": {}
    }
  ],
  "filters": [
    {
      "name": "Manual Transmission Vehicles",
      "description": "Filter to include only manual transmission vehicles",
      "pseudoSQLExpression": "TABLE_NAME.\"COLUMN\" LIKE 'BVM%'",
      "llmInstructions": "Apply when the user asks about manual transmission vehicles",
      "created": {}
    }
  ],
  "primaryKey": { "attributes": ["column_name"] },
  "foreignKeys": []
}
```

**`distinctValuesHandlingMode` values:**

| Value | When to use |
| --- | --- |
| `NONE` | Measures, high-cardinality IDs, and join keys — do not index |
| `AUTO_INDEX` | Filterable dimensions (countries, categories, date codes) — DSS scans and indexes |
| `MANUAL` | Controlled vocabularies — provide values in `manualValues` |

When `distinctValuesHandlingMode` is `AUTO_INDEX`, also set `indexDistinctValues: true` and `resolveInUserRequests: true`. Set `sqlGenerationConfig.autoValuesLimit` to cap how many values are used in SQL generation (e.g., `5` for high-cardinality dims used only as filters).

### Relationship structure

```json
{
  "firstEntity": "Vehicle Sales",
  "secondEntity": "Vehicle Specs",
  "pseudoSQLExpression": "CLE_VFGP_ID = CLE_VFGP_ID"
}
```

### Glossary term structure

Omit `id` when adding a new term — DSS assigns it. Preserve the `id` from the read result for existing terms.

```json
{
  "term": "Winter Push",
  "description": "Seasonal sales campaign covering December, January, and February",
  "source": "MANUAL",
  "userModified": true,
  "synonyms": ["Winter Sales Push", "Winter Promotion"],
  "privateEditorData": {}
}
```

### Glossary binding structure

`termId` must match an `id` in `glossaryTerms`. `targetEntityClass` must match the entity `name` exactly. `targetType` is `"ATTRIBUTE"` or `"METRIC"`.

```json
{
  "termId": "<uuid from the glossaryTerms list>",
  "targetEntityClass": "Entity Name",
  "targetName": "attribute_or_metric_name",
  "targetType": "ATTRIBUTE"
}
```

### Golden query structure

```json
{
  "name": "Descriptive title for this query",
  "question": "Natural language question as the user would ask it",
  "generatedSql": "SELECT ... FROM ... WHERE ...",
  "created": {}
}
```

## Safety Rules

- Never invent semantic model IDs — always discover them with `list_semantic_models`.
- Never write version settings without first reading the current settings.
- Preserve `privateEditorData`, `created` timestamps, and `sqlGenerationConfig` from the read result — do not strip or modify them.
- Treat `delete_semantic_model` as irreversible — confirm with the user before calling it.
