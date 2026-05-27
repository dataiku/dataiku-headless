# Parameters Reference

Use this entrypoint to choose the right parameter reference.

## Common Parameter Shape

```json
{
  "name": "param_name",
  "label": "Human label",
  "type": "STRING",
  "mandatory": true,
  "description": "Shown in the DSS form"
}
```

## Split References

| Need | Read |
|---|---|
| Basic, list, selection, object, DSS object, AI, special parameter types | `parameters-types.md` |
| Dynamic params, Python setup scripts, service-layer helpers, reload behavior | `parameters-dynamic.md` |
| Accessing values from recipes, connectors, macros, webapps, R | `parameters-access.md` |

## Common Fields

| Field | Purpose |
|---|---|
| `name` | Stable machine-readable key used in config |
| `label` | Human-readable UI label |
| `type` | Parameter type enum |
| `mandatory` | Whether DSS requires a value |
| `description` | Help text shown in DSS |
| `defaultValue` | Default value |
| `visibilityCondition` | Conditional display expression |
