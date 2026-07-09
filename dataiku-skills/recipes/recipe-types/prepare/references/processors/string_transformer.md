---
name: prepare-string-transformer
description: "Observed JSON patterns for the StringTransformer prepare/shaker processor."
---

# StringTransformer Processor

Apply single in-place string transformation (case change, trim, URL/XML/Unicode (un)escaping, normalization, truncation) to one+ text columns. SQL pushdown only for `TO_UPPER`/`TO_LOWER` (or any non-`TRUNCATE` mode on Snowflake-with-UDF connections); other modes=DSS/Spark engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `TO_UPPER` \| `TO_LOWER` \| `URL_ENCODE` \| `URL_DECODE` \| `XML_ESCAPE` \| `XML_UNESCAPE` \| `UNICODE_ENCODE` \| `UNICODE_DECODE` \| `UNICODE_DECODE_4_DIGITS_ONLY` \| `TRIM` \| `CAPITALIZE` \| `CAPITALIZE_FULLY` \| `NORMALIZE` \| `NORMALIZE_SQLLIKE` \| `TRUNCATE` | In-place transform per affected column; null/empty cells skipped. |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `truncate_limit` | conditional | `integer` | `>= 0` | Leading chars to keep; required when `mode`=`TRUNCATE`. Default `0`. |

## Canonical Variants

### Uppercase a single column in place

```json
{
  "type": "StringTransformer",
  "params": {
    "mode": "TO_UPPER",
    "columns": ["free_text"],
    "appliesTo": "SINGLE_COLUMN"
  }
}
```

### Truncate selected columns to a fixed length

```json
{
  "type": "StringTransformer",
  "params": {
    "mode": "TRUNCATE",
    "truncate_limit": 32,
    "columns": ["free_text", "description"],
    "appliesTo": "COLUMNS"
  }
}
```
