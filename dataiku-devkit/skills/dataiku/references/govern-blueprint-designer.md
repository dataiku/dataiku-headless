# Govern Blueprint Designer

Design Dataiku Govern blueprints — blueprint versions, fields, workflow steps, signoff configurations, logical hooks, and UI views. Read this reference when you need to create a governance template, fork an existing blueprint, add or change fields, wire signoffs, or move a version through DRAFT → ACTIVE → ARCHIVED. Pairs with `dku-cli` for command reference and `govern.md` (sibling reference) for runtime Govern concepts.

> **Cheat Sheet (read this first)**
>
> 1. **Blueprint ≠ version.** The blueprint entity only stores `name`, `icon`, `color`. Fields, workflow, hooks, views, signoffs all live on the **version**. `set-definition` edits the blueprint entity; `set-version-definition` edits everything else.
> 2. **Fork, do not start blank.** Pass `--from bv.system.default` (or another ACTIVE version) on `create-version`. System versions contain under-the-hood fields and workflow steps required for Govern to work. Only start blank if the user explicitly insists.
> 3. **New versions are DRAFT.** After `create-version` (and after editing), the version is DRAFT and cannot be applied to artifacts. Activate with `set-version-status BP_ID VERSION_ID ACTIVE`. The authoring loop ends with activation.
> 4. **`get-version → edit JSON → set-version-definition` is the idiomatic loop.** Don't try to patch fields individually — there is no add-field command. Round-trip the full JSON.
> 5. **`--force` (dangerZoneAccepted) may destroy data.** If the version has existing artifacts and your edit removes a field or changes its type, the server blocks the save. Re-running with `--force` silently discards that field's data in every artifact. Never use `--force` without the user's explicit go-ahead; prefer creating a new version and migrating.
> 6. **Workflow step IDs are stable keys.** Signoff configurations are keyed on `stepId` — rename a step and the signoff config orphans. Delete the signoff first, rename, recreate.
> 7. **Signoff user types are lowercase.** `"type": "user"` / `"group"` / `"role"` / `"global-api-key"` — NOT `"USER"` / `"SINGLE_USER"`. Server rejection message: `unknown type "USER"`.
> 8. **Signoff create body must not contain `id`.** The server assigns it from the URL path. The CLI strips it defensively, but the JSON you author should omit it.
> 9. **Every field needs `fieldType` + `sourceType`.** `sourceType` is `STORE` (user-set) or `COMPUTE` (auto-calculated — ignore unless you're writing a computed field, which agents should almost never do). Categories need `categories[]`, references need `allowedBlueprints[]`, lists need `"listConfig": {}` (empty object is enough to mark it a list).
> 10. **Hooks run before commit.** Never mutate other artifacts from a hook via the API client — use `handler.artifactIdsToUpdate.append(id)` instead. Mutating external items from a hook may fail the initial action and is explicitly unsupported.
> 11. **Native Govern built-ins before scenarios or external scripts.** Derived field values → **logical hook** on CREATE/UPDATE (not a DSS scenario, not a webhook, not external CI). Validation / save-blocking → **logical hook** with `handler.fail("reason")` (not a separate validation pipeline). Approval gates → **signoff configuration** (not a custom script polling the API). User-triggered side effects → **custom action** on the artifact page (not an external REST endpoint). Only reach for scenarios, webhooks, or external code when the logic truly lives outside the artifact lifecycle. This is the Govern analog of "visual recipes before Python" — the built-ins exist because they compose cleanly with the workflow engine.

# govern-blueprint-designer

A Govern **blueprint** is a container; a **blueprint version** is the actual template applied to artifacts. Designing a blueprint means designing its versions: what fields users see, what workflow steps they progress through, what signoffs gate those steps, what Python hooks fire on create/update/delete, and how the UI lays out views.

This skill teaches agents to use the `dku govern blueprint` CLI to author and maintain blueprint versions end-to-end.

## Mental model

```
Blueprint  bp.<id>          ← icon, name, color only
 └── Version  bv.<id>       ← DRAFT | ACTIVE | ARCHIVED
      ├── fieldDefinitions  ← 9 FieldTypes × 2 sourceTypes (STORE/COMPUTE)
      ├── workflowDefinition.stepDefinitions[]   ← ordered lifecycle steps
      │    └── SignoffConfiguration (per step)   ← reviewers + approvers
      ├── logicalHookList[]   ← Python scripts on CREATE/UPDATE/DELETE
      ├── actions{}           ← Python buttons users can trigger
      ├── uiDefinition        ← views + per-step view assignments
      ├── hierarchicalParentFieldId   ← parent artifact for breadcrumbs
      └── instructions        ← admin-facing authoring notes
```

A blueprint can carry multiple versions simultaneously (e.g. `bv.v1` ACTIVE, `bv.v2` DRAFT under development, `bv.v0` ARCHIVED). **Only ACTIVE versions can be applied to new artifacts.**

## Authoring loop (canonical)

```bash
# 1. Fork from an existing ACTIVE version
dku govern blueprint create-version bp.my_bp v1 \
  --name "Version 1" \
  --from bv.system.default

# 2. Dump the draft definition to a working file
dku govern blueprint get-version bp.my_bp bv.v1 -o json > bv.json

# 3. Edit bv.json — add fields, tweak workflow, wire uiDefinition, etc
$EDITOR bv.json

# 4. Save the edited definition back
dku govern blueprint set-version-definition bp.my_bp bv.v1 --definition @bv.json

# 5. Wire a signoff on any workflow step that needs approval
dku govern blueprint create-signoff-config bp.my_bp bv.v1 review \
  --definition @signoff.json

# 6. Activate — only now can artifacts use this version
dku govern blueprint set-version-status bp.my_bp bv.v1 ACTIVE

# 7. Later: retire
dku govern blueprint set-version-status bp.my_bp bv.v1 ARCHIVED
```

**Do not skip activation.** A DRAFT version is invisible to normal users and cannot host artifacts.

## Creating a brand-new blueprint

```bash
# 1. Create the blueprint entity (name/icon/color only)
dku govern blueprint create my_bp --definition '{
  "name": "My Blueprint",
  "icon": "science",
  "color": "#da7f15",
  "backgroundColor": "#fce4c7"
}'

# 2. Create the first version — fork from the closest system blueprint
dku govern blueprint create-version bp.my_bp v1 --from bv.system.default

# 3. ... continue the authoring loop above
```

## Command reference

### Discovery

```bash
dku govern blueprint list                                   # all blueprints
dku govern blueprint get BP_ID                              # blueprint entity
dku govern blueprint list-versions BP_ID                    # all versions (DRAFT + ACTIVE + ARCHIVED)
dku govern blueprint get-version BP_ID VER_ID               # full version definition
dku govern blueprint fields BP_ID [--version VER]           # field schema (scannable)
dku govern blueprint version-status BP_ID VER_ID            # DRAFT / ACTIVE / ARCHIVED
dku govern blueprint list-signoff-configs BP_ID VER_ID      # wired signoffs
dku govern blueprint get-signoff-config BP_ID VER_ID STEP   # one signoff
```

### Authoring (admin only)

```bash
dku govern blueprint create ID --definition JSON
dku govern blueprint set-definition BP_ID --definition JSON             # name/icon/color

dku govern blueprint create-version BP_ID NEW_ID [--name N] [--from VER]
dku govern blueprint set-version-definition BP_ID VER_ID --definition JSON [--force]
dku govern blueprint set-version-status BP_ID VER_ID {DRAFT|ACTIVE|ARCHIVED}

dku govern blueprint create-signoff-config BP_ID VER_ID STEP_ID --definition JSON
dku govern blueprint set-signoff-config    BP_ID VER_ID STEP_ID --definition JSON
```

### Destructive (require `--confirm`)

```bash
dku govern blueprint delete BP_ID --confirm                               # all versions must be gone first
dku govern blueprint delete-version BP_ID VER_ID --confirm                # all artifacts must be gone first
dku govern blueprint delete-signoff-config BP_ID VER_ID STEP_ID --confirm
```

### Fork across instances (export / import)

```bash
# Source instance — produce an envelope containing version def + trace + signoffs
dku govern blueprint export-version BP_ID VER_ID -o json > bv_export.json

# Target instance — the target blueprint must already exist
dku govern blueprint create BP_ID --definition '{"name": "..."}'            # if not already
dku govern blueprint import-version BP_ID --definition @bv_export.json \
    [--ignore-origin-errors] \
    [--signoff-roles ALL|EXISTING|NONE] \
    [--migration-behavior FAIL_IMPORT_ON_EXISTING_MIGRATION_OR_MISSING_VERSION|...]
dku govern blueprint set-version-status BP_ID VER_ID ACTIVE                # imported versions land in DRAFT
```

`--signoff-roles` controls only the **role** validation strictness on import (user/group/api-key validation is hardcoded to NONE by the server and always drops those reviewers — see below):
- `ALL` (default) — every role referenced in signoff configs must exist on the target. Fails loudly on missing roles.
- `EXISTING` — keep existing role references, silently drop missing ones.
- `NONE` — skip role validation entirely and drop every role reviewer too.

**Hard Govern limitation: only role-based reviewers survive export → import.** The import endpoint hardcodes `forUsers=NONE, forGroups=NONE, forApiKeys=NONE`, and NONE in Govern means "drop the entire collection" (not "skip validation and keep"). User/group/api-key reviewers in an exported envelope are always stripped on import. The CLI's `export-version` applies the same filter by default so the envelope you get is round-trip-safe; if you need to hand-edit logins before importing, pass `--keep-non-role-users` on export.

**Workaround for cross-instance forks that depend on concrete users:** define a Govern **role** (`dku govern role create`) containing the reviewers, then reference the role in the signoff config. Roles survive the round-trip.

Export omits migration paths. If you need them, use the Govern UI today. The `--migration-behavior` flag is reserved for envelopes that happen to contain them (e.g. re-importing a UI-authored export).

## Field types at a glance

Nine types — see [govern-blueprint-designer/field-types.md](govern-blueprint-designer/field-types.md) for full JSON.

| fieldType | Scalar JSON | List JSON |
|---|---|---|
| `TEXT` | `"hello"` | `["a","b"]` |
| `NUMBER` | `42` | `[1,2,3]` |
| `BOOLEAN` | `true` | `[true,false]` |
| `DATE` | `"2026-06-01T00:00:00.000Z"` (ISO 8601) | array of ISO 8601 |
| `CATEGORY` | `"High"` (from `categories`) | `["EU","US"]` |
| `REFERENCE` | `"ar.123"` (artifact ID) | `["ar.1","ar.2"]` |
| `UPLOADED_FILE` | `"uf.1"` | `["uf.1","uf.2"]` |
| `TIME_SERIES` | field is set via API/hooks only, not GUI | same |
| `JSON` | any JSON value | list of values |

**Every field definition has:** `label`, `fieldType`, `sourceType` (`STORE` or `COMPUTE`), `required` (bool). Plus:

- `CATEGORY` → `categories: [...]`
- `REFERENCE` → `allowedBlueprints: ["bp.system.user", ...]`
- Any list field → `listConfig: {}` (empty object marks it as a list; add `cardinalityMin` / `cardinalityMax` to constrain length)
- Optional `description` (tooltip), `analysisDefinition` (for computed fields)

```json
{
  "risk_level": {
    "label": "Risk level",
    "fieldType": "CATEGORY",
    "sourceType": "STORE",
    "required": true,
    "categories": ["Low", "Medium", "High"]
  },
  "owners": {
    "label": "Owners",
    "fieldType": "REFERENCE",
    "sourceType": "STORE",
    "required": false,
    "allowedBlueprints": ["bp.system.user", "bp.system.group"],
    "listConfig": {}
  }
}
```

## Workflow + signoff configuration

Workflow steps are an ordered list:

```json
"workflowDefinition": {
  "stepDefinitions": [
    { "id": "draft",    "name": "Draft",    "displaySignoffAfterView": false },
    { "id": "review",   "name": "Review",   "displaySignoffAfterView": false },
    { "id": "approved", "name": "Approved", "displaySignoffAfterView": false }
  ]
}
```

Step `id` values are **stable keys** — signoff configurations reference them. Optional `visibilityCondition` can hide a step based on field values.

A signoff configuration is created on a specific step. The minimal payload accepted by `create-signoff-config`:

```json
{
  "title": "Review gate",
  "description": "Business review before moving to Approved",
  "mandatory": true,
  "feedbackUsersGroups": [
    {
      "id": "reviewers",
      "title": "Reviewers",
      "users": [
        { "usersContainer": { "type": "user", "login": "alice" } }
      ]
    }
  ],
  "approvers": [
    { "usersContainer": { "type": "user", "login": "bob" } }
  ],
  "recurrenceConfiguration": {
    "activated": false,
    "days": 0, "weeks": 0, "months": 0, "years": 0,
    "reloadConf": false
  }
}
```

**Do not set `id` in the body** — the server builds it from the URL path and rejects requests that include it. The CLI strips it defensively, but your JSON should omit it.

`usersContainer.type` is **lowercase**: `"user"`, `"group"`, `"role"`, `"global-api-key"`. Passing `"USER"` produces:

```
Could not parse a SignoffConfiguration from request body,
caused by: JsonParseException: Cannot deserialize UsersContainer:
unknown type "USER" ... (possible type values are: "role", "global-api-key", "user", "group")
```

See [govern-blueprint-designer/workflow-and-signoffs.md](govern-blueprint-designer/workflow-and-signoffs.md) for more container types and recurrence patterns.

## Logical hooks

Python scripts that run on artifact lifecycle phases (CREATE / UPDATE / DELETE). Added as entries in `logicalHookList[]`:

```json
{
  "name": "Compute risk score",
  "description": "Derive risk_score from risk_level",
  "phases": ["CREATE", "UPDATE"],
  "script": "from govern.core.handler import get_handler\nhandler = get_handler()\nartifact = handler.artifact\nlevel = artifact.fields.get('risk_level')\nartifact.fields['risk_score'] = {'Low': 20, 'Medium': 50, 'High': 80}.get(level)\n"
}
```

**Hook safety rules** (Govern docs warning, verbatim):
- Hooks run **before** the initial action is committed. The action may still fail after the hook runs.
- Do **not** mutate neighbor artifacts via the API client from inside a hook — it may trigger another hook execution, which is unsupported and fails the action.
- To schedule updates on neighbor artifacts, append their IDs to `handler.artifactIdsToUpdate` and they will be UPDATE-hooked **after** the current action commits.

See [govern-blueprint-designer/hooks-and-actions.md](govern-blueprint-designer/hooks-and-actions.md) for the `handler` object API and common hook patterns.

## UI views (minimum viable)

> ⚠️ **Empty `views` does NOT auto-render fields.** Govern silently accepts `"views": {}` and `"viewId": ""` with no error, but the resulting artifact page is **blank** — verified empirically on DSS/Govern 14.5. You **must** declare at least one view that explicitly references your fields, otherwise users opening an artifact see nothing. (This is the same lax-JSON failure pattern documented for signoff configs in CLAUDE.md — the API accepts the wrong shape silently and the bug only surfaces in the UI.)

The minimum viable `uiDefinition` for a blueprint with fields `title`, `risk_score`, `notes` and workflow steps `draft` / `review` / `approved`:

```json
"uiDefinition": {
  "views": {
    "main": {
      "label": "Main",
      "description": "",
      "viewComponent": {
        "type": "container",
        "layout": {
          "type": "sequential",
          "viewComponents": [
            { "type": "text-field",   "fieldId": "title",      "label": "Title" },
            { "type": "number-field", "fieldId": "risk_score", "label": "Risk score" },
            { "type": "text-field",   "fieldId": "notes",      "label": "Notes" }
          ]
        }
      }
    }
  },
  "uiStepDefinitions": {
    "draft":    {"viewId": "main"},
    "review":   {"viewId": "main"},
    "approved": {"viewId": "main"}
  },
  "artifactPageViewId": "main"
}
```

**Rules**:
- `artifactPageViewId` must point to a real view id, otherwise the main artifact page is blank.
- Every workflow step ID must have an entry in `uiStepDefinitions`, and every entry should point to a real `viewId` (typically `"main"`).
- Each `viewComponent` inside the layout's `viewComponents[]` references one field by id and uses the component type that matches its field type. **The complete set of valid `type` values is fixed by the server** (`text-field`, `category-field`, `card-reference-field`, `date-field`, `time-series-field`, `table-reference-field`, `boolean-field`, `json-field`, `uploaded-file-field`, `number-field`, plus `container`, `action`, `plugin-action` for layout/special). Anything else is rejected — `select-field`, `markdown-field`, `users-groups-roles-field`, `string-field` all sound plausible but **do not exist**:

| Field type | View component `type` |
|---|---|
| `TEXT` | `text-field` |
| `CATEGORY` | `category-field` |
| `NUMBER` | `number-field` |
| `BOOLEAN` | `boolean-field` |
| `DATE` | `date-field` |
| `REFERENCE` | `card-reference-field` (also used to reference users/groups via `bp.system.user` / `bp.system.group`) |
| `UPLOADED_FILE` | `uploaded-file-field` |
| `JSON` | `json-field` |

To build richer views (grouped cards, tabs, conditional visibility, per-step field hiding), see [govern-blueprint-designer/ui-views.md](govern-blueprint-designer/ui-views.md).

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `list-versions` hides a version I just created | Pre-existing non-admin path filtered DRAFTs (fixed — uses admin path now) | Re-run after upgrading; DRAFT versions should appear |
| `Save blocked: this version has existing artifacts...` | Edit removes a field or changes its type; server refuses without `dangerZoneAccepted` | Review diff (`get-version ... -o json`), then **ask the user** before retrying with `--force`. Prefer creating a new version |
| `unknown type "USER"` on signoff create | `usersContainer.type` is uppercase | Use lowercase: `"user"`, `"group"`, `"role"`, `"global-api-key"` |
| `signoffConfiguration.id must not be set in creation` | Round-tripped a signoff payload from `get-signoff-config` into `create-signoff-config` | Strip `id` before POST. `set-signoff-config` (update) is fine with `id` present |
| `Blueprint version IDs do not match` | JSON body's `id.versionId` differs from the URL `--version` | Either remove `id` from the body or align it with the URL |
| New version is invisible to artifact CRUD | Version is still DRAFT | `set-version-status BP VER ACTIVE` |
| Rename a workflow step → signoff config stops working | Signoff configs are keyed on step ID | Delete the signoff first, rename, recreate |
| Field added but UI doesn't show it | Field is not referenced by any `viewComponent` in any view | Add the field as `{"type": "<x>-field", "fieldId": "<id>", "label": "..."}` inside a view's `viewComponent` container |
| **Blueprint saves but artifact page is blank** | `uiDefinition.views = {}` and/or `viewId = ""` everywhere | Govern accepts empty views silently with no error. You MUST define at least one view (typically `main`) listing every field, set `artifactPageViewId` to it, and assign every step's `viewId` to it. See "UI views (minimum viable)" above. |
| Hook "Cannot mutate artifact from another hook" | Hook calls `dataikuapi` to edit a neighbor | Use `handler.artifactIdsToUpdate.append("ar.123")` instead |
| `category value not in categories list` | Artifact field value isn't in the CATEGORY field's `categories[]` | Expand `categories[]` in a new blueprint version, or fix the artifact value |
| `blueprint not found` after delete | All versions must be deleted first, then the blueprint | `delete-version` every version, then `delete` the blueprint |
| `cannot delete version, artifacts still reference it` | Artifacts using this version still exist | Delete the artifacts first, then the version |

## When NOT to use this skill

- **Artifact CRUD** (creating/updating/deleting individual governed items) → use the `dku-cli` skill's `govern artifact` commands
- **Runtime signoff operations** (moving through phases, adding feedback, delegating approvals) → use `dku govern signoff` commands (see dku-cli skill)
- **Govern users/groups admin** → use `dku govern user` / `dku govern group`
- **General Govern concepts** (what is a blueprint, what is governance) → see sibling `govern.md`

## References

- [govern-blueprint-designer/field-types.md](govern-blueprint-designer/field-types.md) — Complete catalogue of the 9 FieldTypes with JSON templates and live payload examples
- [govern-blueprint-designer/workflow-and-signoffs.md](govern-blueprint-designer/workflow-and-signoffs.md) — Workflow step definition, visibility conditions, signoff reviewer containers, recurrence, delegation
- [govern-blueprint-designer/hooks-and-actions.md](govern-blueprint-designer/hooks-and-actions.md) — Python hook anatomy, `handler` API, safe patterns, common pitfalls
- [govern-blueprint-designer/ui-views.md](govern-blueprint-designer/ui-views.md) — uiDefinition.views, view components (container / text-field / reference-field / ...), per-step view assignments, conditional views
- [govern-blueprint-designer/canonical-examples/](govern-blueprint-designer/canonical-examples/) — Real blueprint version payloads: a minimal starter + a rich fork of `bp.system.govern_project`
