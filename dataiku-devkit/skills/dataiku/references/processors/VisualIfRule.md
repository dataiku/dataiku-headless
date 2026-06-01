# VisualIfRule

**When:** If/then/else branching logic. For multiple branches, prefer over nested GREL `if()`.

**CLI shortcut:** `dku recipe add-step RECIPE --type VisualIfRule --params '{"legacyPositioning":false,"visualIfDesc":...}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `legacyPositioning` | Yes | Always `false` for new steps |
| `visualIfDesc.ifThen` | Yes | Primary IF branch: `{filter, actions}` |
| `visualIfDesc.elseIfThens` | No | Additional ELSE IF branches (array) |
| `visualIfDesc.elseActions` | No | ELSE actions (array) |

**Condition operators:**

| Category | Operator string | Value field |
|----------|----------------|-------------|
| Empty/defined | `is empty` / `not empty` | — |
| String | `== [string]` / `!= [string]` / `contains` / `not contains` | `string` |
| Number | `== [number]` / `!= [number]` / `>  [number]` / `<  [number]` / `>= [number]` / `<= [number]` | `num` |
| Column compare | `== [column]` | `col` (other column name, NOT `string`) |
| Boolean | `true` / `false` | — |

**Action operators:**

| Operator | Field used |
|----------|------------|
| `ASSIGN_VALUE` | `value` |
| `ASSIGN_COLUMN` | `column` |
| `ASSIGN_FORMULA` | `formula` (GREL expression) |

```json
{
  "legacyPositioning": false,
  "visualIfDesc": {
    "ifThen": {
      "filter": {"uiData": {"mode": "&&", "conditions": [{"input": "amount", "col": "amount", "string": "", "num": 200.0, "items": [], "operator": ">= [number]", "num2": 0.0}]}, "distinct": true, "enabled": true},
      "actions": [{"outputColumnName": "tier", "column": "", "formula": "", "value": "HIGH", "operator": "ASSIGN_VALUE"}]
    },
    "elseIfThens": [
      {
        "filter": {"uiData": {"mode": "&&", "conditions": [{"input": "amount", "col": "amount", "string": "", "num": 100.0, "items": [], "operator": ">  [number]", "num2": 0.0}]}, "distinct": true, "enabled": true},
        "actions": [{"outputColumnName": "tier", "column": "", "formula": "", "value": "MEDIUM", "operator": "ASSIGN_VALUE"}]
      }
    ],
    "elseActions": [{"outputColumnName": "tier", "column": "", "formula": "", "value": "LOW", "operator": "ASSIGN_VALUE"}]
  }
}
```
