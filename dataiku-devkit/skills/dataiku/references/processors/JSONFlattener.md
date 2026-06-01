# JSONFlattener

**When:** Flatten JSON object/array columns into separate columns.

**CLI shortcut:** `dku recipe add-step RECIPE --type JSONFlattener --params '{"inCol":"metadata","flattenArrays":false,"maxDepth":10,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Column containing JSON |
| `flattenArrays` | Yes | Also flatten arrays |
| `maxDepth` | Yes | Max nesting depth to flatten |
| `nullAsEmpty` | Yes | Treat null as empty string |
| `prefixOutputs` | Yes | Prefix output columns with path |
| `separator` | Yes | Separator between nested keys (e.g. `"_"`) |

```json
{"inCol": "metadata", "flattenArrays": false, "maxDepth": 10, "nullAsEmpty": true, "prefixOutputs": true, "separator": "_"}
```
