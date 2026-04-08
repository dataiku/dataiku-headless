# Pending Learnings

Insights from past sessions. Copy relevant entries to the dataiku-cli repo's `.learnings/PENDING.md` to process them into fixes via `/cli-improvement`.

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
