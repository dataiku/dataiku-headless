---
name: prepare-split-into-chunks
description: "Observed JSON patterns for the SplitIntoChunks prepare/shaker processor."
---

# SplitIntoChunks Processor

Split long free-text column into overlapping character-bounded chunks; one output row per chunk. Not SQL-translatable: always DSS engine (Snowflake-targeted recipe falls back to DSS). Multiplies row count, copying all other columns onto each chunk row.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any existing text column name | Input text column to split. Throws if blank; empty/blank cell values produce no output rows. |
| `outCol` | yes | `string<column_name>` | Any valid output column name | Output column receiving each chunk. Throws if blank. |
| `chunkIdCol` | no | `string<column_name>` | Any valid output column name | Optional column holding 0-based chunk index per source row. |
| `separators` | yes | `list<object<{value:string<any>,isDefault:boolean,description:string<any>,enabled:boolean}>>` | List of separators; see `` `separators[]` Matrix `` below | Ordered, applied sequentially (recursive). At least one enabled; all enabled `value`s distinct. |
| `chunkSize` | yes | `integer` | `> 0` | Max chars per chunk. Default `4000`. Throws if `<= 0`. |
| `chunkOverlap` | yes | `integer` | `>= 0` and `< chunkSize` | Chars overlapping between consecutive chunks. Default `200`. Throws if `>= chunkSize`. |
| `keepSeparator` | no | `boolean` | `true` \| `false` | Keep separators in output chunks (kept on right side of split). Default `true`. |
| `isRegex` | no | `boolean` | `true` \| `false` | Treat separator `value`s as regex instead of literal strings. Default `false`. |
| `stripWhitespace` | no | `boolean` | `true` \| `false` | Strip surrounding whitespace from each chunk (empty chunks dropped). Default `true`. |

## `separators[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `value` | yes | `string<any>` | Separator string (regex when `isRegex`=`true`). |
| `isDefault` | yes | `boolean` | Marks built-in default separator. |
| `description` | yes | `string<any>` | Human-readable label. |
| `enabled` | yes | `boolean` | Whether separator participates in splitting. |

## Canonical Variant

```json
{
  "type": "SplitIntoChunks",
  "params": {
    "inCol": "free_text",
    "outCol": "free_text_chunk",
    "chunkIdCol": "free_text_chunk_id",
    "separators": [
      {"value": "\n\n", "isDefault": true, "description": "Double new lines", "enabled": true},
      {"value": "\n", "isDefault": true, "description": "New Lines", "enabled": true},
      {"value": " ", "isDefault": true, "description": "Spaces", "enabled": true},
      {"value": "", "isDefault": true, "description": "Each character", "enabled": true}
    ],
    "chunkSize": 20,
    "chunkOverlap": 5,
    "keepSeparator": true,
    "isRegex": false,
    "stripWhitespace": true
  }
}
```
