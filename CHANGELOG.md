## Unreleased

Supervisor refactor: `dataiku-headless` is now the supervisor kit for external
coding agents — gather project context and verify with read tools, delegate
building to Cobuild, and use exactly three direct executions. One fixed tool
surface (53 non-cobuild + 5 cobuild tools), gated only by transport.

### BREAKING CHANGE

- **mcp**: remove the exposure modes — `DKU_MCP_COBUILD_MODE`, `DKU_MCP_TOOL_EXPOSURE`, and `DKU_MCP_SEARCH_*` are gone. The server exposes one curated supervisor surface (guarded by the allow-list test in `tests/test_smoke.py`), gated only by `DKU_MCP_TRANSPORT`
- **skills**: collapse the 23 per-object skills into a single `dataiku-headless` skill (router `SKILL.md` + `soul.md` + 5 playbooks + references), routed by frontmatter description
- **mcp**: remove the per-object deep-read modules (agent-reviews, webapps, wikis, insights, dashboards, semantic-models, evaluation-stores); the full-CRUD surfaces remain in the agent-dev-kit upstream
- **flow**: replace `get_flow_items_in_traversal_order` with `get_flow_graph` (nodes, edges, and an ASCII build tree in one call)
- **cobuild**: `allow_edit_project` now defaults to `false` — a build grant is opt-in per message

### Feat

- **cobuild**: durable conversation registry under `DKU_MCP_STATE_DIR` (default `~/.local/state/dataiku-headless`) — conversations and pending delete-confirmations survive server restarts; retained-turn timeouts with a `get_cobuild_turn_status` poll tool; restart-safe `list_cobuild_conversations`
- **execution**: three direct-execution tools restored from the dev kit — `build_datasets`, `run_recipe`, `run_scenario`
- **context**: composed grounding tools — `get_project_overview` (one call replaces the `list_*` fan-out) and `get_flow_graph`
- **audit**: `audit_project` — a read-only reviewability gate over structure, documentation, evidence, and maintainability, with an optional output contract; fixes are re-pointed at Cobuild delegations and named MCP tools
- **datasets**: expose the transport-appropriate uploaded-dataset tool — `create_upload_dataset` on `stdio`, `create_upload_dataset_from_rows` on `streamable-http`
- **skills**: single-skill layout with a generated tool-index and a skill link checker as the skills contract
- **ci**: continuous integration running the test suite and skill-integrity checks

### Review hardening

Adversarial re-review pass. The skills were rewritten against the *real* registered
tool surface and the behavior/vocabulary below was aligned across docs, skills, and
`.env.example`:

- **skills**: purge 37 references to tools that were pruned from the surface but still
  cited (`object-model.md` + playbooks). Where an object type has no deep-read tool,
  the docs now say so explicitly and route inspection through a read-only Cobuild turn.
- **guard**: new `scripts/check_skill_tool_names.py` validates every tool-shaped token
  in the skill markdown against the live registry (with an explicit non-tool
  allowlist), wired into the `pytest` gate — a reintroduced ghost tool now fails CI.
- **checker**: `check_skill_links.py` — basename fallback is restricted to *bare*
  references; path-qualified references must resolve exactly; duplicate basenames in
  the tree are an error rather than silently overwriting each other.
- **cobuild**: `answer_cobuild_confirmation` now **requires** `confirmation_id`
  (exact-match proof-of-inspection).
- **cobuild**: `streamable-http` no longer exposes `upload_file_to_managed_folder` /
  `write_project_library_file` (no server-filesystem access over a shared HTTP host).
- **cobuild**: restart semantics — conversations and observed confirmation ids survive
  a restart; a turn still *running* does not, and polling it reports `turn_lost`.
- **cobuild**: retained turns are capped by `DKU_MCP_MAX_COBUILD_TURNS` (default `8`).
- **config**: instance config resolves `$DKU_CONFIG_DIR/config.json` →
  `./.dataiku/config.json` → `~/.config/dataiku-headless/config.json`.
- **config**: `DKU_NO_CHECK_CERTIFICATE` uses a strict vocabulary — `true`/`1`/`yes`
  vs `false`/`0`/`no` (or empty); any other value is rejected.
- **config**: remove `DKU_DEFAULT_CONNECTION` / `DKU_DEFAULT_FOLDER_CONNECTION` /
  `DKU_DEFAULT_LLM` / `DKU_DEFAULT_EMBEDDING_LLM` (they were never applied).
- **projects**: `get_project_variables` redacts secret-like values and takes
  `include_local` (default `false`); `get_project_overview` redacts variables too.
- **folders**: `upload_file_to_managed_folder` enforces `overwrite=false` — no silent
  replacement of an existing file.
- **audit**: `audit_project` documented as a **flow-level** audit (datasets, recipes,
  zones, wiki); models, agents, and dashboards are verified separately.
- **libraries**: `list_project_library` / `read_project_library_file` are bounded
  (`max_items` / `depth` / `max_bytes`).
- **execution**: `build_datasets` runs one build job covering all requested outputs;
  scenario runs settle via `get_scenario_run_history`, not a DSSFuture path.
- **license**: align `SKILL.md` frontmatter and the Codex plugin manifest to
  `LicenseRef-Proprietary` (matching `LICENSE` and `pyproject.toml`).

## v0.2.0 (2026-06-09)

### Feat

- **packaging**: publish as dataiku-headless bundling server, skills, and docs
- **mcp**: reconcile compaction stack #161–#165 onto main (lossless tool-result trimming) (#169)
- **flow**: emit get_flow_items as [ref, type] pairs (lossless) (#160)
- **recipes**: omit engineParams from get_recipe_settings by default (#159)
- **datasets**: compact get_dataset_profile (top-N arrays + compact JSON) (#157)
- **datasets**: columnar get_dataset_sample + lower default n_rows (#156)
- **datasets**: add include_schema opt-out to create_upload_dataset
- **join,datasets**: H2 FULL OUTER trap + sticky-bigint inference
- **recipes/prepare**: add MultiColumnFold + removeFoldedColumns param
- **recipes/prepare**: add MultiColumnByPrefixFold processor reference
- **recipes,datasets**: gotchas surfaced by migration testing
- **data-collections**: list collections and their objects
- **cross-project-sharing**: surface required permissions on forbidden
- **cross-project-sharing**: expose_objects tools as a dedicated module
- **jobs**: surface recipe_name and outputs per job activity
- **kb**: add delete_knowledge_bank tool
- **webapps**: add delete_webapp MCP tool and update skill docs

### Fix

- **mcp**: remove conflict markers shipped to main in datasets.py (#168)
- **datasets**: require upload connection
- **datasets**: correct create_upload_dataset connection docs (required)
- **ml**: honor full_reguess when target/prediction_type unchanged
- enable create_recipe for NLP recipe types (summarization, classification)
- **agents**: enforce build-run-inspect loop for dependent recipes
- **prepare**: quote numval column in flag formula example
- **prepare**: always quote column names in val/strval/numval examples
- **recipes**: support sql_query recipe code read/write/create
- **ml**: skip mltask.guess() no-ops and respect mutual exclusivity

### Refactor

- **mcp**: compact JSON for all tool results (shared compact_json helper) (#158)
- **datasets**: drop sticky-bigint bullet (Excel-specific, not general)
- **recipes**: trim gotcha clauses to rule-only
- **recipes**: PR140 review feedback — relocate/tighten gotchas
- **recipes,datasets**: caveman style — drop autodiscoverable + prose
- **cross-project-sharing**: rename expose/unexpose to share/unshare
- **cross-project-sharing**: drop item validation, document constraint in skill
- **cross-project-sharing**: simplify expose/unexpose to single target_project
