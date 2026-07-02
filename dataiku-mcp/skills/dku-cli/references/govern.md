# Reference: Govern

Govern is a standalone node: **no projects/datasets/recipes** — only a
governance schema (blueprints + versions) describing governed records
(artifacts) and a review workflow (signoffs / feedbacks / approvals). The CLI
uses `get_govern_client()` and needs an admin API key. Exact flags: `--help`.

On a GOVERN node every non-govern, project-scoped command exits **code 4** and
tells you to use `dku govern …` (or `dku auth switch <design-profile>`).

## Entity model

| Concept | ID prefix | What it is |
|---|---|---|
| Blueprint | `bp.*` | Container — stores only `name`, `icon`, `color`, `backgroundColor` |
| Blueprint version | `bv.*` | The actual template: fields, workflow, hooks, views, signoffs. `DRAFT` / `ACTIVE` / `ARCHIVED`. `bv.system.default` always exists |
| Artifact | `ar.*` | One governed record. References its `{blueprintId, versionId}` |
| Role | `ro.*` | Reviewer/approver template, bindable per blueprint |
| Custom Page | `cp.*` | UI page (table/matrix/kanban/custom-html) |
| Uploaded File | `uf.*` | Attachment stored against a field |
| Time Series | `ts.*` | Timestamped metric points on an artifact |

**Blueprint ≠ version.** `set-definition` edits the blueprint entity
(name/icon/color); everything structural lives on the **version** and is edited
via `set-version-definition`. Only **ACTIVE** versions can host new artifacts.

## Authoring loop (canonical)

1. **Fork, don't start blank:** `create-version BP NEW --from bv.system.default`
   (system versions carry under-the-hood fields/steps Govern needs). New
   versions land in **DRAFT**.
2. `dku --format json govern blueprint get-version BP VER > bv.json` → edit the full JSON (there is no
   add-field command; round-trip the whole definition).
3. `set-version-definition BP VER --definition @bv.json`.
4. `create-signoff-config BP VER STEP --definition @signoff.json` per gated step.
5. `set-version-status BP VER ACTIVE` — **do not skip**; DRAFT is invisible.

`--force` (dangerZoneAccepted): if the version has artifacts and your edit
removes a field or changes its type, the server blocks the save. `--force`
**silently discards that field's data in every artifact** — never use without
explicit user go-ahead; prefer a new version + migrate.

`describe-version BP VER` pretty-prints fields/workflow/signoffs/views AND flags
silent-failure patterns (empty views, missing `artifactPageViewId`, unreferenced
fields). Prefer it over `get-version | jq` when authoring.

## Version definition — top-level keys (unusual names!)

| Key | Type | Note |
|---|---|---|
| `id` | `{blueprintId, versionId}` | must match the URL or → "Blueprint version IDs do not match" |
| `fieldDefinitions` | **dict keyed by field id** (NOT a list) | type at `.fieldType`, NOT `.type` |
| `workflowDefinition` | `{stepDefinitions:[...], initialStepId}` | NOT `workflow` |
| `logicalHookList` | list (NOT `hooks`) | `{name, phases, script}` |
| `actions` | dict keyed `ac.*` | user-triggered buttons |
| `uiDefinition` | `{views, uiStepDefinitions, artifactPageViewId}` | empty `views` silently renders BLANK |

## Field types — validation rules (high-value)

Nine `fieldType` values. Every definition has `label`, `fieldType`,
`sourceType` (`STORE` user-set / `COMPUTE` auto — agents author STORE only),
and required flag (`isMandatory` on read; `required` also accepted on write).

| fieldType | Scalar value | Extra required key |
|---|---|---|
| `TEXT` | `"hello"` | — |
| `NUMBER` | `42` / `3.14` | — |
| `BOOLEAN` | `true` | — |
| `DATE` | `"2026-06-01T00:00:00.000Z"` | — |
| `CATEGORY` | `"High"` | `categories: [...]` |
| `REFERENCE` | `"ar.123"` | `allowedBlueprints: [...]` |
| `UPLOADED_FILE` | `"uf.1"` | — |
| `TIME_SERIES` | API/hook-only | — |
| `JSON` | any JSON | — |

**The validation rules that cause errors:**

- **List vs scalar.** Any field becomes a list by adding `listConfig`
  (presence is what matters: `{}`, or `{"cardinalityMin":N,"cardinalityMax":M}`).
  In the artifact payload, **list fields MUST be JSON arrays even for one value**:
  `{"countries": ["France"]}` ✓ vs `{"countries": "France"}` ✗ (silently ignored).
- **CATEGORY.** `categories` is required; artifact values must match **exactly,
  case-sensitively**, or → "category value not in categories list". Multi-select
  via `listConfig`.
- **REFERENCE.** Value is an **artifact ID** (`ar.<n>`), NOT a login/name —
  passing `-f owner=admin` → "REFERENCE field expects an artifact ID". There is
  **no USER/GROUP fieldType**: reference users/groups via `allowedBlueprints:
  ["bp.system.user","bp.system.group"]` and point at `ar.*` artifacts.
- **DATE.** Must be an ISO-8601 string **with a time portion and timezone** —
  `"2026-06-01"` alone is rejected. `…T00:00:00.000Z` (UTC) is safest.
- **`required: true` is global** — enforced on every artifact regardless of
  workflow step or view visibility. For "required from step X", use a hook, not
  `required`. A required field not placed in any view blocks save (user can't set it).

Field definition example:

```json
{
  "risk_level": {"label":"Risk level","fieldType":"CATEGORY","sourceType":"STORE",
    "required":true,"categories":["Low","Medium","High"]},
  "owners": {"label":"Owners","fieldType":"REFERENCE","sourceType":"STORE",
    "required":false,"allowedBlueprints":["bp.system.user","bp.system.group"],"listConfig":{}}
}
```

Artifact create payload (`create --definition` / via `-b`/`-n`/`-f` flags;
`set-field` updates one field):

```json
{"blueprintVersionId":{"blueprintId":"bp.system.govern_project","versionId":"bv.system.default"},
 "name":"Churn model","fields":{"description":"…","cost_rating":"High",
  "countries":["France","Germany"],"start_date":"2025-01-15T00:00:00.000Z","owner":"ar.10"}}
```

## Workflow + sign-offs

`workflowDefinition.stepDefinitions` is an ordered list; users advance in
sequence (no branching). Step `id` is a **stable key** — signoff configs are
keyed on it; rename a step and the signoff orphans (delete signoff, rename,
recreate). Optional `visibilityCondition` (an `ArtifactFilter`) hides a step;
**a mandatory signoff on a hidden step is silently bypassed**.

Sign-off state machine (uppercase, case-sensitive):
`NOT_STARTED → WAITING_FOR_FEEDBACK → WAITING_FOR_APPROVAL → APPROVED|REJECTED|ABANDONED`.
Reset must pass through `ABANDONED` (can't jump `WAITING_*` → `NOT_STARTED`).
Feedback status: `APPROVED|MINOR_ISSUE|MAJOR_ISSUE`. Approval: `APPROVED|REJECTED|ABANDONED`.

Signoff config payload (`create-signoff-config BP VER STEP`):

```json
{"title":"Review gate","mandatory":true,
 "feedbackUsersGroups":[{"id":"reviewers","title":"Reviewers",
   "users":[{"usersContainer":{"type":"user","login":"alice"}}]}],
 "approvers":[{"usersContainer":{"type":"user","login":"bob"}}],
 "recurrenceConfiguration":{"activated":false,"days":0,"weeks":0,"months":0,"years":0,"reloadConf":false}}
```

- **Do NOT set `id` in a create body** — server builds it from the URL; →
  "signoffConfiguration.id must not be set in creation". `set-signoff-config`
  (update) tolerates `id`.
- Each `feedbackUsersGroups` entry needs both `id` (used by
  `add-feedback/delegate-feedback --group-id`) **and** `title` (server rejects
  empty). `approvers` is a flat list (no grouping).
- **`usersContainer.type` is lowercase, four values only** (server
  `UsersContainer` enum): `user` (`login`), `group` (`groupName`), `role`
  (`roleId`), `global-api-key` (`keyId`). `"USER"` / `"SINGLE_USER"` / `"FIELD"`
  → `unknown type "…"` (there is no FIELD/dynamic-reviewer container type).
- `recurrenceConfiguration.activated:true` requires sum of intervals > 0;
  `reloadConf:true` reloads the config from the blueprint on reset.
- `addedBy`/`addedOn` are server-stamped — omit on create.
- **Cross-instance export/import drops all non-role reviewers** (server
  hardcodes user/group/api-key validation to NONE). Use Govern **roles** for
  reviewers that must survive a round-trip; imported versions land in DRAFT.
  Built-in roles (the full set): `ro.project_manager`, `ro.contributor`,
  `ro.reader`, `ro.business_reviewer`, `ro.it_operations_reviewer`,
  `ro.risk_compliance_reviewer`, `ro.final_approver`.

**Runtime prerequisites to create/run a signoff** (each maps to a distinct error):
the workflow step must be `ONGOING`, not `NOT_STARTED` (`workflow step is not active`);
a signoff **config** must exist on the version (`No sign-off configuration exists`);
the signoff must be created on the artifact before feedback/approval; and the
authenticated identity must be in the target feedback/approval group — otherwise
`add-feedback`/`add-approval` fail with `User/API key is not part of the group` (use a
`delegate-*` command to act on someone's behalf). A **role** used as reviewer/approver
must first be bound to real groups/users; an unbound role is an empty set, making a
mandatory gate impossible to cross (`add-approval` → "is not an approver").

## UI views — the #1 silent-failure

**Empty `views: {}` does NOT auto-render — the artifact page is BLANK.** The API
silently accepts `views:{}`, `artifactPageViewId:""`, and step `viewId:""`.
You MUST declare ≥1 view that references your fields, set `artifactPageViewId`
to a real view id, and give **every** workflow step a `uiStepDefinitions` entry
pointing at a real view. Verify with `describe-version`.

Each `viewComponent` is a `container` (`layout`: `sequential` or `grid`) holding
field-component leaves. **Valid component `type` values are a fixed server set**
— anything else is rejected even if plausible (`select-field`, `markdown-field`,
`string-field`, `users-groups-roles-field` do NOT exist):

| fieldType | component `type` |
|---|---|
| TEXT | `text-field` |
| NUMBER | `number-field` |
| BOOLEAN | `boolean-field` |
| DATE | `date-field` |
| CATEGORY | `category-field` |
| REFERENCE (incl. user/group) | `card-reference-field` |
| UPLOADED_FILE | `uploaded-file-field` |
| TIME_SERIES | `time-series-field` |
| JSON | `json-field` |

Plus layout/special: `container`, `action` (`actionId`), `plugin-action`,
`table-reference-field`. `absoluteUiIndex` is server-generated — preserve it
when round-tripping. Components support `conditionalVisibility`
(`{type:"field",fieldId,comparator,value}`). An `action` is only visible if a
view contains a matching `action` component.

## Embedding external content (custom-html page)

A custom page's `type` value is the short form — verified live: `standard-page`,
`artifact-table`, `custom-html` (the `custom-page-*` strings are Angular component
names, NOT the `type` field). A `custom-html` page (`cp.*`) is the **only** way to
surface external content — a DSS dashboard/webapp, chat assistant, BI view — inside
Govern without a plugin; the other types (`artifact-table`/matrix/kanban) are structured
views over artifacts. Custom HTML runs through `DomSanitizer.bypassSecurityTrustHtml`, so
**`<iframe>` and `<script>` are both allowed** (admin-only editable — Govern trusts the author).

```json
{"type":"custom-html","htmlContent":"<iframe src=\"…\" style=\"position:absolute;inset:0;width:100%;height:100%;border:0\"></iframe>"}
```

- **Embed a DSS webapp by its BARE view URL** `http://<dss>/webapps/<PROJECT>/<id>/`,
  **NOT** the Angular-shell `…/projects/<PROJECT>/webapps/<id>_<slug>/` (the shell won't
  render in an iframe). The card takes 100% width/height; let the iframe own scrolling.
- Author via `dku govern custom-page create <id> --definition @page.json`; round-trip an
  existing custom-html page (`dku --format json govern custom-page get <id>`) to confirm the full shape.
- **Embedding auth:** the iframe renders only if the user has a live DSS session in the same
  browser AND Govern+DSS are same-site (`SameSite=Lax` cookie). Different domains → user must be
  logged into both, or make the webapp public. For no-login embeds set `forceAuthentication=false`
  and use `/public-webapps/<proj>/<id>/`. Always use the URL the user's BROWSER hits DSS on, not
  Govern's internal URL — wrong choice = blank iframe / login wall with no error.

## Time series — datapoint shape

`ts.*` points are pushed as an array; `timestamp` is **epoch milliseconds, not seconds**
(a seconds value lands in 1970). API/hook-only — no view authoring.

```json
[{"timestamp": 1700000000000, "value": 42}, {"timestamp": 1700000060000, "value": 99.5}]
```

## Logical hooks & custom actions (durable rules)

Python on lifecycle phases `CREATE`/`UPDATE`/`DELETE`, as `logicalHookList[]`
entries (`{name, description, phases, script}`). Custom **actions** are
user-triggered buttons in `actions{}` (keyed `ac.*`), shown only if a view holds
a matching `action` component. Both call `handler = get_handler()` — the **same**
object (server `handler.py`). Its complete surface: `handler.artifact.fields[...]`
(`None` on DELETE), `handler.hookPhase`, `handler.authCtxIdentifier` (a string —
no `.login`), `handler.client`, `handler.status` (default `'SUCCESS'`),
`handler.message`, `handler.fieldMessages`, `handler.artifactIdsToUpdate`.

- **There is NO `handler.fail()`, `.log()`, `.now()`, or `.parameters`.** Block a
  save by `raise ValueError("reason")` (loud — traceback in the log) or
  `handler.status="ERROR"; handler.message="reason"` (clean — no log trace).
- **`print()` is dropped** (the kernel `exec`s with no stdout redirect) — log via
  `logging.getLogger('govern_python_server')`. Log file (Govern node):
  `$DIP_HOME/run/python-scripts/logical-hook.log`.
- Hooks run **before** commit; the action may still fail afterward. **Never mutate
  neighbor artifacts via `handler.client`** from a hook — it can trigger another
  hook and is unsupported. Sync neighbors by appending IDs to
  `handler.artifactIdsToUpdate` (their UPDATE hooks run after this commits).
- Actions, unlike hooks, **can** safely call `dataikuapi` (explicit, post-commit).
  Prefer built-ins over external code: derived values → hook; validation/blocking
  → hook `raise`/`status`; approval gates → signoff; user side-effects → action.

## Audit & observability

`auditTrailSettings.targets` is `[]` by default — **no audit is captured** and
`audit.log` stays 0 bytes however many hooks fire (an empty log is NOT proof
hooks aren't running; it means audit isn't enabled). Enable via `PUT
/admin/general-settings` (returns an empty body → `JSONDecodeError` on success;
verify with a GET). Govern wires only **two** target types: `LOG4J`
(JSON-per-line to `$DIP_HOME/run/audit.log`) and `EVENT_SERVER` (POST each event
to a URL → DSS Event Server → audit dataset → public API). Design-node targets
`KAFKA` / `FSLIKE` (S3/Azure/GCS) / `BIGQUERY` / `STATSD` are **not** wired on
Govern — copying them over silently no-ops. EVENT_SERVER pushes are chunked
(`Transfer-Encoding: chunked`, **no `Content-Length`**) with a **flat** event
shape; `audit.log` nests the same fields under `message:{}`.

## Common error → cause → fix

| Symptom | Fix |
|---|---|
| exit 4 on GOVERN node | use `dku govern …` |
| blank artifact page | declare a non-empty view; set `artifactPageViewId`; map every step |
| `unknown type "USER"` | lowercase `usersContainer.type` |
| `id must not be set in creation` | strip `id` from signoff create body |
| `Save blocked: existing artifacts` | ask user → `--force`, or new version + migrate |
| list field rejected | pass a JSON array even for one value |
| REFERENCE expects artifact ID | use `ar.<n>`, not a login (`blueprint fields BP` shows allowedBlueprints) |
| field values silently ignored | field id doesn't match version; check `blueprint fields BP` |
| version invisible to artifacts | still DRAFT → `set-version-status … ACTIVE` |
| signoff has no reviewers after save | key is `feedbackUsersGroups`, NOT `feedbackGroups` — wrong key silently accepted, group ends up empty |
