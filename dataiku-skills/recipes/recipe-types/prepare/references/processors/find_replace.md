---
name: prepare-find-replace
description: "Observed JSON patterns for the FindReplace prepare/shaker processor."
---

# FindReplace Processor

Replace values in selected columns using explicit mapping rules, with configurable matching mode and normalization.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo = PATTERN`. |
| `output` | no | `string<column_name>` \| `""` | Any valid output column name or empty string | Empty string means replace in place; non-empty writes to a new output column. |
| `useDatasetForMapping` | yes | `boolean` | `true` \| `false` | Mapping source mode. Observed value: `false` (inline mapping list). |
| `mapping` | conditional | `list<object>` | List of `{from,to}` mapping rules | Required when `useDatasetForMapping = false`. |
| `mappingDatasetRef` | conditional | `string<dataset_ref>` | Any valid dataset name | Mapping dataset; required when `useDatasetForMapping = true`. Must also be wired as a secondary recipe input. |
| `mappingDatasetFromColumn` | conditional | `string<column_name>` | Any column of the mapping dataset | Match (`from`) column in the mapping dataset; required when `useDatasetForMapping = true`. |
| `mappingDatasetToColumn` | conditional | `string<column_name>` | Any column of the mapping dataset | Replacement (`to`) column in the mapping dataset; required when `useDatasetForMapping = true`. |
| `matching` | yes | `enum` | `FULL_STRING` \| `SUBSTRING` \| `PATTERN` | Matching strategy: full value, substring, or regex pattern. |
| `normalization` | yes | `enum` | `EXACT` \| `LOWERCASE` | Comparison normalization mode. |
| `stopAfterFirstMatch` | no | `boolean` | `true` \| `false` | Stop replacing after the first matching rule for each value. |

## `mapping[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `from` | yes | `string<any>` | Source value/sub-pattern to match. |
| `to` | yes | `string<any>` | Replacement value. |

## Canonical Variants

### Full-string mapping in place

```json
{
  "type": "FindReplace",
  "params": {
    "output": "",
    "useDatasetForMapping": false,
    "mapping": [
      {"from": "yes", "to": "True"},
      {"from": "no", "to": "False"},
      {"from": "", "to": "False"}
    ],
    "normalization": "EXACT",
    "columns": ["is_active"],
    "appliesTo": "SINGLE_COLUMN",
    "stopAfterFirstMatch": false,
    "matching": "FULL_STRING"
  }
}
```

### Regex pattern mapping to new output column

```json
{
  "type": "FindReplace",
  "params": {
    "output": "fake_user_agent_bowser",
    "useDatasetForMapping": false,
    "mapping": [
      {"from": "(\\w+)\\/", "to": "Browser "}
    ],
    "normalization": "EXACT",
    "columns": ["fake_user_agent"],
    "appliesTo": "SINGLE_COLUMN",
    "stopAfterFirstMatch": true,
    "matching": "PATTERN"
  }
}
```

### Substring mapping on multiple columns (case-insensitive)

```json
{
  "type": "FindReplace",
  "params": {
    "output": "",
    "useDatasetForMapping": false,
    "mapping": [
      {"from": ".1", "to": ""}
    ],
    "normalization": "LOWERCASE",
    "columns": ["geo_location", "fake_ip_address"],
    "appliesTo": "COLUMNS",
    "stopAfterFirstMatch": true,
    "matching": "SUBSTRING"
  }
}
```

### Dataset-backed mapping (secondary input)

```json
{
  "type": "FindReplace",
  "params": {
    "output": "category_mapped",
    "useDatasetForMapping": true,
    "mappingDatasetRef": "category_mapping",
    "mappingDatasetFromColumn": "from",
    "mappingDatasetToColumn": "to",
    "normalization": "EXACT",
    "columns": ["category"],
    "appliesTo": "SINGLE_COLUMN",
    "stopAfterFirstMatch": false,
    "matching": "FULL_STRING"
  }
}
```

The mapping dataset must also be wired as a secondary recipe input with role `reference` (the recipe then has a `main` input plus a `reference` input). Runs on the DSS engine on filesystem input and pushes down to an in-database join on a SQL input.

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FindReplace`.
3. Keep scope fields coherent (`appliesTo` with `columns` or `appliesToPattern`).
4. Keep mapping-source mode coherent: `useDatasetForMapping=false` with inline `mapping[]`; for dataset-backed mapping set `useDatasetForMapping=true`, provide `mappingDatasetRef`/`mappingDatasetFromColumn`/`mappingDatasetToColumn`, and wire that dataset as a secondary recipe input with role `reference`.
5. Keep matching behavior coherent (`matching`, `normalization`, and `stopAfterFirstMatch` together define replacement behavior).
