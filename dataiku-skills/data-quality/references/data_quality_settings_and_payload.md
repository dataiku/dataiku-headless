---
name: data-quality-rule-settings-and-payload-reference
description: "Observed settings and payload reference for DSS Data Quality rules, including common fields, rule family structures, and result payloads."
---

# Data Quality Rule Settings And Payload Reference

Use this reference when creating or updating Data Quality rules through `create_data_quality_rule` and `update_data_quality_rule`.

Data Quality rule payloads are type-specific. This reference records observed structures; it is not an exhaustive schema. For updates, read the target rule with `get_data_quality_rule`, modify only intended fields, and preserve unknown fields.

## Rule Type Quick Reference

Pick the type that matches the check intent, then consult the relevant section below for payload fields.

| Type | What it checks |
| --- | --- |
| `RecordCountInRangeRule` | Row count within hard/soft bounds |
| `ColumnMinInRangeRule` | Column minimum within hard/soft bounds |
| `ColumnMaxInRangeRule` | Column maximum within hard/soft bounds |
| `ColumnAvgInRangeRule` | Column mean within hard/soft bounds |
| `ColumnMedianInRangeRule` | Column median within hard/soft bounds |
| `ColumnSumInRangeRule` | Column sum within hard/soft bounds |
| `ColumnStdDevInRangeRule` | Column standard deviation within hard/soft bounds |
| `ColumnCountInRangeRule` | Dataset column count within hard/soft bounds |
| `ValuesInRangeRule` | Every individual row value in a column within bounds (row-level, not aggregate) |
| `numericRange` | A DSS metric value within hard/soft bounds |
| `DriftRecordCountRule` | Row count hasn't shifted from its historical baseline |
| `DriftColumnCountRule` | Column count hasn't shifted from its historical baseline |
| `DriftColumnMinRule` | Column minimum hasn't shifted from its historical baseline |
| `DriftColumnMaxRule` | Column maximum hasn't shifted from its historical baseline |
| `DriftColumnAvgRule` | Column mean hasn't shifted from its historical baseline |
| `DriftColumnMedianRule` | Column median hasn't shifted from its historical baseline |
| `DriftColumnSumRule` | Column sum hasn't shifted from its historical baseline |
| `DriftColumnStdDevRule` | Column standard deviation hasn't shifted from its historical baseline |
| `DriftColumnEmptyValueCountRule` | Empty value count hasn't shifted from its historical baseline |
| `DriftColumnUniqueValueCountRule` | Unique value count hasn't shifted from its historical baseline |
| `DriftMetricRule` | A DSS metric value hasn't shifted from its historical baseline |
| `ColumnNotEmptyRule` | Column empty rate is below a threshold — use to assert completeness |
| `ColumnEmptyRule` | Column empty rate is above a threshold — use to assert values ARE empty or sparse |
| `ColumnUniqueValuesRule` | Column values are unique or near-unique |
| `ValuesInSetRule` | All column values are members of an allowed set |
| `TopValuesInSetRule` | The top N most frequent values are all in a specified set |
| `ModeValueInSetRule` | The most frequent value is in a specified set |
| `valueSet` | A DSS metric value is one of an allowed set of values |
| `CompareMetricsRule` | A metric on this dataset satisfies a comparison (< = >) against a metric on another dataset |
| `ColumnMeaningValidityRule` | Column values conform to a DSS semantic meaning (e.g. LongMeaning, EmailMeaning) |
| `DatasetSchemaEqualsRule` | Dataset schema exactly matches an expected schema |
| `DatasetSchemaContainsRule` | Dataset schema contains at least the specified columns and types |
| `python` | Custom Python check — use only when no built-in type fits |

## Common Rule Fields

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string<rule_type>` | Rule implementation type. Required for create and update. |
| `id` | after create | `string<rule_id>` | DSS-assigned. Omit for create; preserve on update. |
| `displayName` | common | `string` | UI display name. |
| `enabled` | common | `boolean` | Disabled rules are ignored by compute/status. |
| `autoRun` | common | `boolean` | Runs after dataset builds. Errors can fail builds. |
| `computeOnBuildMode` | common | `enum/string` | Observed: `PARTITION`. Preserve unless intentionally changing. |

## Range Rule Fields

Covers: `RecordCountInRangeRule`, `ColumnCountInRangeRule`, `ColumnMinInRangeRule`, `ColumnMaxInRangeRule`, `ColumnAvgInRangeRule`, `ColumnMedianInRangeRule`, `ColumnSumInRangeRule`, `ColumnStdDevInRangeRule`, `ValuesInRangeRule`, metric-backed `numericRange`.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `columns` | column rules | `list<string<column_name>>` | Absent for `RecordCountInRangeRule`, `ColumnCountInRangeRule`, and `numericRange`. Validate with `get_dataset_info` before create. |
| `minimum` / `minimumEnabled` | common | `number` / `boolean` | Hard lower bound. |
| `maximum` / `maximumEnabled` | common | `number` / `boolean` | Hard upper bound. |
| `softMinimum` / `softMinimumEnabled` | common | `number` / `boolean` | Warning lower bound. |
| `softMaximum` / `softMaximumEnabled` | common | `number` / `boolean` | Warning upper bound. |
| `metricId` | `numericRange` | `string<metric_id>` | e.g. `basic:COUNT_COLUMNS`. |
| `autoComputeMetric` | `numericRange` | `boolean` | Whether DSS computes the metric automatically. |
| `meta` | `numericRange` | `object` | Preserve when present. |

## Drift Rule Fields

Covers: `DriftRecordCountRule`, `DriftColumnCountRule`, `DriftColumnMinRule`, `DriftColumnMaxRule`, `DriftColumnAvgRule`, `DriftColumnMedianRule`, `DriftColumnSumRule`, `DriftColumnStdDevRule`, `DriftColumnEmptyValueCountRule`, `DriftColumnUniqueValueCountRule`, `DriftMetricRule`.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `columns` | column rules | `list<string<column_name>>` | Absent for `DriftRecordCountRule`, `DriftColumnCountRule`, and `DriftMetricRule`. Validate with `get_dataset_info` before create. |
| `metricId` | `DriftMetricRule` | `string<metric_id>` | e.g. `reporting:BUILD_DURATION`. Replaces `columns`. |
| `driftParams` | yes | `object` | Drift configuration block. Preserve sibling fields on update. |

`driftParams` fields:

| Field | Domain | Notes |
| --- | --- | --- |
| `periodUnit` | `enum/string` | Observed: `DAYS`. |
| `learningPeriod` | `integer` | Baseline period length. |
| `lookbackPeriod` | `integer` | Recent comparison period length. |
| `iqrFactor` | `number` | Hard threshold multiplier. |
| `softIqrFactor` | `number` | Soft threshold multiplier. |
| `iqrFactorEnabled` | `boolean` | Enables hard drift threshold. |
| `softIqrFactorEnabled` | `boolean` | Enables soft drift threshold. |

## Empty, Not-Empty, And Unique Fields

Covers: `ColumnEmptyRule`, `ColumnNotEmptyRule`, `ColumnUniqueValuesRule`.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `columns` | yes | `list<string<column_name>>` | Validate with `get_dataset_info` before create. |
| `thresholdType` | yes | `enum/string` | Observed: `ENTIRE_COLUMN_EMPTY`, `ENTIRE_COLUMN_NOT_EMPTY`, `ENTIRE_COLUMN`. |
| `minimum` / `minimumEnabled` | observed | `number` / `boolean` | Observed on empty and unique rules. |
| `softMinimum` / `softMinimumEnabled` | observed | `number` / `boolean` | Observed on empty and unique rules. |
| `maximum` / `maximumEnabled` | observed | `number` / `boolean` | Observed on not-empty rules. |
| `softMaximum` / `softMaximumEnabled` | observed | `number` / `boolean` | Observed on not-empty rules. |

## Value Set Rule Fields

Covers: `ValuesInSetRule`, `TopValuesInSetRule`, `ModeValueInSetRule`, metric-backed `valueSet`.

Column-based types (`ValuesInSetRule`, `TopValuesInSetRule`, `ModeValueInSetRule`):

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `columns` | yes | `list<string<column_name>>` | Validate with `get_dataset_info` before create. |
| `valueSet` | yes | `list<string>` | Preserve full list on update unless intentionally replacing. |
| `topN` | `TopValuesInSetRule` | `integer` | Number of top values to check. |

Metric-backed `valueSet`:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `metricId` | yes | `string<metric_id>` | e.g. `basic:COUNT_COLUMNS`. |
| `values` | yes | `list<string>` | Allowed metric values as strings. Note: `values`, not `valueSet`. |
| `autoComputeMetric` | yes | `boolean` | Whether DSS computes the metric automatically. |
| `meta` | observed | `object` | Preserve when present. |

## Compare Metrics Rule Fields

`CompareMetricsRule`: compares a metric on this dataset against a metric on another dataset.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `metricId` | yes | `string<metric_id>` | Metric on this dataset, e.g. `basic:COUNT_COLUMNS`. |
| `metricBId` | yes | `string<metric_id>` | Metric on the reference dataset. Often same as `metricId`. |
| `datasetBName` | yes | `string<dataset_name>` | Reference dataset name in the same project. |
| `operator` | yes | `enum/string` | Observed: `LT`, `LTE`, `GT`, `GTE`, `EQ`. |
| `autoComputeMetric` | yes | `boolean` | Whether DSS computes the metric automatically. |

## Meaning Validity Fields

`ColumnMeaningValidityRule`: validates column values against a DSS semantic meaning.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `columnSpecs` | yes | `list<object>` | Uses specs instead of `columns`. |
| `columnSpecs[].column` | yes | `string<column_name>` | Validate with `get_dataset_info` before create. |
| `columnSpecs[].meaning` | optional | `string<meaning>` | If omitted, DSS uses the dataset column meaning. |
| `thresholdType` | yes | `enum/string` | Observed: `ENTIRE_COLUMN`. |
| `considerEmptyAsValid` | yes | `boolean` | Whether empty values are treated as valid. |
| `minimum` / `minimumEnabled` | observed | `number` / `boolean` | Threshold fields. |
| `softMinimum` / `softMinimumEnabled` | observed | `number` / `boolean` | Soft threshold fields. |

## Schema Rule Fields

`DatasetSchemaEqualsRule`: fails if any column is missing or extra. `DatasetSchemaContainsRule`: passes if all specified columns are present; extra columns allowed. Both use the same `expectedSchema` structure.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `expectedSchema` | yes | `object` | Expected dataset schema. Can be large. |
| `expectedSchema.columns` | yes | `list<object>` | Preserve complete list on update unless intentionally changing. |
| `expectedSchema.columns[].name` | yes | `string` | Column name. |
| `expectedSchema.columns[].type` | yes | `string<dss_type>` | Column type. |
| `expectedSchema.columns[].comment` | observed | `string` | Column comment. |
| `expectedSchema.columns[].meaning` | observed | `string` | Column meaning, when present. |
| `expectedSchema.columns[].maxLength` | observed | `integer` | String max length, when present. |
| `expectedSchema.userModified` | observed | `boolean` | Preserve when present. |

## Python Rule Fields

`python`: custom check — prefer built-in types; use Python only as a last resort.

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `code` | yes | `string<python_source>` | Defines a `process(last_values, dataset, partition_id)` function. |
| `envSelection` | yes | `object` | Code environment selection. Preserve unless intentionally changing runtime. |
| `envSelection.envMode` | yes | `enum/string` | Observed: `USE_BUILTIN_MODE`. |
| `envSelection.envName` | observed | `string` | Empty when built-in mode is used. |
| `meta` | observed | `object` | Preserve when present. |

## Result Payloads

| Field | Domain | Notes |
| --- | --- | --- |
| `id` | `string<rule_id>` | Rule associated with this result. |
| `outcome` | `enum/string` | `OK`, `WARNING`, `ERROR`, `EMPTY`. |
| `message` | `string` | Observed value or failure description. |
| `computeDate` | `integer<epoch_ms>` | Computation timestamp. |
| `partition` | `string` | `NP` for non-partitioned datasets. |

Uncomputed rules may be absent from latest results. Do not assume a missing result means a rule passed.

## Payload Examples

### Record count range (simple)

```json
{
  "type": "RecordCountInRangeRule",
  "minimum": 0.0,
  "minimumEnabled": true,
  "maximum": 1000000.0,
  "maximumEnabled": true,
  "displayName": "Record count is between 0 and 1000000",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Values in set

```json
{
  "type": "ValuesInSetRule",
  "columns": ["LOAN_PURPOSE"],
  "valueSet": ["debt_consolidation", "credit_card", "home_improvement", "other"],
  "displayName": "All values of LOAN_PURPOSE are in set",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Top N values in set

```json
{
  "type": "TopValuesInSetRule",
  "columns": ["LOAN_PURPOSE"],
  "topN": 4,
  "valueSet": ["debt_consolidation", "credit_card", "other", "home_improvement"],
  "displayName": "Top 4 values of LOAN_PURPOSE are in set",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Not-empty with percentage threshold

`thresholdType: MAX_PERCENTAGE_EMPTY` uses `maximum`/`softMaximum` as percentage bounds. Contrast with `ENTIRE_COLUMN_NOT_EMPTY` below, which encodes a zero-tolerance constraint in the type itself.

```json
{
  "type": "ColumnNotEmptyRule",
  "columns": ["ID"],
  "thresholdType": "MAX_PERCENTAGE_EMPTY",
  "maximum": 5.0,
  "maximumEnabled": true,
  "softMaximum": 2.5,
  "softMaximumEnabled": true,
  "displayName": "Less than 5% of ID is empty",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Not-empty (strict — zero empty values allowed)

```json
{
  "type": "ColumnNotEmptyRule",
  "columns": ["ID"],
  "thresholdType": "ENTIRE_COLUMN_NOT_EMPTY",
  "displayName": "No empty values exist in ID",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Meaning validity (`columnSpecs` instead of `columns`)

```json
{
  "type": "ColumnMeaningValidityRule",
  "columnSpecs": [{"column": "AMOUNT_REQUESTED", "meaning": "LongMeaning"}],
  "thresholdType": "ENTIRE_COLUMN",
  "considerEmptyAsValid": false,
  "minimum": 0.0,
  "minimumEnabled": false,
  "softMinimum": 0.0,
  "softMinimumEnabled": false,
  "displayName": "All values of AMOUNT_REQUESTED are valid",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Cross-dataset metric comparison

```json
{
  "type": "CompareMetricsRule",
  "metricId": "basic:COUNT_COLUMNS",
  "metricBId": "basic:COUNT_COLUMNS",
  "datasetBName": "LOAN_REQUESTS",
  "operator": "LT",
  "autoComputeMetric": true,
  "displayName": "Column count is less than column count on dataset LOAN_REQUESTS",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```

### Drift rule (`driftParams` nesting)

```json
{
  "type": "DriftColumnAvgRule",
  "columns": ["AirTime"],
  "driftParams": {
    "periodUnit": "DAYS",
    "learningPeriod": 4,
    "lookbackPeriod": 7,
    "iqrFactor": 1.5,
    "softIqrFactor": 1.25,
    "iqrFactorEnabled": true,
    "softIqrFactorEnabled": false
  },
  "displayName": "Avg of AirTime is within its typical range",
  "computeOnBuildMode": "PARTITION",
  "autoRun": true,
  "enabled": true
}
```
