# CLAUDE.md — Dataiku DevKit

## Quick Start

```bash
uv sync                    # Install deps
uv run pre-commit install  # Install git hooks (commitlint, ruff, whitespace fixes)
uv run pytest -v           # Run tests (all must pass)
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run dku                 # Run CLI locally (dev, uses .venv)
uv build                   # Build wheel
```

### Reinstalling the global `dku` CLI

The globally-installed `dku` tool (via `uv tool install`) caches its build. After merging changes to the main repo, you must force-reinstall to pick them up:

```bash
uv tool install --from . dku-cli --force --reinstall
```

**`--force` alone is not enough** — it reuses the cached wheel. `--reinstall` rebuilds from source. Without both flags, `dku folder create --help` etc. will show "No such command" even though the code is on disk.

## Mission

**This repo exists to make AI coding agents excellent at operating Dataiku DSS.** Every change — CLI code, skill docs, error messages, tests — is evaluated by one question: *does this make agents more successful?*

We ship two components:

1. **`dku` CLI** — a `kubectl`-style tool wrapping `dataikuapi`. Replaces throwaway Python scripts with composable shell commands agents chain with `&&`.
2. **Agent skills & knowledge** — 2 skills, reference docs, and 3 subagents that teach agents how to operate DSS.

**Private repo — NOT on PyPI.** Install from a local clone — see [Distribution](#distribution).

---

## Strategy

Five levers make agents better:

1. **Progressive disclosure in skills** — Cheat sheet (top 30 lines, always loaded) → full SKILL.md → `references/*.md`. The cheat sheet must prevent the top 6 failure modes.
2. **CLI as agent co-pilot** — `--help` is documentation; error messages are instructions with the fix command; idempotent where possible.
3. **Built-in features first** — Visual recipes > GenAI recipes > AutoML > Agents/Knowledge Banks > Scenarios > SQL > Python. Python is the escape hatch, not the default.
4. **Gotchas in three places** — CLI error message (recovery) + SKILL.md cheat sheet (prevention) + CLAUDE.md below (development). All three or it will be missed.
5. **Benchmark-driven** — 9-tier benchmark (192 scenarios) measures agent success. See `benchmark/README.md`.

---

## Development Workflow

When you receive benchmark feedback:

1. **Capability check first** — Could a visual recipe, model, agent, or knowledge bank replace the Python recipe the agent wrote?
2. **Categorize**: built-in capability gap > CLI bug > skill doc gap > test gap > not actionable
3. **Fix in all three places** — CLI error message + skill doc + CLAUDE.md gotcha
4. **Verify against `dataikuapi`** — Never invent APIs. Read the source in `.venv/lib/*/dataikuapi/`.
5. **Run tests — ALWAYS, no exceptions** — `uv run pytest -v` after ANY CLI code change. Write new tests for new commands. Test error paths too, not just happy paths. Never skip this step.
6. **Test against live DSS (MANDATORY)** — Unit test mocks are guesses until verified. After unit tests pass, run every new/changed command against the real DSS instance with `uv run dku <command>`. Use projects **ADVISORGPT** (Snowflake datasets, recipes, flow graph) or **AGENTTEST**. Verify:
   - Table output shows real data, not blank columns (field name mismatches cause this)
   - JSON output field names match what DSS actually returns
   - Empty results produce helpful messages (no usages, no schemas, etc.)
   - Wrong inputs (bad column name, non-SQL connection for schemas) produce prescriptive errors
   - If live testing reveals mismatches, fix them BEFORE committing
7. **Format before committing** — `uv run ruff format .` (CI runs `ruff format --check` and will reject unformatted code)

---

## CLI Architecture

```
typer (CLI framework)
  └─ rich (terminal formatting)
  └─ dataikuapi (DSS API client)
  └─ keyring (credential storage)
  └─ platformdirs (config file locations)
  └─ tomli/tomllib (TOML parsing)
```

**Branding:** Uses `◆` (black diamond) as icon. Must wrap in Rich markup (`[blue bold]◆[/blue bold]`) in Typer help strings or Typer strips it.

### Pattern: `dku <noun> <verb>`

Every command follows the same flow:
1. Resolve auth (flags → env → keychain → file) via `helpers.get_client_from_ctx()`
2. Resolve project (flag → env → config) via `helpers.resolve_project()`
3. Call `dataikuapi` methods
4. Format output via `output.py`

### File Layout

| File | Responsibility |
|---|---|
| `main.py` | Root Typer app, global options (`--url`, `--api-key`, `--profile`, `--quiet`), sub-command registration, `whoami` |
| `brand.py` | `◆` icon, `version_string()`, `welcome()`, `status_ok()`/`status_err()` |
| `helpers.py` | `resolve_project()`, `get_client_from_ctx()`, `read_json_input()` — eliminates duplication |
| `config.py` | TOML config read/write via `platformdirs` |
| `auth.py` | Keyring + file fallback credential storage |
| `client.py` | Auth resolution → `DSSClient` factory |
| `output.py` | All rendering: `render()` for table/json/csv, `render_raw()` for single dict/list, `success()`/`error()`/`warn()`/`info()` + quiet mode |
| `errors.py` | `dataikuapi` exception → user-friendly message + exit code. **Every error must tell the agent what to do next.** |
| `commands/*.py` | One file per noun. Never touches presentation directly — always uses `output.py` |

---

## Development Conventions

- **One file per noun** in `commands/`. File named `{noun}.py` (except `auth_cmd.py` and `config_cmd.py` to avoid stdlib collisions).
- **All formatting through `output.py`** — command modules never import `rich` directly.
- **Project resolution** via `helpers.resolve_project()`: `--project` flag → `DKU_PROJECT` env → `config.toml` default → error.
- **Client creation** via `helpers.get_client_from_ctx(ctx)` — extracts global opts from `ctx.obj`.
- **Global options** (`--url`, `--api-key`, `--profile`, `--quiet`) are on the root app and passed via `ctx.obj`.
- **Tests mock `DSSClient`** — no real DSS connection in unit tests. Use `patch_client` fixture.
- **Version** is single-sourced from `src/dku_cli/__init__.py` via `[tool.hatch.version]` in `pyproject.toml`.
- **Error messages are prescriptive** — every `except` block must tell the agent the next command to run, not just what went wrong. Use `exit_with_error()` with `details=[]` for multi-line guidance.
- **Agent commands resolve by name or ID** — `helpers.resolve_agent()` tries `get_agent(ref)` first (by ID), falls back to `list_agents()` name match. All agent commands use this.
- **Text input helper** — `helpers.read_text_input(value)` reads from literal string, `@file.txt`, or stdin (`-`). Used by `set-prompt`, same pattern as `set-code`.

---

## DevKit: Skills, Agents & Plugin

```
dataiku-devkit/
├── skills/
│   ├── dataiku/               # Platform knowledge router
│   │   ├── SKILL.md           # Routes to correct reference doc based on task
│   │   └── references/*.md    # Deep platform knowledge (progressive disclosure layer 3)
│   └── dku-cli/               # CLI operations and composability patterns
│       ├── SKILL.md           # THE primary agent interface — cheat sheet + patterns + gotchas
│       └── references/        # CLI command reference
└── agents/                    # Subagents for complex tasks
    ├── plugin-reviewer.md
    ├── dss-explorer.md
    └── tool-designer.md
.claude-plugin/            # Plugin manifest for Claude Code marketplace
```

### Skill Quality Standards

When editing skills, **progressive disclosure is non-negotiable**:

| Layer | File | What goes here | What does NOT go here |
|-------|------|----------------|----------------------|
| 1 | SKILL.md cheat sheet (top 30 lines) | Failure prevention rules, one line each | Command syntax, flag details |
| 2 | SKILL.md body | Command Groups table (verb names only), chaining patterns for new workflows | Per-command notes, flag descriptions, API details |
| 3 | `references/commands.md` | Full command syntax, all flags, usage notes, API quirks | — (this is the detail layer) |

**Rules:**
- **SKILL.md is loaded into every conversation.** Every line costs tokens. Be ruthless about what earns a spot.
- **Never add per-command documentation to SKILL.md.** That's what `references/commands.md` is for. SKILL.md gets the verb in the Command Groups table + a chaining pattern IF the command enables a new workflow.
- **Cheat sheet** (top 30 lines): Must prevent the top failure modes. One line per rule. If you add a gotcha to CLAUDE.md, ask: does the cheat sheet need a rule too?
- **Examples**: Every example must be copy-paste-runnable. Include `-P PROJ` and all required flags.
- **Gotchas table**: Scannable — symptom in one column, fix in another. Agents pattern-match on error messages.

---

## Safety & Guarded Mode

**`dku` is guarded by default.** Every destructive command calls `safety.guard()`. There is NO other path — adding a new destructive command without calling `guard()` is a bug.

### The primitives

- **`src/dku_cli/safety.py`** — the only module that emits `AGENT INSTRUCTION` blocks and exits 77.
  - `Tier.READ / WRITE / DELETE / CASCADE / ADMIN` (IntEnum).
  - `guard(ctx, *, tier, action, subject, yes, target_id=None, confirm_name=None, i_know=False, prompt=None)` — the only call every destructive command makes.
- **Exit code 77** (`SAFETY_BLOCKED_EXIT`) is reserved for safety blocks. Do NOT reuse it.
- **Global flag `--dangerous`** + **env `DKU_DANGEROUS=1`** + **`config.toml` `dangerous_mode=true`** all disable tier 2–3 guards. Tier 4 (admin) is never bypassable.

### Tiers — call-site rules

| Tier | Use when the command … | Required flags |
|---|---|---|
| `READ` / `WRITE` | Lists, creates, reversible updates | No guard call needed |
| `DELETE` | Deletes one resource or wipes its data | Pass `yes=yes` |
| `CASCADE` | Is irreversible, touches many resources, or uses a `--force` override | Pass `yes=yes`, `target_id=<id>`, `confirm_name=confirm_name` |
| `ADMIN` | Reserved for instance-wide admin mutators | Pass `yes`, `target_id`, `confirm_name`, `i_know` |

### When adding a new destructive command

1. Pick the tier. If in doubt between DELETE and CASCADE, ask: *can this destroy work the user did not explicitly name in the command*? If yes → CASCADE.
2. Add `yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard")`.
3. For CASCADE: also add `confirm_name: str = typer.Option(None, "--confirm-name", help="Must match <TARGET> to proceed.")`.
4. Call `guard(ctx, tier=Tier.X, action="noun.verb", subject="human-readable '{name}' in {scope}", yes=yes, ..., prompt="User-facing question ending in a question mark?")`.
5. Write the `prompt=` from the user's perspective — it's shown to the human verbatim by the agent. Start with the verb, name the target, end with a question.
6. Write tests: (a) blocks without `--yes` (exit 77), (b) succeeds with `--yes`, (c) tier-3 rejects mismatched `--confirm-name`, (d) `DKU_DANGEROUS=1` bypasses (tier 2) or still requires `--confirm-name` (tier 3).

### Existing agent-facing artifacts that mention safety

- `dataiku-devkit/skills/dku-cli/SKILL.md` — cheat sheet rule 18 + the "Deletion Commands (Safety Guards)" section.
- `dataiku-devkit/skills/dku-cli/references/commands.md` — "Safety Modes & Exit Code 77" section.
- CLI error messages — `AGENT INSTRUCTION:` block emitted from `safety._emit_block` / `_emit_cascade_name_mismatch` / `_emit_admin_refusal`.

---

## Critical Gotchas

**Rule: Every gotcha below MUST also exist in `dataiku-devkit/skills/dku-cli/SKILL.md` gotchas table AND be caught with a prescriptive error message in the CLI code.**

### Foreign / Shared Datasets in `list_datasets`
`dataikuapi.DSSProject.list_datasets()` defaults `include_shared=False` — the `?foreign=False` API param silently drops datasets shared in from other projects, so `dku dataset list` would return 0 even when the UI shows foreign datasets at `/projects/X/foreigndatasets/...`. The CLI now defaults to `include_shared=True` and exposes `--own-only` to opt out; output includes a `projectKey` column so agents can spot foreign rows. Same fix applied to `dku agent-tool list` (its SDK method has the same `include_shared` parameter). When adding any new list command, check whether `dataikuapi.DSSProject.list_*` exposes `include_shared` — if yes, default it on and surface `projectKey` in output.

### Dataset Create + Upload
`dku dataset create` defaults to Filesystem, which does NOT support `dku dataset upload`. Use `--type UploadedFiles` for anything being uploaded via CLI.

`dku dataset delete` and `dku recipe delete` prompt by default but support `--yes` / `-y` for non-interactive deletion. `dku project delete` requires `--confirm`, `--yes`, or `-y`.

### Code Recipe Create + Connection
`dku recipe create` for code recipes fails if the project has no default managed connection. Always pass `--connection` / `-c` when creating Python/SQL recipes in projects without a default managed connection. Use `dku connection list` to find available connections (`filesystem_managed` is the most common). If `connection list` is unavailable, inspect an existing dataset with `dku dataset get-definition DS -P PROJ -o json | jq -r '.params.connection'`. Cross-project recipe inputs use `PROJECT_KEY.DATASET_NAME`. Visual recipe shortcuts auto-create outputs and don't need `--connection`.

### Dataset Verification + Schema Reality
`dku dataset head -o json` returning `[]` means the dataset has 0 rows, not an error. Always verify built outputs with `dku dataset head OUTPUT -P PROJ -n 5` and inspect actual columns with `dku dataset schema OUTPUT -P PROJ` before assuming a recipe worked. Wiki plans and schema docs can lag the real dataset.

### Python Recipe Numeric IDs
ID columns from external datasets may contain nulls or non-numeric values. Never cast directly with `.astype("int64")`; use `pd.to_numeric(..., errors="coerce")`, `dropna`, then cast, or the recipe will fail with `IntCastingNaNError`.

### Snowflake: concat Aggregation + Bigint Precision
`--agg "col:concat"` in `create-group` compiles to Snowflake's `LISTAGG()`, which has a per-group result size limit. Large text/JSON columns (200+ chars per row, multiple rows per group) fail with error 300002. Fix: visual group for numeric aggs only, Python recipe downstream for JSON/text merging. Also: pandas loads Snowflake bigints as float64, losing precision for values > 2^53. Visual recipes preserve full precision. Python recipes should cast via string, not `pd.to_numeric().astype("int64")`.

### Plugin Webapp Backend
DSS injects `app` (Flask) globally into `backend.py`. NEVER create your own `app = Flask(__name__)` — it breaks `/__ping`. Import from `dataiku.customwebapp`, not `dataiku.webapp`. Folder is `webapps/`, not `custom-webapps/`. `webapp.json` needs `hasBackend: true`, `noJSSecurity: true`.

### Code Environments on Python 3.11
NEVER use `installCorePackages: true` — installs `pandas==0.23.4` which fails on Python 3.11. Use `installCorePackages: false` + explicit `requirements.txt`: `pandas>=2.0,<3`, `numpy>=1.22,<3`, `python-dateutil>=2.8,<3`, `requests>=2.28,<3`. Include all four even if not used directly. If `create_code_env()` fails, the broken env persists — delete it before retrying.

### GREL Formula Quirks
`log()` = base-10, `ln()` = natural log (despite `exp()` being base-e). `numval()`/`strval()`/`val()` require QUOTED column names — `numval("col")` works, bareword `numval(col)` silently returns empty. `replace(s, "pat", ...)` is literal substring; regex needs `/pat/` delimiters. Formula columns default to STRING — always run `apply-schema` after adding formula steps.

### Agent Tool Patterns
Trace API: `trace.attributes[key] = value` — NOT `set_attribute()` or `add_metadata()`. `invoke()` input is at `input.get("input", {})`, not root. Subprocess tools MUST set `stdin=subprocess.DEVNULL` + `env["CI"] = "true"` + `env["NO_COLOR"] = "1"`.

### Agent Versioning: Active Version + saved-model API
Agent settings live in `raw['versions']` (a list of dicts). The legacy CLI behavior of `set-prompt`/`set-llm`/`add-tool` was to mutate the dict whose `versionId` matches `raw['activeVersion']` and PUT the whole agent. That works, but is lossy — every prompt iteration overwrites the previous one with no rollback. Project mission rule: prompt iteration is a top failure mode for agents, so the CLI now offers `--new-version` (deep-copies the active version and appends as `vN+1`) and `--activate` (flips the pointer). Also surfaces `list-versions`, `create-version`, `set-active-version` as standalone verbs that mirror `dku semantic-model`. **Hard gotcha:** setting `raw['activeVersion'] = new_vid` and saving does NOT persist on the server. The only path that flips active is `project.get_saved_model(agent_id).set_active_version(new_vid)` — agents are saved models server-side. `_activate_version()` in `commands/agent.py` is the canonical helper; never write `raw['activeVersion'] = X` from CLI code. When adding a new agent mutator command, default to in-place for backwards compatibility, accept `--new-version`/`--activate`, validate that `--activate` requires `--new-version` (else silent no-op).

### SVA Block Graph (DSS 14.5+)
Agent type MUST be `STRUCTURED_AGENT` for block graphs. `TOOLS_USING_AGENT` silently drops blocks. Every CORE_LOOP/LLM_REQUEST block needs explicit `llmId`. Every SAVE_TO_STATE block needs `outputKey`. Empty string in SET_STATE_ENTRIES `value` crashes CEL — use `"''"`.

### Date Formatting in Prepare Recipes
`DateFormatter`, `DateTruncate`, `UNIXTimestampParser` **all exist** on DSS 14.5 (verified against `dip/src/.../shaker/processors/time/`). The agent trap is wrong param names: they use `inCol`/`outCol` (NOT `column`/`outputColumn` from older docs), and DSS returns a misleading `Empty column name` error otherwise — the `dku recipe add-step` CLI catches this pre-send. Other traps: `DateTruncate` param is `datePart` (values `YEAR`/`MONTH`/`DAY`/`HOUR`/`MINUTE`/`SECOND`) and defaults to `YEAR` if missing. `UNIXTimestampParser` uses `milliseconds` BOOLEAN, not `unit` string. What actually *doesn't* work: GREL `formatDate()` and `toDate()` do not exist; GREL `toString(date, "format")` is a no-op; `DateParser` without `outCol` silently produces all nulls. ISO 8601 DateParser format: use `Z`/`z` pattern, NOT `XXX`.

### Chart Column Names
Not validated server-side — wrong column names save but render blank charts. Verify with `dku dataset schema DS -P PROJ` first. Dashboard tiles at `pages[i].grid.tiles`, not `pages[i].tiles`.

### Plugin Deployment via API
`install_plugin_from_archive()` / `update_from_zip()` return None (use async variants for futures). ZIP must have `plugin.json` at root. Plugin must NOT be in `plugins/dev/` when installing via API.

### Plugin Structure
`python-agent-tools/`, `webapps/`, `custom-recipes/`, `python-runnables/`, `python-connectors/`, `python-lib/`, `code-env/`. See `skills/dataiku/references/plugin-structure.md`.

### Admin Writes Require `--yes` + Lockout Acknowledgement
All `dku admin` mutations (`license upload`, `sso/ldap/azure-ad/settings set`, `users-sync resync-all`, `messaging create`, `infra push-base-images`, `infra apply-k8s-policies`) dry-run without `--yes`. IAM writes additionally require `--i-understand-lockout-risk` — a bad SAML/OIDC/LDAP payload locks every user out and recovery requires filesystem access to `$DATA_DIR/config/general.json`. `admin settings set` is a FULL replace, not a merge: the CLI refuses payloads missing keys present in the live config (fail-closed). Always GET → edit → SET. See `dataiku-devkit/skills/dku-cli/references/admin-safety.md` for the full destructive-verb matrix and recovery steps.

### Semantic Model Schema
`dataikuapi.dss.semantic_model` exposes `entities`, `relationships`, `goldenQueries`, `glossaryTerms`, `glossaryBindings` as **opaque dicts with no inner class definitions** — the schema is nowhere in the SDK or public docs. Relationship shape (verified DSS 14.4.3): `{"firstEntity","secondEntity","pseudoSQLExpression":"left.col = right.col"}` — three fields, no cardinality (inferred from `entity.primaryKey`). `set-version` is a **shallow merge** at the version top level — passing `{"relationships":[...]}` replaces the whole array. Always build one example in the UI → `get-version -o json` → templatize → `set-version @file`. Full schema in `dataiku-devkit/skills/dataiku/references/semantic-models.md`.

### Govern nodes + node-type guard
`dku auth login` persists `node_type` (DESIGN/AUTOMATION/GOVERN/DEPLOYER/API) into the profile TOML after probing `get_instance_info()`. `helpers.get_client_from_ctx(ctx)` defaults to rejecting GOVERN profiles with exit code **4** and a prescriptive error pointing at `dku govern …`. Cross-node commands (`user`, `group`, `admin`, `whoami`) opt into broader support via `get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)`. Govern-only commands use `get_govern_client_from_ctx(ctx)` which requires `node_type == "GOVERN"`. When adding a new command: project-scoped command → do nothing (default guard applies); cross-node command → pass `allowed_node_types=ALL_NODE_TYPES`; Govern-only → use `get_govern_client_from_ctx`. Legacy profiles without stored `node_type` show `[?]` in `dku auth list` and BYPASS the guard (backwards compatible) — `dku auth login --profile X` refreshes them.

### Govern API payload shapes
`dataikuapi.GovernClient` lives on its own host, API-key-only auth. List-item payloads nest: `list_blueprints()` items have `{"blueprint": {"id","name",…}}`; blueprint-version list-items have `{"blueprintVersion": {"id": {"blueprintId","versionId"}}, "blueprintVersionTrace": {"status","originVersionId"}}`; artifact search hits have `{"artifact": {"id","name","status","workflow"}, "blueprint": {…}, "blueprintVersion": {"id":{…}}}`. Signoff list items use `signoffId.{artifactId,stepId}` (NOT flat `id`), `approverResponse` (NOT `approval`), `feedbackResponses` (NOT `feedbacks`). Never `.get('id')` on a list-item raw — navigate the nested shape. All workflow/status enum values are UPPERCASE (`APPROVED`, `WAITING_FOR_FEEDBACK`, `MAJOR_ISSUE`, `ACTIVE`). Delegation requires `GovernUserUsersContainer(login).build()` — raw login string fails. `create_*()` on admin handlers takes `new_identifier` as a SEPARATE positional arg: `create_blueprint(new_identifier, payload_dict)`. `save(danger_zone_accepted=True)` on a blueprint-version definition is the schema-breaking escape hatch → maps to tier-3 CASCADE with `--confirm-name` when that CLI command lands.

### Global flag position
`--errors json`, `--profile`, `--dangerous`, `--url`, `--api-key` are root-app options. They must precede the subcommand: `dku --errors json user delete X` works; `dku user delete X --errors json` fails with "No such option". The AGENT INSTRUCTION block's `rerun_with_confirmation` preserves the correct position automatically — agents should copy it verbatim.
---

## dataikuapi Quirks

Quirks are annotated inline in each `commands/*.py` file. Key patterns:

- `list_*()` usually returns dicts, not objects — access via `.get()`
- `create_*()` returns objects with non-standard id fields (e.g. `.dashboard_id`, `.insight_id`)
- Async operations return `DSSFuture` — call `.wait_for_result()`
- `get_agent(id)` is lazy — call `get_settings()` to verify existence
- `create_managed_folder()` returns `DSSManagedFolder` with `.id` (8-char hash)
- `plugin.list_files()` returns nested dict tree — dev plugins only
- Plugin recipe types not registered until JVM restart after API install
- `get_semantic_model()` is lazy — must call `_get_definition()` to verify existence
- Agent Hub is a plugin webapp, not a first-class object — manage via `get_webapp()` + `get_backend_actions()`
- `DSSScenario.get_last_finished_run()` returns None when no runs exist (not an error)
- `folder.list_contents()` returns `{"items": [...]}`, not a flat list
- `DSSAgent.as_llm()` returns `DSSLLM` — the only way to call an agent programmatically (no `run_conversation()`)
- `DSSAgentSettings` exposes `get_version_ids()`, `active_version`, `get_version_settings(vid)` — but NO `new_version()` (unlike `DSSSemanticModel.new_version()`). Create a new agent version by appending to `raw['versions']` and calling `settings.save()`. To activate: `project.get_saved_model(agent_id).set_active_version(vid)` — setting `raw['activeVersion']` and saving does not persist.
- `project.create_evaluation_store(name, flavor)` — `flavor` must be `'LLM'` for LLM eval stores
- Prompt recipe creation requires output dataset in `creationSettings`, not `recipe_proto` (internal API, not exposed via `dataikuapi`)
- Valid scenario step types: `build_flowitem` (builds datasets/folders), `custom_python` (inline script), `exec_sql` (SQL). See `dataikuapi/dss/scenario.py` line 629.

---

## Pull Request Descriptions

Every PR description must answer: *does this make agents more successful?*

- **What changed** — CLI commands, flags, skill docs, error messages, tests (be specific)
- **Why** — benchmark feedback / discovered gotcha / PR review finding / skill gap
- **Agent impact** — what failure mode this prevents or what new capability it unlocks
- **Test plan** — `uv run pytest -v` + any manual `dku` commands to verify the behavior

---

## Commit Conventions

Uses [Conventional Commits](https://www.conventionalcommits.org/) — enforced by commitlint pre-commit hook on `commit-msg` stage:

```
feat: add new command group
fix: handle empty dataset schema
docs: update skill reference
test: add recipe creation tests
chore: bump dependency versions
```

Hook pipeline also runs: `ruff-check --fix`, `ruff-format`, `uv-lock` sync, trailing-whitespace, detect-private-key.

---

## Testing

```bash
uv run pytest -v                # All tests (must all pass)
uv run pytest tests/commands/   # Command tests only
uv run pytest -k "test_dataset" # Filter by name
```

CI matrix: Python 3.10, 3.11, 3.12, 3.13 — use 3.10 as minimum baseline.

- Unit tests mock `DSSClient` via `conftest.py` fixtures (`mock_client`, `patch_client`)
- `patch_client` patches `dku_cli.client.get_client` AND `dku_cli.helpers.get_client`
- Use `typer.testing.CliRunner` for CLI invocation tests
- Pass `--project PROJ1` in tests instead of patching `resolve_project`
- Test both table and JSON output modes
- **Test error messages too** — verify agents get prescriptive guidance on failure

---

## Distribution

**CLI (Python package) — NOT on PyPI. Install from GitHub source:**

| Channel | Command |
|---------|---------|
| **Direct** | `uv tool install git+https://github.com/dataiku/dataiku-cli.git` |
| **Local dev** | `uv tool install --from . dku-cli` |

**Dataiku DevKit (AI agent skills):**

| Channel | Command |
|---------|---------|
| **Claude Code Plugin** | `/plugin marketplace add dataiku/dataiku-cli` |
| **skills.sh (40+ agents)** | `npx skills add dataiku/dataiku-cli --all` |

---

## Docs Index

| Doc | Description |
|-----|-------------|
| `benchmark/README.md` | Benchmark framework architecture, test tiers, how to run |
| `dataiku-devkit/skills/dku-cli/references/commands.md` | Full CLI command reference with flags and examples |
| `dataiku-devkit/skills/dataiku/references/*.md` | Platform reference docs — see Quick Router in `dataiku/SKILL.md` |
