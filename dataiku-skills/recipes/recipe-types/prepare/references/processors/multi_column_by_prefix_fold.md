---
name: prepare-multi-column-by-prefix-fold
description: "Observed JSON patterns for the MultiColumnByPrefixFold prepare/shaker processor."
---

# MultiColumnByPrefixFold Processor

Fold every column whose name matches a regex into long form, emitting one row per non-empty matched column with captured column name and value in two new columns. DSS engine only (not SQL-translatable); despite the type name, matching is NOT a literal prefix: `columnNamePattern` is a full-string-anchored Java regex (`matches()`) that must match a column's ENTIRE name, and with a capture group `group(1)` is the fold name.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `columnNamePattern` | yes | `string<regex>` | A Java regular expression, optionally with one capture group | Columns whose NAME fully matches are folded. With a capture group, `group(1)` of column name is used as fold name instead of full name. Invalid regex throws at init. |
| `columnNameColumn` | yes | `string<any>` | Any valid new column name | New output column holding fold NAME (matched/captured column name). Created before first folded column. |
| `columnContentColumn` | yes | `string<any>` | Any valid new column name | New output column holding fold VALUE. Created before first folded column. |
| `foldRemoveFoldedColumns` | no | `boolean` | `true` \| `false` | `true`=matched folded columns deleted in post-processing. Form default `true`; null coerced to `false`. |

## Canonical Variant

```json
{
  "type": "MultiColumnByPrefixFold",
  "params": {
    "columnNamePattern": "(l..)",
    "columnNameColumn": "coord_name",
    "foldRemoveFoldedColumns": true,
    "columnContentColumn": "coord_value"
  }
}
```

`(l..)` matches the full 3-char names `lat`/`lng` only, folding both into `coord_name`/`coord_value` (8 rows → 16). A looser `(l.*)` would also match `log_line` (any full name starting with `l`), folding 3 columns — anchor the pattern to the exact set intended.
