# Pending Learnings

Insights from past sessions. Copy relevant entries to the dataiku-cli repo's `.learnings/PENDING.md` to process them into fixes via `/cli-improvement`.

---

## [2026-04-14] Govern blueprint UI: empty `views` silently produces a blank artifact page (third instance of the lax-JSON gotcha)
**Status:** processed (2026-04-14) — fixed `govern-blueprint-designer/SKILL.md` "UI views (minimum viable)" section + gotchas table; added a hard rule to the Blueprint Designer POC system prompt requiring a default `main` view on every blueprint.

### TL;DR
While testing the Blueprint Designer webapp POC, the agent created `bp.gdpr_data_export` with `uiDefinition.views = {}` and every step's `viewId = ""`. The user opened the artifact in Govern and saw **no view at all** — completely blank `/general` tab. The agent defended its choice by citing the skill's claim that "empty viewId means the step uses no custom view — users see the default overview". That claim is **wrong**: empty views renders nothing; Govern does NOT auto-render `fieldDefinitions` when `views` is `{}`. This is the third documented instance of the same Govern lax-JSON failure pattern (after the two signoff-config bugs in `[2026-04-08]`): the API silently accepts a wrong/empty payload shape, the doc encodes the assumed-correct behavior, and nothing tests the actual UI outcome.

### What broke
- **Skill** (`dataiku-devkit/skills/govern-blueprint-designer/SKILL.md` lines 286–304 + gotchas table line 317): the "UI views (minimum viable)" section showed `"views": {}` as the recommended baseline and explicitly told the agent that empty views = default overview rendering. The gotchas table also said "or leave `uiDefinition.views = {}` for default-rendered overview".
- **Result**: the Blueprint Designer agent followed the skill faithfully and shipped blueprints with no usable UI.
- **Compounding issue**: the agent confidently asserted *"all 5 fields visible on every step"* in its post-creation explanation, even though it had never opened the Govern UI itself — a doc citation presented as observed reality.

### What was fixed (this session)
- Rewrote the skill's "UI views (minimum viable)" section with a working minimal `uiDefinition` (a `main` view containing a sequential container of field references), plus a field-type → component-type table (`STRING`→`text-field`, `NUMERIC`→`number-field`, `BOOLEAN`→`boolean-field`, `DATE`→`date-field`, `CATEGORY`→`select-field`, `USER`/`GROUP`/`ROLE`→`users-groups-roles-field`, `ARTIFACT_REFERENCE`→`card-reference-field`, `MARKDOWN`→`markdown-field`).
- Replaced the misleading gotchas row and added a new explicit one: *"Blueprint saves but artifact page is blank — `uiDefinition.views = {}` and/or `viewId = ""` everywhere — Govern accepts empty views silently with no error. You MUST define at least one view."*
- Added a HARD RULE to `webapps/blueprint-designer/system_prompt.md` Phase 5: every blueprint MUST emit a default `main` view listing all fields, with the same field-type → component-type table inline, even if the user didn't ask for views.
- Added a tone rule to the same prompt: *"Trust empirical observation over documentation. ... If the user reports something doesn't work the way you described it, do NOT defend the doc — verify against a working example."*

### Where this should propagate (next /cli-improvement run)
| Where | What |
|---|---|
| `dataiku-devkit/skills/dataiku/references/govern.md` | Audit the version-definition examples — do any of them ship `"views": {}`? If so, replace with a working main view and a similar warning. |
| `scripts/verify_govern_docs.py` | The script already classifies "blueprint version" payloads and posts them to a live Govern instance. Extend it to check whether the resulting `uiDefinition.views` is non-empty and `artifactPageViewId` is set — if not, fail the doc. This catches the silent UI-blank failure at doc-validation time. |
| `CLAUDE.md` "Govern Doc Validation" gotcha | Add this as a third recorded instance (next to the two signoff-config bugs from 2026-04-08 and 2026-04-12), so the pattern is visible to future agents. |
| `dku govern blueprint set-version-definition` CLI | Consider a soft warning (stderr) when the pushed definition has `views: {}` — agents pattern-match on stderr and would catch this immediately. |
| `dataiku-devkit/skills/govern-blueprint-designer/references/ui-views.md` | Verify (or create, if it doesn't exist yet) the deeper reference for grouped cards / tabs / conditional visibility / per-step view assignments. |

### Meta-lesson
This is the **third time** a Govern doc shipped a wrong payload shape that the API silently accepted (signoff `feedbackUsersGroups` vs `feedbackGroups`, signoff `approvers[]` vs `approverConfiguration`, now empty-views vs default-rendering). The pattern is consistent: lax JSON validation on the server + no test that opens the UI + agents that trust the doc = silent UI-broken state. The fix is structural: `verify_govern_docs.py` needs to assert UI-shape invariants, not just "did the API return 200".

### Reproduction
```bash
# Create a blueprint with empty views (the way the skill said was OK):
uv run python -c "
import dataikuapi
c = dataikuapi.DSSClient('http://localhost:8082', '<api-key>')
g = c.get_govern_client()
... (set-version-definition with uiDefinition.views = {}) ...
"
# Open in Govern UI: http://localhost:8102/blueprint-designer/blueprint/<id>/version/bv.v1/general
# Observe: page is blank. Expected (per old doc): all fields rendered.
```

---

## [2026-04-08] Govern CLI — new command groups, signoff verbs, admin commands, reference doc, namespace refactor
**Status:** processed (2026-04-08) — added delete commands for group/role/blueprint/custom-page, file download, time-series push-values/delete, dataikuapi quirks in CLAUDE.md, updated govern.md and commands.md

### TL;DR
The biggest friction came from **dataikuapi's signoff configuration payloads** — field names differ between creation (`feedbackUsersGroups`, `approverConfiguration`) and what the signoff definition returns (`feedbackGroups`, `approvers`), and the server gives cryptic errors (`NullPointerException`, `title is required`) instead of telling you which field is wrong. The second major insight is that **no Govern documentation existed at all** in the devkit — agents had zero guidance on JSON payload structures, the signoff state machine, or users container types. Third, several CLI commands that would be natural to have are missing (group delete, role delete, blueprint delete, file download).

### CLI Friction (5 issues)

| Issue | What Happened | Suggested Fix |
|-------|--------------|---------------|
| No `govern group delete` | Had to use Python API `govern.get_group('name').delete()` to clean up test groups | Add `dku govern group delete GROUP_NAME --confirm` |
| No `govern role delete` | Had to use Python API `handler.get_role('id').delete()` to clean up test roles | Add `dku govern role delete ROLE_ID --confirm` |
| No `govern blueprint delete` | Had to use Python API `designer.get_blueprint('id').delete()` to clean up | Add `dku govern blueprint delete BLUEPRINT_ID --confirm` |
| No `govern custom-page delete` | Had to use Python API for cleanup | Add `dku govern custom-page delete PAGE_ID --confirm` |
| No `govern file download` | `GovernUploadedFile.download()` exists in API but no CLI command | Add `dku govern file download FILE_ID [--dest PATH]` |

### Skill & Doc Gaps (3 issues)

| Gap | Impact | Where to Fix |
|-----|--------|-------------|
| Zero Govern documentation existed in devkit | Agents had no reference for any govern command, JSON payloads, or the signoff state machine | Created `govern.md` — now fixed |
| `commands.md` had no govern entries | Agents couldn't discover govern commands from the CLI reference | Added to `commands.md` — now fixed |
| No trigger for "govern" in SKILL.md | Skill wouldn't activate when agent needed govern commands | Added trigger — now fixed |

### Gotchas Hit (6 issues)

1. **Signoff config key mismatch**
   - **Tried**: Created signoff config with `feedbackGroups` key (matching the get_details() output)
   - **Failed**: Server silently accepted it but `feedbackUsersGroups` was empty — nobody could review
   - **Fix**: The creation key is `feedbackUsersGroups`, not `feedbackGroups`
   - **Document in**: govern.md gotchas table (done), CLI error would need server-side fix

2. **Signoff config missing `title`**
   - **Tried**: Created signoff config without `title` field
   - **Failed**: `ValidationException: SignoffConfiguration title is required`
   - **Fix**: Add `"title": "..."` to the signoff config JSON
   - **Document in**: govern.md gotchas table (done)

3. **Feedback group missing `title`**
   - **Tried**: Used `id` and `label` on feedback group entries but not `title`
   - **Failed**: `ValidationException: Users group title is required`
   - **Fix**: Each `feedbackUsersGroups` entry needs both `id` and `title`
   - **Document in**: govern.md gotchas table (done)

4. **Users container type must be `"user"` not `"SINGLE_USER"`**
   - **Tried**: `{"type": "SINGLE_USER", "login": "admin"}`
   - **Failed**: `Cannot deserialize UserUsersContainer: unknown type "SINGLE_USER"`
   - **Fix**: `{"type": "user", "login": "admin"}` — lowercase, no prefix
   - **Document in**: govern.md gotchas table (done)

5. **Signoff state machine: can't reset directly**
   - **Tried**: `update_status('NOT_STARTED')` from `WAITING_FOR_FEEDBACK`
   - **Failed**: `Unable to set the status to 'NOT_STARTED' when current status is 'WAITING_FOR_FEEDBACK'`
   - **Fix**: Must go through ABANDONED first: `WAITING_FOR_*` -> `ABANDONED` -> `NOT_STARTED`
   - **Document in**: govern.md signoff state machine (done)

6. **Approver config format: `approverConfiguration` not `approvers` array**
   - **Tried**: `"approvers": [{"type": "user", "login": "admin"}]`
   - **Failed**: `Expected BEGIN_ARRAY but was BEGIN_OBJECT` / then `NullPointerException`
   - **Fix**: Use `"approverConfiguration": {"usersContainer": {"type": "user", "login": "admin"}}`
   - **Document in**: govern.md signoff configuration structure (done)

### dataikuapi Discoveries

| Quirk | Details | Add to CLAUDE.md? |
|-------|---------|-------------------|
| `list_users()` returns raw dicts, not objects | Unlike most `list_*` methods that return objects with `.get_raw()`, user list returns plain dicts with camelCase keys (`displayName`, `sourceType`) | Yes |
| `list_groups()` returns raw dicts | Same pattern — plain dicts, not objects | Yes |
| `create_users()` returns status dicts | Returns `[{"login": "...", "status": "SUCCESS/FAILURE", "error": "..."}]` — parsed from text response via `json.loads()` | No (covered by test) |
| `GovernGroup.get_definition()` returns a dict directly | Not a definition object with `.get_raw()` — just a plain dict | Yes |
| `upload_file()` takes `(file_name, file_stream)` | Uses `_perform_json_upload` internally, not `_perform_json` — different codepath | No |
| `GovernTimeSeries.time_series_id` is the ID field | Not `.id` like most other objects | No (minor) |
| `GovernUploadedFile.uploaded_file_id` is the ID field | Same non-standard naming | No (minor) |
| Signoff creation keys differ from read keys | Write: `feedbackUsersGroups`, `approverConfiguration`. Read: `feedbackGroups`, `approvers` | Yes — this is the #1 gotcha |

### Built-In Feature Misses

None — this session was about building CLI commands and documentation, not operating DSS features.

### Recommended Changes (ranked by agent impact)

1. **govern.md reference doc** — Created. This is the highest-impact change: agents had zero Govern guidance before. Contains JSON payloads, state machine, gotchas table with all 6 gotchas discovered during live testing.
2. **Add delete commands** for group, role, blueprint, custom-page — agents currently can't clean up Govern resources via CLI, forcing Python API fallback.
3. **Add `govern file download`** — the API method exists (`GovernUploadedFile.download()`), just needs a CLI wrapper.
4. **Document signoff config key mismatch in CLAUDE.md** — `feedbackUsersGroups` vs `feedbackGroups` is the single most confusing API asymmetry and will trip every agent.
5. **Add `govern time-series push-values` and `govern time-series delete`** — the API has `push_values()` and `delete()` but no CLI commands.

---

## [2026-04-12] Govern blueprint version designer — CLI surface + new authoring skill + live smoke test
**Status:** pending
**Recurring** (also seen: 2026-04-08 — same area, previous fix set `approverConfiguration` singular; actual shape is `approvers[]` plural list. Signoff payload shape keeps getting documented wrong. Third time's the charm — this session re-fixed it by dumping live payloads and reading the Java backend model directly.)

### TL;DR

Three high-value findings: (1) `govern.md` reference doc had **structurally wrong** signoff payload (missing `users[]` nesting inside `feedbackUsersGroups`, wrong singular `approverConfiguration` key — actual shape is `approvers[]` list) — agents authoring from the ref would have failed every time; (2) the pre-existing `list-versions` silently filtered DRAFT versions via the non-admin API path, which makes the whole blueprint authoring loop non-functional; (3) `usersContainer.type` case-sensitivity (`"user"` not `"USER"`) was undocumented and only surfaces as a runtime parse error. All three are now fixed, but all three were caught **only by smoke testing against live Govern** — mock tests couldn't have found them.

### CLI Friction (5 issues)

| Issue | What Happened | Suggested Fix |
|---|---|---|
| `list-versions` hides DRAFTs | Created `bv.v1` as DRAFT, ran `dku govern blueprint list-versions bp.scratch_designer_test`, got empty table. Had to dig into `dataikuapi/govern/blueprint.py` to find out the non-admin `/blueprint/{id}/versions` endpoint filters DRAFTs server-side | FIXED in this PR — `list-versions` now uses `designer.get_blueprint()` |
| `artifact create -f owner=admin` fails opaquely | REFERENCE fields expect artifact IDs (`ar.2`), not logins. Server message was only `Field owner value is required for artifact: ar.875` when the field was missing. Agents will naturally try login strings first | Error should hint: "REFERENCE field 'owner' expects an artifact ID (e.g. `ar.2`). Run `dku govern artifact list --blueprint bp.system.user` to find the right ID." |
| No `dku govern artifact search` command | Typed `dku govern artifact search --blueprint bp.system.user`, got `No such command`. The verb is `list`, not `search` | Consider an alias `search → list`, or make the error message suggest `list` |
| `artifact create -f foo=42` numeric coercion not documented | `-f estimated_monthly_cost_usd=1200` auto-parsed to `1200.0`. Works, but the behavior isn't documented and agents can't predict it for edge cases (quotes? scientific notation?) | Add a row to govern.md artifact structure: "`-f foo=42` auto-parses to number, `-f foo=\"42\"` stays string" |
| `cd /tmp/... && uv run dku ...` lost project context | First smoke test attempt: `cd /tmp/bp-smoke && uv run dku govern blueprint create ...` returned `No such command 'govern'`. Fixed by staying in repo root and using absolute `@/tmp/...` paths | Document in the CLI skill: `uv run` relies on being in the project dir; prefer absolute paths over `cd` when chaining |

### Skill & Doc Gaps (6 issues)

| Gap | Impact | Where to Fix |
|---|---|---|
| **`govern.md` signoff payload was structurally wrong** — showed `feedbackUsersGroups[].usersContainer` (no `users[]` wrapper) and `approverConfiguration` (singular) when the real shapes are `feedbackUsersGroups[].users[].usersContainer` and `approvers[]` (list) | Any agent authoring a signoff via `govern.md` as reference would hit parse errors on every attempt. This is the SECOND time the signoff shape has been documented wrong (see 2026-04-08 — that session set `approverConfiguration` singular) | FIXED in this PR — `dataiku-devkit/skills/dataiku/references/govern.md`. Recommend adding a JSON-shape validation test that parses every JSON block from govern.md and sends it through the relevant command against a live instance |
| `usersContainer.type` case-sensitivity undocumented | Cost me one retry during smoke test (`"USER"` rejected). Would cost every agent a retry | FIXED — now in govern.md, govern-blueprint-designer SKILL.md cheat sheet, CLAUDE.md, and the server's own error lists the valid values |
| Admin vs non-admin Govern API divergence not documented anywhere | The same method name `list_versions()` behaves differently depending on whether you called `govern.get_blueprint()` or `govern.get_blueprint_designer().get_blueprint()`. Non-admin filters DRAFTs. dataikuapi docs don't mention this | Add to CLAUDE.md dataikuapi quirks: "Govern has two parallel read paths — non-admin and admin designer. Use `get_blueprint_designer()` for anything that needs to see DRAFTs or ARCHIVED versions." Audit every `govern_*.py` command file to default to the admin path when available |
| No "fork-from-system" guidance prominent enough | The official Govern docs recommend forking over blank templates, but neither `govern.md` nor the old `dku-cli` skill surfaced this. Agents default to blank, miss under-the-hood system fields | FIXED — `govern-blueprint-designer/SKILL.md` cheat sheet rule #2 makes it explicit |
| `--force` / `dangerZoneAccepted` semantics were undiscoverable before this PR | `set-version-definition` could silently destroy artifact data if an agent reflexively added `--force` to make an error go away | FIXED — prescriptive error message in CLI + cheat sheet rule #5 in the new skill |
| REFERENCE field values in artifact payloads: docs example correct but buried | The `govern.md` artifact JSON example does show `"business_initiative": "ar.10"` but agents tend to skim past it. No gotcha row explicitly calls out "logins don't work" | Add a gotchas row: `REFERENCE field rejected with "validation error"` → `Use artifact ID (ar.N), not the target's login/name. Find the ID via dku govern artifact list --blueprint bp.system.user` |

### Gotchas Hit (4 issues)

**1. Lowercase `usersContainer.type`**
- **Tried:** `{"usersContainer": {"type": "USER", "login": "admin"}}` in my first signoff config
- **Failed:** `Cannot deserialize UsersContainer: unknown type "USER" ... (possible type values are: "role", "global-api-key", "user", "group")`
- **Fix:** Use `"type": "user"` (all lowercase)
- **Document in:** CLI cheat sheet (`govern-blueprint-designer/SKILL.md`) ✓, govern.md gotchas ✓, CLAUDE.md ✓. The server error is already prescriptive — no CLI change needed.

**2. `list-versions` hides DRAFT versions**
- **Tried:** `dku govern blueprint list-versions bp.scratch_designer_test` right after creating a DRAFT version
- **Failed:** Empty table — the version was invisible
- **Fix:** Fixed the command to use the admin designer path (`get_blueprint_designer().get_blueprint(bp).list_versions()`)
- **Document in:** Code fix ✓, skill gotchas row ✓, CLAUDE.md ✓

**3. `govern artifact create -f owner=admin` when owner is REFERENCE**
- **Tried:** Skipped `owner` on first attempt, got `Field owner value is required`. On retry passed `ar.2` (admin artifact ID)
- **Failed:** Validation error; the message doesn't tell you REFERENCE fields need artifact IDs
- **Fix:** Look up the user artifact via `dku govern artifact list --blueprint bp.system.user`
- **Document in:** Should be a new gotcha row in `govern.md` + ideally a prescriptive error in the artifact create path: "Field 'owner' is REFERENCE(bp.system.user) — value must be an artifact ID like `ar.N`, not a login"

**4. Signoff `create` body must not contain `id`; `addedBy`/`addedOn` are server-stamped**
- **Tried:** Round-tripping `get-signoff-config` output into `create-signoff-config` would include server-stamped fields
- **Failed:** Server rejects POST if `id` is set (`signoffConfiguration.id must not be set in creation`)
- **Fix:** CLI strips `id` defensively before POST; update (PUT) is fine with `id` present. `addedBy`/`addedOn` are harmless either way
- **Document in:** Done — `workflow-and-signoffs.md` reference doc + create-signoff-config command help

### dataikuapi Discoveries

| Quirk | Details | Add to CLAUDE.md? |
|---|---|---|
| Admin vs non-admin Govern paths silently differ | `govern.get_blueprint(id).list_versions()` uses `/blueprint/{id}/versions` (filters DRAFTs). `govern.get_blueprint_designer().get_blueprint(id).list_versions()` uses `/admin/blueprint/{id}/versions` (returns all). Same method name, different results | **Yes** — already added as "Govern Blueprint Designer" quirks section |
| `GovernAdminBlueprintVersionTrace.status` is a `@property`, not a method | `trace.status` returns the string directly; `trace.set_status("ACTIVE")` is the mutator and takes a plain string body | No, only touched once |
| `create_signoff_configuration` server-rejects body with `id` set | Backend validation explicitly rejects POST bodies that include `signoffConfiguration.id`. `save_signoff_configuration` (PUT) accepts `id` iff it matches the URL path | Worth a line in dataikuapi quirks: "Govern admin signoff POST body must omit `id` (server assigns from URL); PUT body may include `id` but must match URL" |
| `_perform_json` body serialization for plain strings | `trace.set_status(status)` passes `body=status` (a plain Python string) and the backend expects it serialized as JSON-encoded string (`"ACTIVE"`). Works because `dataikuapi`'s json helper handles primitives | Not a CLAUDE.md entry — standard behavior |
| Server stamps `addedBy` + `addedOn` on each `SignoffUser` | Added on save/create, appear in GET round-trips. Setting on create unnecessary; leaving in on update harmless | Documented in new skill's workflow-and-signoffs.md |

### Built-In Feature Misses

Clean on this dimension — the task was CLI surface + a skill, not shipping user-facing logic. The demo blueprint uses a native Govern **logical hook** for compliance classification (exactly the built-in pattern you'd want vs an external scheduler or Python recipe), so no anti-patterns to report.

### Recommended Changes (ranked by agent impact)

1. **Add a gotcha + prescriptive error for REFERENCE-field-with-login mistake** in `dku govern artifact create` / `set-field`. The server error currently just says "validation error" — if the CLI detected a REFERENCE field being set to a non-`ar.N` value, it could say: *"REFERENCE field 'owner' allows blueprints `[bp.system.user, bp.system.group]` — value must be an artifact ID (e.g. `ar.2`). Run `dku govern artifact list --blueprint bp.system.user` to find candidates."* Every agent authoring their first Govern artifact will hit this. File: `src/dku_cli/commands/govern_artifact.py`.
2. **Audit the rest of `govern.md` reference doc against live payloads.** The signoff structure was materially wrong and only caught because I was actively authoring signoffs. This is the **second time** the signoff payload shape has been documented wrong. Add a doctest-style script in `benchmark/` that parses every JSON block from `govern.md` and sends it through the relevant command. File: `dataiku-devkit/skills/dataiku/references/govern.md` + new validation script.
3. **Expand dataikuapi quirks block in CLAUDE.md with Govern admin/non-admin path divergence.** Generic pattern: `govern.get_X()` returns non-admin views, `govern.get_X_designer()` returns admin views with different filtering. File: `CLAUDE.md` + audit every `govern_*.py` command file.
4. **Extend `tests/conftest.py` Govern fixture into a proper helper module** instead of one monolithic function. Blueprint designer section alone grew 70 lines in this PR. A `tests/fixtures/govern_designer.py` module with dedicated mock builders would make the next Govern feature safer to add.
5. **Add a cheat-sheet rule to `dku-cli/SKILL.md`** pointing at the new `govern-blueprint-designer` skill. Current pointer is ~40 lines into the "Companion Skill" section — agents working on Govern admin tasks might miss it. Add rule to top-of-file cheat sheet.
6. **Add `import-version` / `export-version` CLI commands** (low priority). The server has `/publicapi/admin/blueprint/{id}/versions/import` but `dataikuapi` doesn't wrap it. Essential for "fork across Govern instances" workflows. File: `src/dku_cli/commands/govern_blueprint.py` — call `_perform_json` directly.

---
