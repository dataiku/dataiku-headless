# ExtractNumbers

**When:** Extract numeric values out of free-text columns (e.g. pull every number from a description, optionally normalising "1.2k" → 1200).

**CLI shortcut:** `dku recipe add-step RECIPE --type ExtractNumbers --params '{"input":"description","output":"amounts","multipleValues":true,"replaceMultipliers":true,"extractToJson":true}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `input` | Yes | Source column |
| `output` | Yes | Output column |
| `multipleValues` | No | `true` returns ALL numbers concatenated by `delimiter`; `false` returns the first match only |
| `delimiter` | No | Separator for multiple values. Default `","` |
| `replaceMultipliers` | No | `true` parses `1.2k` → `1200`, `3M` → `3000000` |
| `extractToJson` | No | `true` emits a JSON array string instead of a delimiter-joined string |

```json
{"input": "description", "output": "amounts", "multipleValues": true, "replaceMultipliers": true, "extractToJson": true}
```
