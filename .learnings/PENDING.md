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
