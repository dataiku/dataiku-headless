---
name: visual-conditions-params
description: "Visual Conditions reference, used in visual filter sections, the prepare recipe 'Create if, then, else statements' processor, split recipe, and others."
---

# Visual Conditions Overview

Visual Conditions can used in various places in Dataiku projects, including filter sections of visual recipes (Sample, Join), the split recipe, and in prepare recipe 'Create if, then, else statements' processors.

Visual Conditions are defined by an input column, an operator, and a value.
- Input column: choose any column from the dataset.
- Operator: choose an operator from the dropdown menu. The available operators match the storage type of the column. (a string column will have string operators available, such as contains, while a number column will have numerical operators available, such as <).
- value : input a value or choose an existing column to apply the operator to.

Conditions can be added, deleted, duplicated, and turned into a group to create advanced conditions.

## Params

Use this reference for DSS visual rule Conditions represented as `uiData.conditions[]`.

## `uiData` Condition Group Fields Observed

| Field | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `&&` \| `\|\|` | Boolean combinator across conditions in `conditions[]` (AND/OR). |
| `conditions` | yes | `list<object>` | List of condition-row objects | Ordered list of rule conditions. |
| `$latestOperator` | no | `enum` | Observed: `&&`, `\|\|` | UI marker of latest selected combinator (common in recipe filter payloads). |

## `uiData.conditions[]` Fields Observed

| Field | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `operator` | yes | `enum` | See `Supported operator values` below. | Rule operator token from UI. |
| `input` | no | `string<column_name>` | Any valid input column name | Left-hand value or reference source. |
| `col` | no | `string<column_name>` | Any valid input column name | Comparison column in column-vs-column/rule setups. |
| `string` | conditional | `string<any>` | Any text literal | String literal input for text/regex operations. |
| `num` | conditional | `number` | Any numeric literal | Numeric literal input. |
| `num2` | conditional | `number` | Any numeric literal | Secondary numeric literal (range operators). |
| `items` | conditional | `list<object>` | List of item objects | Used by `in [string]` and related operators. |
| `$showList` | no | `boolean` | `true` \| `false` | UI list display hint. |

## Supported operator values

Note: For defined / undefined checks, use `not empty string` and `empty string` across all data types.

```text
"array contains"
"array not contains"
"not empty string"
"empty string"
"true"
"false"
"== [string]"
"== [string]i"
"!= [string]"
"== [NaNcolumn]"
"!= [NaNcolumn]"
"== [number]"
"!= [number]"
">  [number]"
"<  [number]"
">= [number]"
"<= [number]"
">< [number]"
"<> [number]"
"== [date]"
">  [date]"
">= [date]"
"<  [date]"
"<= [date]"
">< [date]"
"== [column]"
"!= [column]"
">  [column]"
"<  [column]"
">= [column]"
"<= [column]"
"contains"
"contains [string]i"
"not contains"
"not contains [string]i"
"regex"
"geoWithin"
"geoContains"
"in [string]"
"not in [string]"
"in [number]"
"not in [number]"
"in [date]"
"not in [date]"
"in [enum]"
"not in [enum]"
"array contains any [enum]"
"array contains none [enum]"
"array contains all [enum]"
"status no longer healthy"
"status changes"
"status becomes any of"
```

## Canonical Condition Group Variants

### AND (`&&`) between conditions

```json
{
  "mode": "&&",
  "conditions": [
    {"input": "id", "operator": ">  [number]", "num": 10},
    {"input": "id", "operator": "<  [number]", "num": 50}
  ]
}
```

### OR (`||`) between conditions

```json
{
  "mode": "||",
  "conditions": [
    {"input": "country", "operator": "contains", "string": "US"},
    {"input": "country", "operator": "contains", "string": "GB"}
  ]
}
```
