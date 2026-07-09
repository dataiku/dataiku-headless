---
name: prepare-shared-scope-params
description: "Shared scope parameter semantics for prepare/shaker processors."
---

# Shared Scope Params

Use this reference for shared scope selection params reused across multiple prepare processors.

## Typing Notation

- `enum`: strict finite set of allowed values.
- `string<column_name>`: any valid column name from schema.
- `list<string<column_name>>`: list of valid column names.
- `string<regex>`: regex-like text pattern.

## Param Contract

| Param | Domain | Allowed values | Notes |
| --- | --- | --- | --- |
| `appliesTo` | `enum` | `SINGLE_COLUMN` \| `COLUMNS` \| `ALL` \| `PATTERN` | Controls how target columns are selected. |
| `columns` | `list<string<column_name>>` | Any valid list of column names (including `[]`) | Keep list shape consistent with `appliesTo`. |
| `appliesToPattern` | `string<regex>` (conditional) | Any valid regex-like pattern | Required when `appliesTo = PATTERN`; targets matching column names. |
