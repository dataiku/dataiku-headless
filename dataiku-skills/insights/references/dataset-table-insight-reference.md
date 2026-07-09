# Dataset Table Insight Reference

Use this reference for `dataset_table` insight creation and full-settings edits (`create_insight`, `get_insight_settings`, `set_insight_settings`).

## Payload Shape

A reusable dataset-table insight binds to a dataset and persists table exploration state.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `dataset_table`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params` | yes | `object` | Dataset-table runtime and table-state container. |

## `params` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `datasetSmartName` | yes | `string<dataset_name>` | Source dataset smart name. |
| `shakerScript` | yes | `object` | Persisted exploration and display state for the table insight. |

## `shakerScript` Notes

Live table insights persist a large `shakerScript` block with:

- `steps`
- `columnsSelection`
- `columnOrder`
- `columnWidthsByName`
- `columnUseScientificNotationByName`
- `coloring`
- `sorting`
- `flagNumericValues`
- `analysisColumnData`
- `explorationSampling`
- `vizSampling`
- `exploreUIParams`
- `globalSearchQuery`
- `explorationFilters`
- `previewMode`

This is not a good candidate for handwritten minimal payloads. For edits:

- Read the live insight first.
- Preserve the full `shakerScript` unless you intentionally want to change table exploration state.
- Change `datasetSmartName` only when you know the target dataset has a compatible schema.

## Minimal Envelope

```json
{
  "type": "dataset_table",
  "name": "Customer info table",
  "listed": false,
  "params": {
    "datasetSmartName": "CUSTOMER_INFO",
    "shakerScript": {}
  }
}
```

## Practical Note

- Treat the `shakerScript` in that example as a placeholder for shape only, not as a production-ready create payload.
