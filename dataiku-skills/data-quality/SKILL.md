---
name: data-quality
description: Inspect Dataiku Data Quality rules and results. Use when an agent must discover existing rules, read rule outcomes, or understand quality status before asking Cobuild to modify project assets.
---

# Data Quality Inspection

Use this skill to inspect Data Quality rules and outcomes.

## Workflow

1. Use `list_data_quality_rules` to discover rules on a dataset.
2. Use `get_data_quality_status` for the current overall quality status.
3. Use `get_data_quality_rule`, `get_data_quality_rule_results`, and `get_data_quality_rule_history` for rule-specific details.
4. If the task requires creating, updating, computing, or deleting quality rules, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_data_quality_rules`
- `get_data_quality_status`
- `get_data_quality_rule`
- `get_data_quality_rule_results`
- `get_data_quality_rule_history`

## Rule Type Quick Reference

Use this to interpret an existing rule's `type` from `get_data_quality_rule`, or to describe the right rule type in a Cobuild prompt:

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
| `DriftRecordCountRule` / `DriftColumnCountRule` / `DriftColumnMinRule` / `DriftColumnMaxRule` / `DriftColumnAvgRule` / `DriftColumnMedianRule` / `DriftColumnSumRule` / `DriftColumnStdDevRule` / `DriftColumnEmptyValueCountRule` / `DriftColumnUniqueValueCountRule` / `DriftMetricRule` | Corresponding stat hasn't shifted from its historical baseline |
| `ColumnNotEmptyRule` | Column empty rate is below a threshold — asserts completeness |
| `ColumnEmptyRule` | Column empty rate is above a threshold — asserts values ARE empty/sparse |
| `ColumnUniqueValuesRule` | Column values are unique or near-unique |
| `ValuesInSetRule` | All column values are members of an allowed set |
| `TopValuesInSetRule` | The top N most frequent values are all in a specified set |
| `ModeValueInSetRule` | The most frequent value is in a specified set |
| `valueSet` | A DSS metric value is one of an allowed set of values |
| `CompareMetricsRule` | A metric on this dataset satisfies a comparison (< = >) against a metric on another dataset |
| `ColumnMeaningValidityRule` | Column values conform to a DSS semantic meaning (e.g. `LongMeaning`, `EmailMeaning`) |
| `DatasetSchemaEqualsRule` | Dataset schema exactly matches an expected schema |
| `DatasetSchemaContainsRule` | Dataset schema contains at least the specified columns and types |
| `python` | Custom Python check — use only when no built-in type fits |

## Safety Rules

- Inspect the dataset first with the dataset skill when rule context matters.
- Do not document direct Data Quality write workflows here.
