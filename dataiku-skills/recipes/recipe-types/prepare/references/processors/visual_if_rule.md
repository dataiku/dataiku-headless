---
name: prepare-visual-if-rule
description: "Observed JSON patterns for the VisualIfRule prepare/shaker processor."
---

# VisualIfRule Processor

Create if / else-if / else branching logic to assign values or formulas into output columns.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `legacyPositioning` | yes | `boolean` | `true` \| `false` | UI/engine compatibility flag observed in payload envelope. |
| `visualIfDesc` | yes | `object` | Structured branching definition object | Contains `ifThen`, optional `elseIfThens`, and optional `elseActions`. |
| `visualIfDesc.ifThen` | yes | `object` | Branch object | Primary IF branch with `filter` and `actions`. |
| `visualIfDesc.elseIfThens` | no | `list<object>` | Any ordered list of branch objects | Additional ELSE IF branches evaluated in order. |
| `visualIfDesc.elseActions` | no | `list<object>` | Any ordered list of action objects | ELSE branch actions when no prior branch matches. |
| `*.filter` | yes (per branch) | `object` | DSS visual condition/filter object | Branch condition definition. Condition group/row schema (including `uiData.mode` with `&&` or `||`) is in [Visual conditions params](../../../references/visual_conditions_params.md). |
| `*.actions` | yes (per branch) | `list<object>` | DSS visual action objects | Output actions (for example `ASSIGN_VALUE`, formula-based assignment). |

### Visual Conditions Reference
Always read [Visual conditions params](../../../references/visual_conditions_params.md) to build `*.filter.uiData.conditions[]`.

## Canonical Variants

```json
{
  "type": "VisualIfRule",
  "params": {
    "legacyPositioning": false,
    "visualIfDesc": {
      "ifThen": {
        "filter": {
          "uiData": {
            "mode": "&&",
            "conditions": [
              {
                "input": "id",
                "col": "full_name",
                "num": 30.0,
                "items": [],
                "operator": ">  [number]",
                "num2": 0.0
              }
            ]
          },
          "distinct": true,
          "enabled": true
        },
        "actions": [
          {
            "outputColumnName": "new_column_1",
            "column": "id",
            "formula": "",
            "value": "id_above_30",
            "operator": "ASSIGN_VALUE"
          }
        ]
      },
      "elseIfThens": [
        {
          "filter": {
            "uiData": {
              "mode": "&&",
              "conditions": [
                {
                  "input": "id",
                  "col": "full_name",
                  "num": 20.0,
                  "operator": ">  [number]",
                  "num2": 0.0
                }
              ]
            },
            "distinct": true,
            "enabled": true
          },
          "actions": [
            {
              "outputColumnName": "new_column_1",
              "column": "id",
              "formula": "",
              "value": "id_20_to_30",
              "operator": "ASSIGN_VALUE"
            }
          ]
        }
      ],
      "elseActions": [
        {
          "outputColumnName": "new_column_1",
          "column": "id",
          "formula": "",
          "value": "id_below_20",
          "operator": "ASSIGN_VALUE"
        }
      ]
    }
  }
}
```

### OR (`||`) condition group in IF branch

```json
{
  "type": "VisualIfRule",
  "params": {
    "legacyPositioning": false,
    "visualIfDesc": {
      "ifThen": {
        "filter": {
          "uiData": {
            "mode": "||",
            "conditions": [
              {
                "input": "country",
                "operator": "contains",
                "string": "US"
              },
              {
                "input": "country",
                "operator": "contains",
                "string": "GB"
              }
            ]
          },
          "distinct": true,
          "enabled": true
        },
        "actions": [
          {
            "outputColumnName": "country_us_gb",
            "value": "yes",
            "operator": "ASSIGN_VALUE"
          }
        ]
      },
      "elseIfThens": [],
      "elseActions": [
        {
          "outputColumnName": "country_us_gb",
          "value": "no",
          "operator": "ASSIGN_VALUE"
        }
      ]
    }
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `VisualIfRule`.
3. Preserve branch order in `elseIfThens` because evaluation is sequential.
4. Keep action payload fields (`operator`, `outputColumnName`, `value`/`formula`) coherent per action type.
5. Revalidate downstream logic whenever branch conditions or output column names change.

## References

- Dataiku DSS: Create if-then-else statements (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/create-if-then-else.html
