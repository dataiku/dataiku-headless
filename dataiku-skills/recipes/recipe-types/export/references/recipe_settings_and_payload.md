---
name: export-recipe-settings-and-payload-reference
description: "Settings and params reference for export recipes, including destination/format, selection, and naming controls."
---

# Export Recipe Settings And Payload Reference

Use this reference for `export` recipe edits (`get_recipe_settings` + `set_recipe_settings` action `set_params`).

## Observed Settings Shape

In these recipes:

- `params` controls behavior.
- `payload` is not used (`payload_error` observed when reading JSON payload).

Observed top-level params keys:

- `clearOutputPartition`
- `exportParams`
- `filter`
- `outputFilename` (optional)
- `timestampPrefix`
- `variablesExpansionLoopConfig`
- `containerSelection`

## Top-Level Params Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `clearOutputPartition` | no | `boolean` | Partition clearing behavior. |
| `exportParams` | yes | `object` | Core destination/format/selection config. |
| `filter` | no | `object` | Export-level row filter block. |
| `outputFilename` | optional | `string` | Optional output filename stem. |
| `timestampPrefix` | no | `object` | Optional timestamp prefix settings. |
| `variablesExpansionLoopConfig` | no | `object` | Dynamic variable loop settings (disabled in observed recipes). |
| `containerSelection` | no | `object` | Container execution mode settings. |

## `exportParams` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `destinationType` | yes | `enum` | Observed: `DOWNLOAD`. |
| `temporaryFileBehavior` | no | `enum` | Observed: `AUTO`. |
| `originatingOptionId` | yes | `enum/string` | Observed: `tsv-excel-header`, `tsv-excel-header-gz`, `excel`. |
| `format` | yes | `object` | File format config (`type`, `params`). |
| `destinationDatasetProjectKey` | no | `string<project_key>` | Preserve unless explicitly changing destination context. |
| `destinationDatasetConnection` | no | `string<connection_name>` | Preserve unless explicitly changing destination context. |
| `overwriteDestinationDataset` | no | `boolean` | Observed: `false`. |
| `applyExplorationFilters` | no | `boolean` | Observed: `false`. |
| `applyColoring` | no | `boolean` | Observed: `false`. |
| `selection` | no | `object` | Read selection/filter/sampling/ordering block. |
| `config` | optional | `object` | Optional extra config (observed as `{}` in one recipe). |

## `format` and `selection` Highlights

`format`:

- `type`: observed `csv` and `excel`.
- `params` includes format-specific controls.
  For `csv`, observed keys include: `separator`, `compress`, `charset`, `style`, quoting/escaping, and serialization/read-behavior fields.
  For `excel`, observed keys include: `sheetSelectionMode`, `sheetsToColumn`, `invalidCellStrategy`, `rowOverflowStrategy`, `cellOverflowStrategy`, `parseDatesToISO`.

`selection`:

- observed defaults: `samplingMethod="FULL"`, `partitionSelectionMethod="ALL"`.
- `selection.filter`: observed `{"enabled": false, "distinct": false}`.
- `selection.ordering`: observed `{"enabled": false, "rules": []}` in all recipes.

## Filter Integration

Export filtering can appear in:

1. `params.filter` (recipe-level filter block).
2. `params.exportParams.selection.filter` (selection-level filter toggle block).

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Params Examples (Trimmed)

### CSV export baseline

```json
{
  "clearOutputPartition": false,
  "exportParams": {
    "destinationType": "DOWNLOAD",
    "temporaryFileBehavior": "AUTO",
    "originatingOptionId": "tsv-excel-header",
    "format": {
      "type": "csv",
      "params": {
        "style": "excel",
        "charset": "utf8",
        "separator": ",",
        "compress": ""
      }
    },
    "selection": {
      "samplingMethod": "FULL",
      "partitionSelectionMethod": "ALL",
      "ordering": {"enabled": false, "rules": []}
    }
  },
  "filter": {"enabled": false, "distinct": false},
  "timestampPrefix": {"enabled": false, "format": "yyyy-MM-dd'T'HH:mm:ssX"},
  "variablesExpansionLoopConfig": {"enabled": false, "mode": "CREATE_VARIABLE_FOR_EACH_COLUMN", "replacements": []},
  "containerSelection": {"containerMode": "INHERIT"}
}
```

### CSV export with pipe separator and gzip compression

```json
{
  "exportParams": {
    "originatingOptionId": "tsv-excel-header-gz",
    "format": {
      "type": "csv",
      "params": {
        "separator": "|",
        "compress": "gz"
      }
    }
  },
  "outputFilename": "output_file_name",
  "filter": {"enabled": false, "distinct": false}
}
```

### CSV export with recipe-level filter, filename, and timestamp prefix

```json
{
  "filter": {
    "enabled": true,
    "distinct": false,
    "expression": "val('country') == \"US\"",
    "uiData": {"mode": "CUSTOM"}
  },
  "outputFilename": "export_file_name_country",
  "timestampPrefix": {"enabled": true, "format": "yyyy-MM-dd'T'HH:mm:ssX"}
}
```

### Excel export with filter

```json
{
  "exportParams": {
    "originatingOptionId": "excel",
    "format": {
      "type": "excel",
      "params": {
        "sheetSelectionMode": "NAMES",
        "sheetsToColumn": false,
        "invalidCellStrategy": "ERROR",
        "rowOverflowStrategy": "NEW_SHEET",
        "cellOverflowStrategy": "ERROR"
      }
    }
  },
  "filter": {"enabled": true, "distinct": false}
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current `params`.
3. Edit only intended blocks (`exportParams`, `filter`, filename/timestamp/loop controls).
4. Write params with `set_recipe_settings` action `set_params`.
5. Re-read settings to confirm only intended keys changed.
