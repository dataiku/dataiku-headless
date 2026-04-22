# Pending Learnings

Insights from past sessions. Copy relevant entries to the dataiku-cli repo's `.learnings/PENDING.md` to process them into fixes via `/cli-improvement`.

---

## [2026-04-07] App Designer CLI commands + CDISC app build
**Status:** resolved

### TL;DR
Built two new command groups (`dku app-designer`, `dku app`) from scratch by reverse-engineering the manifest JSON from live DSS instances. The biggest gap was **no project import command** in the CLI — had to drop to raw `dataikuapi` Python. The initial CDISC app was poor because there was no reference doc guiding app UX design; after studying production apps (Alteryx, Reconciliation), the quality jumped dramatically.

### CLI Friction (4 issues)

| Issue | What Happened | Suggested Fix |
|-------|--------------|---------------|
| No `dku project import` command | Had to write raw Python (`client.prepare_project_import(f).execute()`) to import a .zip bundle | Add `dku project import FILE.zip [--key KEY]` command |
| Global flags position | Ran `dku app-designer get -P PROJ --url X --api-key Y` — failed because `--url`/`--api-key` are root-level, not subcommand-level | Error message should say "Global options (--url, --api-key) must come before the subcommand: dku --url X app-designer get" |
| No `scenario set-metadata` | Tried `dku scenario set-metadata BUILD_PIPELINE --description "..."` — command doesn't exist | Add `set-metadata` to scenario (it exists on dataset, dashboard, model, agent, folder but not scenario) |
| Scenario `set-definition` step types | Used `"type": "exec_recipe"` which doesn't exist — got `Unknown step type exec_recipe` with no list of valid types | Error message should list valid step types, or `--help` should document them |

### Skill & Doc Gaps (3 issues)

| Gap | Impact | Where to Fix |
|-----|--------|-------------|
| No app-designer content anywhere in skill or reference docs | Agent had zero guidance on how to build DSS apps — had to learn entirely from live inspection | Created `references/app-designer.md` (done this session) |
| `dku app-designer` and `dku app` not in SKILL.md command groups table | Agents won't discover the new commands | Add to SKILL.md command groups table + cheat sheet |
| Scenario step type reference missing | Had to guess `build_flowitem` vs `exec_recipe` — `exec_recipe` doesn't exist | Add scenario step types to `references/scenarios.md` or commands.md |

### Gotchas Hit (3 issues)

1. **`get_app_manifest()` fails on non-app projects**
   - **Tried**: `dku app-designer get -P PIERREPORTALRECONCILIATIONSANDBOX`
   - **Failed**: `IllegalArgumentException: Project is neither an app template nor an app instance`
   - **Fix**: Must call `enable` first (sets `useAppHomepage: true`) before `get` works
   - **Document in**: CLI error message should say "Run: dku app-designer enable -P PROJ" + app-designer.md reference

2. **Scenario step type `exec_recipe` doesn't exist**
   - **Tried**: `set-definition` with `"type": "exec_recipe"` to run a recipe
   - **Failed**: `Unknown step type exec_recipe`
   - **Fix**: Use `build_flowitem` with `MANAGED_FOLDER` type to build the recipe's output
   - **Document in**: scenarios.md reference doc + CLI error message should list valid types

3. **Upload behavior `INLINE_UPLOAD_REDETECT_AND_INFER` not discoverable**
   - **Tried**: Generic `UPLOAD_DATASET_SET_FILE` tiles without behavior
   - **Failed**: Worked but bad UX — didn't auto-detect schema
   - **Fix**: Learned from Reconciliation app that `INLINE_UPLOAD_REDETECT_AND_INFER` is the best behavior
   - **Document in**: app-designer.md (done this session)

### dataikuapi Discoveries

| Quirk | Details | Add to CLAUDE.md? |
|-------|---------|-------------------|
| `DSSAppManifest.save()` only works with `project_key` set | Getting manifest via `DSSApp.get_manifest()` sets `project_key` from the app_id prefix; via `DSSAppInstance.get_manifest()` it's `None` (read-only) | Yes |
| `DSSAppListItem` extends `dict` | `.get()` works directly on list items — no need for `._data` | Already known pattern |
| `prepare_project_import()` API | Returns a `ProjectImportHandle` with `.execute()` — not well documented, returns dict with `usedProjectKey` | Yes — needed for future `project import` command |
| `DSSAppManifest.raw_data` is mutable | Modifying the dict returned by `get_raw()` directly mutates `raw_data`, so `save()` persists changes without reassignment | Yes |

### Built-In Feature Misses

None — built CLI commands wrapping dataikuapi, correct approach.

### Recommended Changes (ranked by agent impact)

1. **Add `dku app-designer` and `dku app` to SKILL.md** — `dataiku-devkit/skills/dku-cli/SKILL.md` — add to command groups table + add app-designer cheat sheet entry.
2. **Improve error on non-app project** — `src/dku_cli/commands/app_designer.py` — catch `IllegalArgumentException` and suggest `dku app-designer enable -P PROJ`.
3. **Add app-designer reference doc to SKILL.md routing** — `dataiku-devkit/skills/dataiku/SKILL.md` — route agents to `references/app-designer.md` when building apps.

---

## [2026-04-07] Live testing app-designer tiles against DSS
**Status:** pending
**Recurring** (also seen: 2026-04-07 — extends previous app-designer entry)

### TL;DR
Live testing revealed that `enable` silently fails on fresh projects because `get_app_manifest()` requires `projectAppType=APP_TEMPLATE` in project settings first (fixed). Multiple tile types silently accept missing required fields via CLI but crash in the DSS UI (blank pages or 500 errors). `INLINE_PYTHON_RUN` has a DSS frontend scoping bug. `GUESS_TRAIN_DEPLOY` is commented out of the UI picker.

### CLI Friction (2 issues)

| Issue | What Happened | Suggested Fix |
|-------|--------------|---------------|
| `enable` fails on fresh projects | `get_app_manifest()` throws on REGULAR projects — must set `projectAppType=APP_TEMPLATE` first | Fixed: `enable` now auto-sets `projectAppType` |
| `add-tile` accepts missing required fields | Tiles without `datasetName`/`folderId`/`dashboardId` save OK but crash in UI | Add validation warnings for required fields per tile type |

### Gotchas Hit (5 issues)

1. **`enable` on REGULAR project** — Fixed: auto-sets `projectAppType=APP_TEMPLATE`
2. **`datasetName` required on all dataset tiles** — Without it, UI opens blank "New dataset" page. No error from CLI or DSS API. Document as **required** in reference doc (done).
3. **`folderId` required on folder tiles** — UI 500: `Required request parameter 'folderId' is not present`. Document as required (done).
4. **`INLINE_DATASET_EDIT` on UploadedFiles** — `Dataset is not editable: type UploadedFiles`. Only Filesystem/SQL datasets work. Noted in reference doc.
5. **`INLINE_PYTHON_RUN` frontend scoping bug** — `$parent.$index` in ng-switch-when resolves to wrong scope. Backend works (confirmed via direct API). No CLI fix possible.

### dataikuapi Discoveries

| Quirk | Details | Add to CLAUDE.md? |
|-------|---------|-------------------|
| `projectAppType` must be `APP_TEMPLATE` before `get_app_manifest()` | Set via `project.get_settings().get_raw()["projectAppType"] = "APP_TEMPLATE"` | Yes |
| `GUESS_TRAIN_DEPLOY` hidden in UI | Commented out at line 73 of apps.js — backend-only | Note in reference doc |
| `VARIABLE_DISPLAY` uses `${var_name}` | Calls `expandExpr()` at runtime. Fails on missing vars. | Yes |
| `includedManagedFolders` required for instances | Folder tiles need folder listed in `projectExportManifest.includedManagedFolders` | Yes |
| `sectionText` processed as markdown | Uses `from-markdown` directive, not raw HTML only | Yes |

### Recommended Changes (ranked by agent impact)

1. **CLI: validate required tile fields** — `app_designer.py` `_build_tile()` — warn on missing `--dataset`/`--folder`/`--dashboard` per tile type
2. **Reference doc: mark `GUESS_TRAIN_DEPLOY` as UI-hidden** — `app-designer.md`
3. **Reference doc: add `INLINE_PYTHON_RUN` known issue** — `app-designer.md`
4. **Reference doc: document `includedManagedFolders` for instances** — `app-designer.md`
5. **CLAUDE.md: add `projectAppType` quirk** — dataikuapi quirks section

---

## [2026-04-22] Built "SAS Portfolio Complexity Evaluator" app template on SOL_SAS_INVENTORY_SCORER
**Status:** pending

**Recurring**: `projectAppType = APP_TEMPLATE` gate already flagged in [2026-04-07] entries — confirms the fix (`dku app enable` auto-setting it) is the right direction. My session hit it again because I went via raw `dataikuapi` instead of a CLI verb, which reinforces the case for exposing `dku app set-manifest` / `dku app convert-to-template`.

### TL;DR
Three major blockers, all worth fixing: (1) `dku scenario set-definition` silently drops steps despite its help text promising otherwise; (2) there's no CLI path for app-template creation/manifest editing — had to hand-roll Python with undocumented `projectAppType=APP_TEMPLATE` flipping; (3) PUT `/app-manifest` returns opaque `AssertionError: null` for any missing top-level field or bad tile type, so you learn the accepted schema by trial and error.

### CLI Friction (6 issues)

| Issue | What Happened | Suggested Fix |
|-------|--------------|---------------|
| `dku scenario set-definition` lies | Help text says "Uses the full settings endpoint (DSSScenarioSettings.save) so params.steps, triggers, and reporters all persist." Code at `src/dku_cli/commands/scenario.py:276` calls `scenario.set_definition(new_def)` — the legacy header-only endpoint that silently drops steps. I wasted 3 round-trips before checking the source. | Change implementation to `s = scenario.get_settings(); s.get_raw().update(new_def); s.save()` — or at minimum, make the help text match reality. |
| `dku scenario get-definition` also uses legacy endpoint | After saving via dataikuapi, `get-definition` still returned 0 steps. Had to verify via Python. `params.steps` is invisible through the CLI. | Same as above — use `get_settings().get_raw()` so steps are visible. |
| No `dku app` verb for creating/editing app templates | `dku app` only has `list`, `get`, `list-instances`, `create-instance`. For app authoring you MUST drop to dataikuapi. Given the CLAUDE.md mission statement ("make AI coding agents excellent at operating DSS"), this is a big gap. | Add `dku app convert-to-template`, `dku app set-manifest -d @file.json`, `dku app unset-template`. Optionally `dku app add-tile` / `dku app add-section` for scripted building. |
| `dku folder list-files` doesn't exist | Typed the obvious name, got "No such command. Did you mean 'delete-files', 'delete-file'?" The actual command is `ls`. | Either add `list-files` as an alias for `ls`, or improve the did-you-mean to suggest `ls` (it's obvious from the noun pair). |
| `dku scenario run --no-wait` doesn't exist | Guessed the flag from common CLI convention. Actual: `--wait` (defaults to no-wait). Error was good ("Did you mean --wait?"), but default-no-wait with a `--wait` flag is unusual; `--no-wait` would be more discoverable. | Accept `--no-wait` as an explicit equivalent of the default, or document it prominently in `--help`. |
| `dku scenario run --wait` timed out at "outcome not available" despite scenario succeeding | Ran `scenario run --wait`, got "outcome not available for this scenario run. Maybe still running?" The run had already succeeded — the CLI gave up too early or checked the wrong endpoint. | Implement `--wait` using a proper poll of the run's final state (`DSSScenarioRun.get_info()` → `result.outcome`) with a sensible timeout. |

### Skill & Doc Gaps (5 issues)

| Gap | Impact | Where to Fix |
|-----|--------|-------------|
| Zero docs on how to programmatically create an app-as-recipe template | Took ~20 min of source-diving + trial-and-error to learn the sequence: `projectAppType = "APP_TEMPLATE"` → `PUT /app-manifest` with full required scalars. No skill mentions this. | Add a new reference doc `references/app-designer.md` in the `dataiku` skill covering: project-to-app conversion, required manifest scalars, valid tile types list, tile-to-object binding, export/instance feature flags. Link from the router in `dataiku/SKILL.md`. |
| Valid tile types not documented anywhere | I invented `DATASET_EXPLORE` (seemed plausible) and `MANAGED_FOLDER_BROWSE` (saw in one example); both rejected. Had to grep across all live apps to build the allow-list. | Same reference doc should include the authoritative list + callouts that `DATASET_EXPLORE` and `MANAGED_FOLDER_BROWSE` are NOT valid. |
| `projectAppType` field not mentioned anywhere in docs | This is the one-line gate between "my PUT works" and "opaque server AssertionError". | CLAUDE.md Critical Gotchas section and/or new app-designer reference doc. |
| AppManifest PUT required-fields list is undiscoverable | The endpoint returns `AssertionError: null` for any missing top-level scalar. There's no schema docs. | Ship a minimal working manifest template (JSON skeleton) in `references/app-designer.md`. |
| `dku scenario set-definition` silently succeeds — no warning | The CLI prints `Updated definition for scenario 'X'` even though steps were dropped. No way for an agent to know it failed without verifying independently. | Independent of the underlying endpoint fix: after save, read back `len(params.steps)` and warn if it differs from input. |

### Gotchas Hit (4 issues)

- **Tried**: `PUT /projects/SOL_SAS_INVENTORY_SCORER/app-manifest` with a full manifest body.
  - **Failed**: `jakarta.servlet.ServletException: Handler dispatch failed: java.lang.AssertionError, caused by: AssertionError: null`
  - **Fix**: Set `project_settings.raw["projectAppType"] = "APP_TEMPLATE"` and `save()` first; then the PUT succeeds.
  - **Document in**: CLAUDE.md Critical Gotchas + new `references/app-designer.md` + (if a `dku app convert-to-template` is added) a clear error message when the project isn't yet an app.

- **Tried**: Same PUT with the project now as APP_TEMPLATE, but minimal body (only `useAppHomepage`, `homepageSections`, `instanceFeatures`, `projectExportManifest`).
  - **Failed**: Same `AssertionError: null` — zero signal about what was missing.
  - **Fix**: Add `id`, `label`, `shortDesc`, `instantiationPermission`, `accessRequestsEnabled`, `limitedVisibilityEnabled`, `showInitials`, `imgPattern`, `tags`, `allowedMissingCodeEnvs`, `allowedMissingConnections`. Mirror from `client._perform_json("GET", "/apps/PROJECT_X/")` on any existing app.
  - **Document in**: reference doc with a ready-to-use skeleton.

- **Tried**: Tile type `"DATASET_EXPLORE"` (seemed natural for "let user explore this dataset").
  - **Failed**: `IllegalArgumentException: Invalid tile type "DATASET_EXPLORE"` (at least this error is prescriptive).
  - **Fix**: Use `DOWNLOAD_DATASET` with `exportParams.format.type = "csv"`. No "view this dataset" tile exists.
  - **Document in**: valid-tile-types table in reference doc.

- **Tried**: `dku scenario set-definition Build_X -d @file.json` and assumed it worked.
  - **Failed**: Steps count was 0 after save despite no error message.
  - **Fix**: Use dataikuapi directly: `scenario.get_settings()` → mutate `.get_raw()["params"]["steps"]` → `.save()`.
  - **Document in**: CLAUDE.md gotchas + fix the CLI so this workaround isn't needed.

### dataikuapi Discoveries

| Quirk | Details | Add to CLAUDE.md? |
|-------|---------|-------------------|
| `project.get_app_manifest()` fails if `projectAppType != APP_TEMPLATE` | No dedicated "convert" endpoint — flip the flag on project settings, then manifest endpoints start working. | Yes — high-value gotcha (recurring) |
| `/projects/X/app-manifest` supports only GET and PUT | POST returns 405. PUT is idempotent upsert once the project is APP_TEMPLATE. | Yes — reference doc |
| `DSSAppManifest.save()` only works if manifest was fetched via `project.get_app_manifest()` | `DSSApp.get_manifest()` returns manifest with `project_key=None` (unless app_id starts with `PROJECT_`), and `.save()` raises. | Worth a line |
| `DSSScenarioSettings.save()` (full) vs `DSSScenario.set_definition()` (header-only) | Two endpoints, wildly different behavior. The CLI picked the wrong one. | Already scheduled as CLI fix — CLAUDE.md line worth adding |

### Built-In Feature Misses

Nothing to report — pure app-template authoring. The task genuinely required app-manifest editing.

### Recommended Changes (ranked by agent impact)

1. **Fix `dku scenario set-definition` to actually use `DSSScenarioSettings.save()`** — `src/dku_cli/commands/scenario.py:276`. Currently calls `scenario.set_definition()` (legacy), contradicting its own docstring. Silently loses work for every agent authoring step-based scenarios via the CLI.
2. **Add `dku app convert-to-template` and `dku app set-manifest -d @file.json`** — closes the biggest capability gap. Every app-authoring workflow currently forces a drop to raw `dataikuapi`.
3. **Add `dataiku-devkit/skills/dataiku/references/app-designer.md`** — projectAppType flip, required manifest scalars with working skeleton, authoritative valid-tile-types list with rejection callouts, tile-binding fields, minimal end-to-end Python snippet. Link from router in `dataiku/SKILL.md`.
4. **Add CLAUDE.md Critical Gotcha**: "App manifest PUT requires `projectAppType = APP_TEMPLATE` on project settings first — otherwise PUT returns opaque `AssertionError: null`." With prescriptive fix snippet.
5. **Fix `dku scenario run --wait`** to actually wait for the run outcome (currently returns "outcome not available" even for successfully-completed runs). Poll `DSSScenarioRun.get_info()["result"]["outcome"]`.
6. **Make `dku scenario get-definition` use the full-settings endpoint** so agents can verify their step-based scenarios after saving without dropping to Python.
7. **Add `list-files` alias for `dku folder ls`** — nice-to-have.

---
