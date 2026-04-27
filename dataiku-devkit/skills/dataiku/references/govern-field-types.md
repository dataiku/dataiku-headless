# Govern Blueprint Field Types

Exhaustive catalogue of the 9 `fieldType` values accepted in `fieldDefinitions`. Sourced from the Govern backend (`com.dataiku.gh.core.models.fields.FieldType`) and verified against the live `bp.system.govern_project/bv.system.default` payload.

## Common envelope (all field types)

```json
{
  "label": "Human-readable label",
  "description": "Optional tooltip shown next to the label",
  "fieldType": "<ONE OF 9 TYPES BELOW>",
  "sourceType": "STORE",
  "required": false
}
```

Optional common keys:

| Key | Shape | Purpose |
|---|---|---|
| `listConfig` | `{}` or `{"cardinalityMin": N, "cardinalityMax": M}` | Presence (even empty) marks field as a list. Cardinality bounds optional |
| `analysisDefinition` | object | Used for computed fields and some UI hints |
| `documentation` | HTML string | Inline docs (shown under the field in the form) |

**`sourceType` values:**
- `STORE` — user-set. Agents almost always use this.
- `COMPUTE` — auto-calculated (computed from other fields via analysis logic). Agents should not author these unless the user explicitly asks for a computed field — the GUI can't edit them and the schema has extra required keys (`computationType`, `analysisDefinition`).

## TEXT — free-text string

```json
{
  "label": "Description",
  "fieldType": "TEXT",
  "sourceType": "STORE",
  "required": false
}
```

**Artifact value:** any string.
**List form:** `"listConfig": {}` → value is `["a", "b"]`.

## NUMBER — integer or decimal

```json
{
  "label": "Cost estimate",
  "fieldType": "NUMBER",
  "sourceType": "STORE",
  "required": false
}
```

**Artifact value:** number literal (`42`, `3.14`).

## BOOLEAN — checkbox

```json
{
  "label": "Contains PII",
  "fieldType": "BOOLEAN",
  "sourceType": "STORE",
  "required": false
}
```

**Artifact value:** `true` / `false`.

## DATE — ISO 8601 datetime

```json
{
  "label": "Go-live date",
  "fieldType": "DATE",
  "sourceType": "STORE",
  "required": false
}
```

**Artifact value:** `"2026-06-01T00:00:00.000Z"` (must be a string in ISO 8601 with a timezone). Pitfalls: `"2026-06-01"` alone is rejected — include the time portion. `UTC` with `Z` suffix is the safest form.

## CATEGORY — constrained choice

```json
{
  "label": "Risk level",
  "fieldType": "CATEGORY",
  "sourceType": "STORE",
  "required": true,
  "categories": ["Low", "Medium", "High"]
}
```

`categories` is **required**. Values must match exactly (case-sensitive). Multi-select via `"listConfig": {}`.

Live example with multi-select:

```json
{
  "label": "Use case technical dimension",
  "description": "Technical use cases of the Govern Project",
  "fieldType": "CATEGORY",
  "sourceType": "STORE",
  "required": false,
  "categories": ["AI/ML", "Analytics", "LLM/GenAI"],
  "listConfig": {"cardinalityMin": 0}
}
```

## REFERENCE — link to another artifact

```json
{
  "label": "Owners",
  "fieldType": "REFERENCE",
  "sourceType": "STORE",
  "required": false,
  "allowedBlueprints": ["bp.system.user", "bp.system.group"],
  "listConfig": {}
}
```

`allowedBlueprints` constrains which blueprints the referenced artifact must be an instance of. Common choices:

| allowedBlueprints | Use case |
|---|---|
| `["bp.system.user"]` | Single-user owner |
| `["bp.system.user", "bp.system.group"]` | Owner that can be a user OR a group (typical for "reviewers" fields) |
| `["bp.system.business_initiative"]` | Parent-child: governed project linked to its business initiative |
| `["bp.system.govern_project"]` | Cross-linking between governed artifacts |

**Artifact value:** artifact ID like `"ar.123"`. Lists hold multiple IDs: `["ar.1", "ar.2"]`.

## UPLOADED_FILE — attached file

```json
{
  "label": "Supporting documents",
  "fieldType": "UPLOADED_FILE",
  "sourceType": "STORE",
  "required": false,
  "listConfig": {}
}
```

**Artifact value:** uploaded file ID (`"uf.1"`) — upload first via `dku govern file upload`, then set the field to the returned ID.

## TIME_SERIES — metrics graph

```json
{
  "label": "Drift metric",
  "fieldType": "TIME_SERIES",
  "sourceType": "STORE",
  "required": false
}
```

**Important:** TIME_SERIES fields cannot be edited from the GUI form. Values are written via the Public API (`dku govern time-series`) or from inside a hook. Used mainly for model metrics graphs on `bp.system.govern_model_version`.

## JSON — arbitrary JSON

```json
{
  "label": "Raw config",
  "fieldType": "JSON",
  "sourceType": "STORE",
  "required": false
}
```

**Artifact value:** any JSON value — object, array, number, string. The GUI provides a JSON editor; validation is syntactic only (no schema).

## List fields

Any field becomes a list by adding `listConfig`. The key is presence, not the contents:

```json
"listConfig": {}                               // list with any length
"listConfig": {"cardinalityMin": 1}            // at least 1
"listConfig": {"cardinalityMin": 1, "cardinalityMax": 5}  // 1 to 5
```

In the artifact payload, list fields **must** be JSON arrays, even for a single value:

```json
{"countries": ["France"]}    // ✓
{"countries": "France"}       // ✗ ignored silently
```

## Required vs. visible

`"required": true` is a **global** constraint: the field must be populated on every artifact regardless of what workflow step it's in and regardless of whether it's visible in any view. A field that's only shown on a later workflow step but is marked required will still block artifact creation if empty.

**If you want "required from step X onwards", do NOT set `required: true`.** Instead, use hooks or view-level validation (not covered here — check with an architect).

## Sample fields from `bp.system.govern_project/bv.system.default`

The real default Govern Project blueprint has 41 fields. A representative slice:

```json
{
  "description": {
    "label": "Description",
    "fieldType": "TEXT",
    "sourceType": "STORE",
    "required": false
  },
  "target_end_date": {
    "label": "Target end date",
    "fieldType": "DATE",
    "sourceType": "STORE",
    "required": false
  },
  "qualification_risk_rating": {
    "label": "Risk rating",
    "fieldType": "CATEGORY",
    "sourceType": "STORE",
    "required": false,
    "categories": ["Low", "Medium low", "Medium high", "High"],
    "analysisDefinition": { "...": "used for risk-score computation" }
  },
  "final_approvers": {
    "label": "Final approvers",
    "description": "List of people acting as Final approvers during sign-off",
    "fieldType": "REFERENCE",
    "sourceType": "STORE",
    "required": false,
    "allowedBlueprints": ["bp.system.user", "bp.system.group"],
    "listConfig": {"cardinalityMin": 0}
  },
  "delivery_docs": {
    "label": "Supporting documents",
    "fieldType": "UPLOADED_FILE",
    "sourceType": "STORE",
    "required": false,
    "listConfig": {"cardinalityMin": 0}
  }
}
```
