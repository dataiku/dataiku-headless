---
name: prepare-json-flattener
description: "Observed JSON patterns for the JSONFlattener prepare/shaker processor."
---

# JSONFlattener Processor

Unnest, or flatten, JSON objects or arrays. By default, arrays are kept untouched.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input column name | Column containing JSON object content to flatten. |
| `flattenArrays` | yes | `boolean` | `true` \| `false` | Whether arrays in JSON are also flattened. |
| `maxDepth` | yes | `integer` | Any positive integer | Maximum flattening depth. |
| `nullAsEmpty` | yes | `boolean` | `true` \| `false` | Whether null values are treated as empty. |
| `prefixOutputs` | yes | `boolean` | `true` \| `false` | Whether output columns are prefixed by input path. |
| `separator` | yes | `string<any>` | Any text string (including empty string) | Separator between nested keys in generated column names. |

## Canonical Variants

### Flatten object fields without flattening arrays

```json
{
  "type": "JSONFlattener",
  "params": {
    "inCol": "metadata",
    "flattenArrays": false,
    "maxDepth": 10,
    "nullAsEmpty": true,
    "prefixOutputs": true,
    "separator": "_"
  }
}
```

### Flatten object fields and arrays

```json
{
  "type": "JSONFlattener",
  "params": {
    "inCol": "metadata",
    "flattenArrays": true,
    "maxDepth": 5,
    "nullAsEmpty": false,
    "prefixOutputs": false,
    "separator": ""
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `JSONFlattener`.
3. Keep `maxDepth`, `flattenArrays`, and `prefixOutputs` aligned with the desired output schema.
4. Choose `separator` and `prefixOutputs` intentionally to avoid output column-name collisions.
