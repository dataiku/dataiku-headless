# CLAUDE.md — dku-headless

Agent-facing guide for working *inside a clone of this repo*. Two very different agents open it:

- **Operators** — you want to *use* the kit against a live DSS instance (build, inspect, verify
  Dataiku projects). **Do not read the source.** Install/enable the plugin or MCP server
  (`README.md` → [Install](README.md)), load the `dataiku-skills/dataiku-headless/` skill, and
  work through the MCP tools. `dataiku-skills/dataiku-headless/SKILL.md` is the router, its
  `playbooks/` are the task recipes, `references/tool-index.md` is the tool list. Stop here — the
  rest of this file is not for you.
- **Contributors** — you are changing this codebase. The rest is for you.

## Tenet

**Reads for grounding, Cobuild for building, verification stays with the agent.** This server
gives a coding agent a deliberately narrow job: supervise Cobuild (the AI builder inside DSS).
Read-only tools ground and verify; every in-project mutation is delegated through a Cobuild
conversation; only three deterministic executions and a handful of bootstrap writes act directly.
The tool surface *is* that division of labor — preserve it.

## Principles

- **One fixed surface.** No exposure modes, no search mode. The only runtime trimming is transport
  gating (`DKU_MCP_TRANSPORT` = `stdio` vs `streamable-http`). The exact registered set is pinned
  by `tests/test_smoke.py` — the surface is a contract, not an accident.
- **No direct in-project write tools.** There is intentionally no `create_recipe` / `update_dataset`.
  Project building routes through `dataiku_mcp/tools/cobuild.py`. Full-CRUD per-object surfaces live
  upstream in the agent-dev-kit, not here.
- **MCP is a thin adapter.** Validate boundary invariants (non-empty required lists, enum-like and
  destructive-intent params); let DSS validate deeper domain constraints. No `confirm*` boolean flags
  — destructive intent is a semantic param (`overwrite`, `drop_data`, `mode="replace"`).
- **Unreadable evidence is never a pass.** The audit engine is read-only and FAIL-severity: a check
  that errors or times out degrades to `error`, not `skip`, and blocks the gate.
- **One fact, one home.** `CODING_STANDARDS_AND_STRUCTURE.md` is canonical for conventions; this file
  points there, never restates it.

## Code map

| Path | Role | Rule |
|---|---|---|
| `dataiku_mcp/__init__.py` | Server construction + tool registration + transport gating | Every `tools/*` module is imported here to register; the `remove_tool` block at the bottom is the sole transport-gating point. |
| `dataiku_mcp/tools/*.py` | One module per DSS object family (datasets, recipes, flow, jobs, scenarios, connections, …) | Read/inspect tools + the sanctioned direct executions/bootstrap writes only. `async def` handlers; blocking SDK calls stay inside `run_blocking(...)`. |
| `dataiku_mcp/tools/cobuild.py` | Cobuild conversation state machine (delegation, turn retention, delete confirmations) | The **only** in-project write path. A blocking turn runs in a daemon thread whose `Future` survives a client timeout — poll, never re-send. |
| `dataiku_mcp/tools/utils/conversation_store.py` | Durable Cobuild registry (`conversations.json` under `DKU_MCP_STATE_DIR`) | Source of truth; the in-memory dict is a hot cache. Resolve the state dir at call time; writes atomic (`mkstemp` + `os.replace`, `0600`). |
| `dataiku_mcp/tools/utils/audit_engine.py` | Read-only project audit (`tools/project_audit.py` is the tool wrapper) | Never recompute metrics, never mutate DSS. Every failing check carries a `fix` re-pointed at this server's actions (a Cobuild prompt or a named MCP tool) — never `dku`/other-harness syntax. |
| `dataiku_mcp/tools/utils/redaction.py` | Secret-like value redaction | Used by connection info/tests and project-variable reads. One detection heuristic, per-surface placeholder. |
| `dataiku_mcp/tools/utils/validation.py` | Reusable input validation helpers | Put structured/enum/destructive-param validation here; reuse from tool modules, don't hand-roll local validators. |
| `dataiku_mcp/config.py`, `config_mcp.py` | Instance config resolution + MCP env settings | Config search order and auth resolution are documented in `README.md`; don't hardcode instance-specific defaults. |
| `cli/cli.py` | `dataiku-headless` entry point (`serve`, default = serve) | Thin Typer wrapper over `run_server()`. Skills ship via the harness plugins, not a CLI copy command. |
| `bin/run_mcp.sh` | `uv run python -m dataiku_mcp` launcher | Standalone/local run only. |
| `dataiku-skills/dataiku-headless/` | The one agent skill (`SKILL.md` router, `soul.md` judgment, `playbooks/`, `references/`) | `references/tool-index.md` is **generated** — never hand-edit. |

## Adding or changing a tool

1. **No new direct in-project write.** If Cobuild has a coverage gap, note it in the skill — do not
   add an MCP write tool around it. A new direct write is justified only if it is cross-project,
   instance-level, or must precede a project/conversation (the four bootstrap writes) — or it is a
   deterministic execution of an existing asset (`build_datasets`, `run_recipe`, `run_scenario`).
2. Verify the `dataikuapi` method exists before wrapping it; keep the handler `async`, blocking calls
   inside `run_blocking(...)`, and reuse `tools/utils/validation.py`.
3. **Update the allow-list on purpose.** Edit `EXPECTED_NON_COBUILD` (or `KNOWN_COBUILD`) in
   `tests/test_smoke.py` for any add/remove/rename. It is the guard.
4. If the tool reads the server's local filesystem, add it to the transport-gating block in
   `dataiku_mcp/__init__.py` (removed under `streamable-http`).
5. Regenerate the tool-index: `uv run python scripts/generate_tool_index.py` (commit the result).
6. Update `README.md`'s tool counts (currently **53 non-cobuild + 5 cobuild**).
7. Update the skill if behavior or payloads changed; rerun the skill-integrity checks (below).

## Changing the skill

- Routing is by `SKILL.md` frontmatter `description` — there is no separate root routing file.
  Judgment lives in `soul.md`, task recipes in `playbooks/`, facts in `references/`.
- Never hand-edit `references/tool-index.md`; regenerate it.
- `scripts/check_skill_links.py` validates frontmatter, routing completeness, and dead *file*
  references (path-qualified refs must resolve; duplicate basenames are an error).
- `scripts/check_skill_tool_names.py` requires every backticked, tool-shaped token to resolve to a
  real registered tool or the explicit non-tool allowlist.

## What not to do

- Don't add a direct create/update/delete tool for an in-project asset — route through Cobuild.
- Don't add `confirm*` boolean flags; model destructive intent as a semantic param.
- Don't hardcode instance-specific values (project keys, model/LLM ids, code-env or connection names)
  as defaults in tools or skills.
- Don't hand-edit the generated tool-index, or change the tool surface without updating the allow-list.
- Don't cache `DKU_MCP_STATE_DIR`, re-send a timed-out Cobuild turn, or leave `allow_edit_project`
  defaulting to anything but `false`.
- Don't emit `dku`/other-harness syntax in audit `fix` text — only this server's action model.
- Don't mix raised exceptions and serialized `{"error": ...}` for the same failure class in one tool.

## Testing

Exactly what CI runs (`.github/workflows/ci.yml`) — no live DSS needed:

```bash
uv run ruff check .                              # lint (rules pinned in pyproject.toml)
uv run pytest -q                                 # smoke + surface + cobuild + context + audit
uv run python scripts/check_skill_links.py       # skill file/routing integrity
```

`pytest` also enforces the other two scripts (`tests/test_tool_index.py` re-renders the tool-index and
diffs it; `tests/test_skill_links.py` runs the tool-name checker). Release automation must run the
same repository gates against the exact release commit. To exercise the server end to end:
`./bin/run_mcp.sh`, or inspect interactively with `uv run --with "mcp[cli]" mcp dev -m dataiku_mcp`.

## Commits & release

Conventional Commits via Commitizen (`type(scope): subject`). Validate with
`uv run cz check --rev-range origin/main..HEAD`; `uv run cz bump` derives the version and updates
`CHANGELOG.md`. The PR checklist is in **`CODING_STANDARDS_AND_STRUCTURE.md`**. The release trigger,
verification, build, and publication policy live in **`.github/workflows/release.yml`**.

## Doc index

| Doc | Open when |
|---|---|
| `README.md` | Product story, install, tool-surface counts, transport gating, config/auth resolution |
| `CODING_STANDARDS_AND_STRUCTURE.md` | Canonical conventions — tool-surface/write-routing rules, async style, skill contract |
| `.github/workflows/release.yml` | Release trigger, verification, build, and publication policy |
| `dataiku-skills/dataiku-headless/SKILL.md` | The skill router — permanent rules + task→playbook table |
| `dataiku-skills/dataiku-headless/playbooks/` | One task-complete recipe per task kind |
| `dataiku-skills/dataiku-headless/references/tool-index.md` | Every tool name with a one-line purpose (generated) |
