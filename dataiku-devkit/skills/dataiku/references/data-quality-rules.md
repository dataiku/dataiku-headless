# Data Quality Rules

## Overview

DSS Data Quality rules are configured per-dataset to validate data against expectations. Rules are stored in the dataset's `checks` or `metricsChecks` settings. Rules can block builds, generate warnings, or just report.

## The 10 Rule Families

### 1. Record Count

| Type | What it checks |
|------|---------------|
| `RecordCountInRangeRule` | Row count stays within min/max bounds |

Supports `minimum`/`maximum` (hard bounds → ERROR) and `softMinimum`/`softMaximum` (soft → WARNING).

### 2. Size

| Type | What it checks |
|------|---------------|
| `FileSizeInRangeRule` | File size stays within min/max bounds |

Supports `minimum`/`maximum` (hard bounds → ERROR) and `softMinimum`/`softMaximum` (soft → WARNING).

### 3. Numeric Range

| Type | What it checks |
|------|---------------|
| `ColumnMinInRangeRule` | Column min value in range |
| `ColumnMaxInRangeRule` | Column max value in range |
| `ColumnAvgInRangeRule` | Column average in range |
| `ColumnSumInRangeRule` | Column sum in range |
| `ColumnStdDevInRangeRule` | Column std dev in range |
| `ColumnMedianInRangeRule` | Column median in range |
| `ColumnCountInRangeRule` | Column non-null count in range |

Required: `columns` list (must exist in schema), at least one hard bound (`minimumEnabled` + `minimum`, or `maximumEnabled` + `maximum`). Optional: `softMinimumEnabled`, `softMaximumEnabled`.

### 4. Emptiness & Presence

| Type | What it checks |
|------|---------------|
| `ColumnEmptyRule` | Selected columns must be empty |
| `ColumnNotEmptyRule` | Selected columns must be non-empty |

Common `thresholdType`: `ENTIRE_COLUMN_EMPTY` / `ENTIRE_COLUMN_NOT_EMPTY`. For percentage-based: `MIN_COUNT_EMPTY` / `MAX_COUNT_EMPTY` / `MIN_PERCENTAGE_EMPTY` / `MAX_PERCENTAGE_EMPTY` with corresponding `minimumEnabled`/`minimum` or `maximumEnabled`/`maximum`.

### 5. Uniqueness & Distinct Values

| Type | What it checks |
|------|---------------|
| `ColumnUniqueValuesRule` | Cardinality expectations on selected columns |

`thresholdType`:
- `ENTIRE_COLUMN` — column must be unique
- `MIN_COUNT` — requires `minimumEnabled=true` + `minimum`
- `MIN_PERCENTAGE` — requires `minimumEnabled=true` + `minimum`

### 6. Allowed Values & Range

| Type | What it checks |
|------|---------------|
| `ValuesInSetRule` | Values must belong to an allowed set (`valueSet`) |
| `ValuesInRangeRule` | Values must stay within a numeric range |

`ValuesInSetRule` requires `columns` and `valueSet`. `ValuesInRangeRule` requires `columns` and at least one enabled bound.

### 7. Top / Mode Value Membership

| Type | What it checks |
|------|---------------|
| `TopValuesInSetRule` | Top N most frequent values must be in an expected set |
| `ModeValueInSetRule` | Mode value must be in an expected set |

Require `columns` and `valueSet`. `TopValuesInSetRule` also supports `topN`.

### 8. Meaning Validity

| Type | What it checks |
|------|---------------|
| `ColumnMeaningValidityRule` | Values must be valid for the column's assigned meaning |

Requires `columnSpecs` (array of `{column, meaning}`) and `thresholdType`. If `meaning` is omitted for a column, the rule uses the schema-assigned meaning. Typical meanings: `Temperature`, `Latitude`, `Longitude`, `IPAddress`, `Email`, `URL`, `GeoPoint`, `UserAgent`.

### 9. Schema Containment

| Type | What it checks |
|------|---------------|
| `DatasetSchemaContainsRule` | Required columns remain present in the schema |

Requires `expectedSchema.columns` (array of `{name}`). Optionally validate `type` and `meaning` per column.

### 10. Metric Comparison

| Type | What it checks |
|------|---------------|
| `CompareMetricsRule` | Relationship between two metrics (greater, less, equal) |

## Execution Pattern

1. **Inspect**: `dku dq list DS -P PROJ` — list configured rules
2. **Create**: `dku dq create DS -P PROJ --config @rule.json` — raw JSON for any rule type, or use `--type`/`--column`/`--min`/`--max` for common rules
3. **Compute**: `dku dq compute DS -P PROJ [--rule-id ID]` — compute all enabled rules, or a single rule
4. **Results**: `dku dq results DS -P PROJ` — latest outcomes
5. **Status**: `dku dq status DS -P PROJ` — dataset-level DQ status
6. **Delete**: `dku dq delete DS -P PROJ --rule-id ID` — requires `-y` confirmation
7. **Project rollup**: `dku dq project-status -P PROJ` — DQ status across all datasets

`dku dq` is a top-level command group (not `dku dataset dq`). There is no `get`/`set`/`run` verb: create rules one at a time with `create --config`, and remove with `delete --rule-id`.

## Dataset Monitor

The dataset-level `monitor` flag controls whether the dataset contributes to broader Data Quality monitoring views. Rule configuration and computation are separate from this flag.

## Safety Rules

- Never delete a rule without explicit user confirmation.
- Prefer built-in rule types over Python-code rules. Create Python-code rules only when no built-in type can express the check.
- For column-based rules, verify referenced columns exist in the schema before creating.
- Treat `autoRun=true` as build-affecting: ERROR results can fail build jobs.
- `WARNING` is soft-threshold; `ERROR` is hard-threshold and can break builds.
- Drift rules need enough historical runs to be meaningful.
