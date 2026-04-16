# Workflow Steps and Signoff Configurations

The workflow of a blueprint version is an ordered list of **steps**. Each step may have a **signoff configuration** that gates moving past it. This doc is the authoritative reference for the JSON shapes.

## Workflow definition

```json
"workflowDefinition": {
  "stepDefinitions": [
    { "id": "draft",    "name": "Draft",    "displaySignoffAfterView": false },
    { "id": "review",   "name": "Review",   "displaySignoffAfterView": false },
    { "id": "approved", "name": "Approved", "displaySignoffAfterView": false }
  ]
}
```

| Key | Type | Purpose |
|---|---|---|
| `id` | string | **Stable key.** Signoff configs reference this. Once referenced, do not rename without recreating the signoff |
| `name` | string | User-facing step label |
| `displaySignoffAfterView` | bool | UI detail — if `true`, signoff panel appears below the main view; if `false` (default), above |
| `visibilityCondition` | object (optional) | Hides the step based on artifact filter. Used to skip steps for artifacts that don't need them |
| `analysisDefinition` | object (optional) | Step-level computed analysis hooks — rare |

**Step ordering is the list order.** Users advance through steps in sequence. There is no branching.

### Visibility conditions

A `visibilityCondition` is an `ArtifactFilter` — the same filter shape used for searching artifacts. The most common usage hides a step when a field has a particular value:

```json
{
  "id": "detailed_review",
  "name": "Detailed review",
  "visibilityCondition": {
    "type": "field",
    "fieldId": "risk_level",
    "comparator": "EQUALS",
    "value": "High"
  }
}
```

**Important (from Govern docs):** If a mandatory signoff is defined on a step that is hidden when the workflow advances, the mandatory signoff is **bypassed silently**. A warning shows but the workflow is not blocked. If the step later becomes visible again, the mandatory signoff becomes enforced once more.

## Signoff configuration

Created per workflow step via `create-signoff-config` or edited via `set-signoff-config`.

### Canonical payload

```json
{
  "title": "Review gate",
  "description": "Business review before moving to Approved",
  "mandatory": true,
  "feedbackUsersGroups": [
    {
      "id": "business_reviewers",
      "title": "Business Reviewers",
      "users": [
        { "usersContainer": { "type": "user", "login": "alice" } },
        { "usersContainer": { "type": "user", "login": "bob" } }
      ]
    },
    {
      "id": "legal_reviewers",
      "title": "Legal Reviewers",
      "users": [
        { "usersContainer": { "type": "group", "groupName": "legal_team" } }
      ]
    }
  ],
  "approvers": [
    { "usersContainer": { "type": "user", "login": "cathy" } }
  ],
  "recurrenceConfiguration": {
    "activated": false,
    "days": 0, "weeks": 0, "months": 0, "years": 0,
    "reloadConf": false
  }
}
```

### Fields

| Key | Type | Required | Purpose |
|---|---|---|---|
| `title` | string | yes | Human-readable signoff name (e.g. "Risk Review") |
| `description` | string | no | Shown next to the title |
| `mandatory` | bool | no (default `true`) | Must the signoff be approved before advancing to the next step? |
| `feedbackUsersGroups` | array | yes (may be empty) | Reviewers grouped by role. Each group must have `id`, `title`, `users[]` |
| `approvers` | array | yes (may be empty) | Final approvers — each is a `SignoffUser` with a `usersContainer` |
| `recurrenceConfiguration` | object | yes | Reset schedule for an approved signoff |
| `id` | object | **NO** on create | Server assigns from URL path on POST. Stripped defensively by the CLI |

### `feedbackUsersGroups[]` entry

```json
{
  "id": "business_reviewers",       // stable group key — used by `dku govern signoff add-feedback --group-id`
  "title": "Business Reviewers",    // display label (required — server rejects empty)
  "users": [
    { "usersContainer": { "type": "user", "login": "alice" } }
  ]
}
```

Both `id` and `title` are required. The `id` is referenced in runtime signoff commands (`add-feedback --group-id business_reviewers`, `delegate-feedback --group-id ...`).

### `usersContainer` types

**All type values are lowercase.** The Java enum is `UsersContainer` with JsonTypeId discriminators.

| type | Extra fields | Meaning |
|---|---|---|
| `"user"` | `"login": "alice"` | A single DSS user |
| `"group"` | `"groupName": "legal_team"` | All members of a Govern group |
| `"role"` | `"roleId": "ro.reviewer"` | All users assigned a given role |
| `"global-api-key"` | `"keyId": "api:..."` | A specific global API key identity |

Passing `"USER"` or `"SINGLE_USER"` produces: `Could not parse a SignoffConfiguration from request body, caused by: JsonParseException: Cannot deserialize UsersContainer: unknown type "USER" ... (possible type values are: "role", "global-api-key", "user", "group")`

### `approvers[]` entry

Approvers have the **same `usersContainer` shape** as feedback users, but are not grouped (they're a flat list). On update, the server auto-stamps `addedBy` and `addedOn`:

```json
{
  "addedBy": "api:JZDTbzNpsBg5y6OC",        // server-stamped, do not set on create
  "addedOn": "2026-04-12T18:07:41.398625Z", // server-stamped
  "usersContainer": { "type": "user", "login": "bob" }
}
```

You can omit `addedBy` / `addedOn` on both create and update — the server will fill them. Round-tripped `get-signoff-config` JSON will contain them; leaving them in is harmless for `set-signoff-config`.

### `recurrenceConfiguration`

Automatically resets an approved signoff after a period so it must be re-approved. Four independent interval fields that sum:

```json
{
  "activated": true,
  "days":   0,
  "weeks":  0,
  "months": 6,
  "years":  0,
  "reloadConf": false
}
```

- `activated: false` disables recurrence entirely (default)
- Sum of intervals > 0 required when `activated: true`
- `reloadConf`: when `true`, reset also reloads the full signoff config from the blueprint (picks up any reviewer changes made since the last approval)

## End-to-end example: wiring a two-stage review

```bash
# 1. Define the workflow in the version definition
cat > bv.json <<'EOF'
{
  ...existing fields...
  "workflowDefinition": {
    "stepDefinitions": [
      {"id": "draft",    "name": "Draft",    "displaySignoffAfterView": false},
      {"id": "business_review", "name": "Business Review", "displaySignoffAfterView": false},
      {"id": "legal_review",    "name": "Legal Review",    "displaySignoffAfterView": false},
      {"id": "approved", "name": "Approved", "displaySignoffAfterView": false}
    ]
  },
  "uiDefinition": {
    ...existing views — keep them, do NOT ship empty (see ui-views.md)...
    "uiStepDefinitions": {
      "draft":            {"viewId": "main"},
      "business_review":  {"viewId": "main"},
      "legal_review":     {"viewId": "main"},
      "approved":         {"viewId": "main"}
    },
    "artifactPageViewId": "main"
  }
}
EOF
dku govern blueprint set-version-definition bp.my_bp bv.v1 --definition @bv.json

# 2. Wire a signoff on each review step
cat > business_signoff.json <<'EOF'
{
  "title": "Business Review",
  "mandatory": true,
  "feedbackUsersGroups": [
    {
      "id": "business",
      "title": "Business Stakeholders",
      "users": [
        {"usersContainer": {"type": "group", "groupName": "product_owners"}}
      ]
    }
  ],
  "approvers": [
    {"usersContainer": {"type": "user", "login": "head_of_product"}}
  ],
  "recurrenceConfiguration": {"activated": false, "days": 0, "weeks": 0, "months": 0, "years": 0, "reloadConf": false}
}
EOF
dku govern blueprint create-signoff-config bp.my_bp bv.v1 business_review --definition @business_signoff.json

cat > legal_signoff.json <<'EOF'
{
  "title": "Legal Review",
  "mandatory": true,
  "feedbackUsersGroups": [
    {
      "id": "legal",
      "title": "Legal Team",
      "users": [
        {"usersContainer": {"type": "group", "groupName": "legal_team"}}
      ]
    }
  ],
  "approvers": [
    {"usersContainer": {"type": "role", "roleId": "ro.compliance_officer"}}
  ],
  "recurrenceConfiguration": {"activated": true, "days": 0, "weeks": 0, "months": 12, "years": 0, "reloadConf": false}
}
EOF
dku govern blueprint create-signoff-config bp.my_bp bv.v1 legal_review --definition @legal_signoff.json

# 3. Activate
dku govern blueprint set-version-status bp.my_bp bv.v1 ACTIVE
```

## Reference-based reviewers (dynamic per-artifact)

A common pattern: put a REFERENCE field on the artifact (e.g. `reviewers_business`) and use `"type": "FIELD"` in the signoff's users container to dynamically resolve reviewers from that field. This is covered in advanced Govern docs; note that `FIELD` is **uppercase** in this specific case and only valid in signoff configurations (not for artifact field values). Confirm with `bp.system.govern_project/bv.system.default` → `signoff_reviewers_business` field + any signoff config referencing it for a live example.

## Migration from older blueprint versions

Changing signoff configurations mid-lifecycle is safe: existing open signoffs continue to use their snapshotted config; new signoffs use the updated one. To force existing signoffs to reload: set `recurrenceConfiguration.reloadConf = true` and trigger a manual reset.
