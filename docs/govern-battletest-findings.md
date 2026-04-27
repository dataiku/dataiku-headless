# Govern + Guarded-Mode Battletest Findings

Date: 2026-04-23. Target: `https://chrisgovern.se-platform.dataiku-sandbox.io` (DSS 14.5.1, **GOVERN node**, nodeId `ChrisGovern`).

## TL;DR

1. **Zero Govern-node support in `dku` today.** Every non-shared command (anything beyond `user`, `group`, `admin instance-info`, `admin usage`) fails with a raw `NotFound: /dip/publicapi/...` — no guidance that the agent hit the wrong node type.
2. **Guarded mode works as designed** for the two tiers in active use (DELETE, CASCADE) — text + JSON output, `--confirm-name` mismatch detection, rerun-command reconstruction all correct.
3. **Zero tier-4 ADMIN guards exist in the codebase.** The tier is defined and the block emitter is wired, but no command calls `guard(tier=Tier.ADMIN, ...)`. Several commands that *should* be tier-4 (bulk `user delete`, `connection delete`, `cluster delete`, global `api-key delete`, `group delete`) are sitting at tier-2 or tier-3.
4. **Govern introduces new governance primitives** (blueprints, artifacts, signoffs, role-assignments, blueprint permissions, custom pages, danger-zone schema saves) that map cleanly onto our existing tier framework but need an entire new command group to exist.

---

## 1. Govern node surface (from `dataikuapi.GovernClient`)

Source: installed SDK at `.venv/lib/python3.10/site-packages/dataikuapi/govern/`. Public docs at `/dss/11/python-api/govern/` and `/dss/latest/python-api/govern/` return 404 for per-page anchors — installed SDK is authoritative.

| Group | Primitives | Notes |
|---|---|---|
| Blueprints (user) | `list_blueprints`, `get_blueprint`, `.list_versions`, `.get_version(id)`, `.get_definition`, `.get_trace` | Lazy — must call `.get_definition()` to see a 404. |
| Blueprint designer (admin) | `create_blueprint`, `create_version(origin_version_id)`, `.get_definition().save(danger_zone_accepted=True)`, `.get_trace().set_status(DRAFT/ACTIVE/ARCHIVED)`, signoff-config CRUD | `danger_zone_accepted=True` is the direct analog of our CASCADE `--confirm-name`. |
| Artifacts | `create_artifact`, `get_artifact`, `.get_definition().save()`, `.delete()` | Composite ID; `list_*` → `ListItem` dicts, call `.to_artifact()` for handle. |
| Artifact search | `new_artifact_search_request(query)` → paged cursor; filters by blueprint, version, field value, archived status; sorts by name/workflow/field | Pagination mandatory — no bulk list. |
| Signoffs (workflow engine) | `list_signoffs`, `create_signoff(step_id)`, `update_status(...)`, `add_feedback`, `add_approval`, `delegate_feedback/approval`, recurrence config | `delegate_*` requires `GovernUserUsersContainer(login).build()`, not a raw login string. |
| Roles & Permissions (admin) | Roles CRUD, per-blueprint role assignments, blueprint permissions, default permissions | Govern RBAC is scoped per blueprint, not per project. |
| Custom pages | End-user list/get, admin CRUD, reorder | Govern-only. |
| Users / Groups / API keys / SSO | Same shape as `DSSClient` but `Govern*` classes | `user list`, `group list` already work on Govern because these endpoints are shared. |
| Uploaded files & time series | Per-blueprint-field attachment storage | `.delete(min_ts, max_ts)` on time-series = range delete → CASCADE territory. |
| Logs & audit (admin) | `list_logs`, `get_log`, `log_custom_audit(type, params)` | Same endpoint shape as DSS admin logs — already supported by `dku admin logs` (TEST). |

**Auth**: `GovernClient(host, api_key=...)` — API-key only. No user/password. Lives on a separate host (commonly `:11200`). **Cannot reuse a Design-node key.**

**Unique concepts** (no Design-node analog): blueprints, artifacts, signoffs/feedbacks/approvals, blueprint-scoped role assignments, custom pages, danger-zone schema edits.

## 2. Current CLI behavior against Govern node

Tested `uv run dku <cmd>` on the `chrisgovern` profile:

| Command | Result | Agent-facing quality |
|---|---|---|
| `whoami` | ✅ Works (user info is cross-node) | Good |
| `admin instance-info` | ✅ Works — correctly reports `nodeType: GOVERN` | Good |
| `admin usage` | ✅ Works | Good |
| `admin logs` | ❓ Untested — likely works (shared endpoint) | — |
| `user list`, `group list` | ✅ Works (shared endpoints) | Good |
| `project list` | ❌ `NotFound: /dip/publicapi/projects/` | **Bad** — no hint that this is a Govern-node problem |
| `dataset list`, `recipe list`, `scenario list`, `flow graph`, `bundle list`, `folder list`, `agent list` | ❌ 404 on project path | **Bad** — same generic 404 |
| `connection list` | ❌ `Cannot connect to DSS: NotFound: /dip/publicapi/admin/connections/` | **Worse** — message says "Cannot connect" which is false; DSS is reachable |
| `plugin list`, `code-env list` | ❌ 404 | **Bad** — 404 passthrough |

### Gap: no node-type awareness anywhere
- `dku auth login` does NOT persist `nodeType` to the profile (it prints the DSS version on success, reads nodeType implicitly, but doesn't store it).
- No existing command calls anything like `require_design_node()` / `require_govern_node()`.
- No prescriptive error tells an agent *"this instance is a Govern node — try `dku govern artifact list` instead."*

## 3. Guarded-mode battletest results

All tests below triggered the block BEFORE any API call (no destructive side effects).

### Tier 2 — DELETE
```
$ dku user delete __nosuchuser__
◆ BLOCKED by guarded mode — tier-2 (delete) blast radius.
AGENT INSTRUCTION:
  1. Stop. Do not retry automatically.
  2. Ask the user verbatim:
       "Delete DSS user '__nosuchuser__'?"
  3. If they say yes, run this exact command:
       dku user delete __nosuchuser__ --yes
  4. To authorise everything for this session, ask the user:
       export DKU_DANGEROUS=1
Exit code: 77  (safety_blocked)
```
✅ Perfect. Exit 77.

### Tier 2 — DELETE with `--errors json`
```json
{
  "error": {
    "code": "safety_blocked",
    "message": "Tier-2 op blocked: user.delete.",
    "exit_code": 77,
    "safety": {
      "tier": 2, "tier_label": "delete",
      "action": "user.delete",
      "subject": "user '__nosuchuser__'",
      "prompt_to_user": "Delete DSS user '__nosuchuser__'?",
      "rerun_with_confirmation": "dku --errors json user delete __nosuchuser__ --yes",
      "session_bypass": "DKU_DANGEROUS=1"
    }
  }
}
```
✅ JSON payload correctly preserves `--errors json` in the rerun command.

**⚠ Gotcha found**: `--errors json` is a global flag and must be passed **before** the subcommand. `dku user delete X --errors json` fails with "No such option: --errors". Worth documenting in SKILL.md — agents will get this wrong.

### Tier 3 — CASCADE
```
$ dku project delete __NOSUCHPROJECT__
◆ BLOCKED by guarded mode — tier-3 (cascade) blast radius.
AGENT INSTRUCTION:
  Prompt: "Permanently delete project '__NOSUCHPROJECT__'? This cannot be undone."
  Re-run: dku project delete __NOSUCHPROJECT__ --yes --confirm-name __NOSUCHPROJECT__
Exit code: 77
```
✅

### Tier 3 — name mismatch
```
$ dku project delete __NOSUCHPROJECT__ --yes --confirm-name WRONG
◆ BLOCKED — tier-3 cascade requires --confirm-name to match the target.
Expected: --confirm-name '__NOSUCHPROJECT__'
Got:      --confirm-name 'WRONG'
```
✅

### Tier 4 — ADMIN
**Not testable — zero tier-4 call sites in the codebase.** The tier and emitter are defined in `safety.py` but no command uses them.

### Codebase audit: tier distribution across 48 destructive commands
| Tier | Count | Examples |
|---|---|---|
| CASCADE | 2 | `project delete`, `connection delete` |
| DELETE | 46 | everything else including `user delete`, `group delete`, `api-key delete`, `cluster delete`, `connection delete` at tier 2 where some should be higher |
| ADMIN | **0** | — |

## 4. Concrete gaps & proposed fixes

### P0 — Node-type awareness (2-3 days)
1. On `dku auth login`, call `get_instance_info()` and persist `node_type` to the profile TOML (`design` / `automation` / `govern` / `deployer` / `apinode`).
2. Add `helpers.require_node_type(ctx, allowed: set[str])`. Every command that hits a project-scoped endpoint calls `require_node_type(ctx, {"design", "automation"})`.
3. Prescriptive error:
   ```
   ◆ This command requires a Design or Automation node. Your profile is pointed at a GOVERN node.
   Try:  dku govern --help
   Or switch profile: dku auth use <design-profile>
   ```
4. Fix `connection list` error wording — "Cannot connect to DSS" is wrong; rewrite to "Connection listing is not available on GOVERN nodes."

### P0 — Tier-4 ADMIN adoption (1 day)
Migrate genuinely instance-wide destructive ops to tier 4:
- `cluster delete` — kills compute for every user of the cluster → ADMIN
- `api-key delete` (global keys) → ADMIN
- `group delete` — system groups like `administrators` are catastrophic → ADMIN when group is a system group, else DELETE
- `connection delete` (already CASCADE, arguably ADMIN given cross-project blast radius)
- Write tests for the ADMIN path (currently uncovered).

### P1 — New `dku govern` command group (~1 week for MVP, 2 weeks full)

MVP (read-only + basic workflow):
```
dku govern instance-info
dku govern blueprint {list, get, versions}
dku govern artifact  {list/search, get, create, edit, delete}
dku govern signoff   {list, get, update-status, add-feedback, add-approval}
dku govern role      {list, get}
dku govern role-assignment {list, get}
dku govern custom-page {list, get}
dku govern uploaded-file {upload, download, delete}
dku govern log       {list, get, custom-audit}
```

Full (admin ops):
```
dku govern blueprint {create, delete} (ADMIN)
dku govern blueprint-version {create, save, save --danger-zone, set-status, delete}
     danger-zone save = CASCADE with --confirm-name
dku govern role {create, delete} (CASCADE — cross-blueprint blast)
dku govern role-assignment {create, delete}
dku govern blueprint-permission {list, set, delete}
dku govern custom-page {create, edit, delete, reorder}
dku govern time-series {push, get, delete --range} (range-delete = CASCADE)
dku govern user / group / api-key  → reuse existing commands, routed via GovernClient when profile.node_type == "govern"
```

Auth wiring — extend `helpers.get_client_from_ctx(ctx, node_type="govern")` to return `GovernClient` when profile says govern; existing `DSSClient` path stays the default. One auth module, two client constructors.

### P1 — Agent-facing skill + reference updates
- `dataiku-devkit/skills/dku-cli/SKILL.md`:
  - Cheat sheet rule: "If you see `NotFound: /dip/publicapi/projects/`, the profile is a GOVERN node — switch profile or use `dku govern …`."
  - Cheat sheet rule: "Global flags (`--errors json`, `--profile`, `--dangerous`) go BEFORE the subcommand."
  - Add Govern section to the Command Groups table.
- `dataiku-devkit/skills/dku-cli/references/commands.md`: document every new `dku govern ...` command.
- `dataiku-devkit/skills/dataiku/references/govern.md` (NEW): platform knowledge doc on blueprints vs artifacts vs signoffs, danger-zone semantics, role-per-blueprint model, artifact-field types (uploaded-file, time-series). Linked from `dataiku/SKILL.md` router.
- New subagent `agents/govern-explorer.md` — maps blueprint catalog + artifact state for a new Govern node (analog of `dss-explorer`).

### P2 — CLAUDE.md gotchas (as each fix lands)
- Govern node has no projects/datasets/recipes — use `dku govern artifact`.
- `dku auth login` should always persist `node_type`; agents should `dku whoami --show-node-type` (new flag) before running project-scoped commands.
- `--errors json` must come before the subcommand.
- Govern `danger_zone_accepted=True` on blueprint-version save maps to our `--confirm-name` flag.
- `delegate_*` requires `GovernUserUsersContainer(login).build()` — wrap in the CLI so agents pass plain logins.

## 5. Priority order

1. **P0 Node-type guard** — single biggest agent failure mode today. 1 PR.
2. **P0 Tier-4 adoption** — tightens guarded-mode story before we add more destructive commands via Govern. 1 PR.
3. **P1 `dku govern` MVP** (read-only + signoffs) — unlocks the whole governance story. 2-3 PRs.
4. **P1 Skill/reference updates** — shipped alongside each Govern PR, not at the end.
5. **P1 `dku govern` admin ops** — after MVP validated on a real Govern catalog.
6. **P2 `govern-explorer` subagent** — once enough commands exist to script a real catalog tour.

## Appendix: tier mapping for Govern ops

| Operation | Tier | Why |
|---|---|---|
| `artifact delete`, `signoff feedback delete`, `signoff approval delete`, `uploaded-file delete` | DELETE | single-object scope |
| `artifact create`, `signoff update-status`, `add-feedback`, `add-approval`, `delegate-*` | WRITE | reversible, workflow mutations |
| `blueprint-version delete`, `custom-page delete`, `role delete`, `role-assignments delete`, `blueprint-permissions delete`, `time-series delete --range` | CASCADE | wipes many dependent artifacts/rows |
| `blueprint delete`, `blueprint-version save --danger-zone`, `set-license`, bulk `user delete`, `provision-users` | ADMIN | instance-wide blast radius, schema-breaking |
