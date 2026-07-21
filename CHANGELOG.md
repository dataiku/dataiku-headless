## Unreleased

Supervisor slice: read DSS state for grounding and proof, delegate project
asset design and mutation to Cobuild, and execute only existing assets
directly. One fixed stdio catalog of 58 registered tools (53 non-Cobuild
inspect/execute/bootstrap plus 5 Cobuild conversation tools) — no
tool-exposure or Cobuild mode, and no HTTP transport. The server is
single-process, single-credential, and local.

### Breaking change

- **surface**: delete both tool-exposure modes (BM25 search exposure and
  Cobuild-mode read suppression) and remove the streamable-HTTP transport
  entirely; the server always runs stdio and every registered tool is always
  present. `create_upload_dataset_from_rows` and the HTTP bearer-header auth
  path are gone
- **cobuild**: `allow_edit_project` defaults to false, so a message can create
  or edit project objects only when the caller opts in for that one message;
  `answer_cobuild_confirmation` requires the SDK `confirmation_id` and rejects a
  mismatched or already-consumed id before any SDK call
- **tools**: replace ~15 per-object settings/version readers with one
  `get_object_settings` (closed object-type enum, optional version discovery,
  field-name redaction); fold `get_dataset_column_descriptions` into
  `get_dataset_info`; delete `search_project_library` and
  `validate_project_library_file`
- **surface**: prune the remaining per-object discovery and runtime readers for
  dashboards, insights, WebApps (including live backend-state reads), evaluation
  stores, knowledge banks (including knowledge-bank search), retrieval-augmented
  LLMs, agent tools, agent reviews, and semantic models — landing on one fixed
  58-tool catalog (53 non-Cobuild + 5 Cobuild). Discover these families' ids from
  `get_project_overview`'s `object_inventory` section, then deep-read settings
  with `get_object_settings(object_type, object_id)`; runtime proof that saved
  settings cannot answer (a WebApp's running backend, an agent review's
  runs/results) comes from delegating a read-only Cobuild turn, not a dedicated
  tool
- **skills**: replace the 23 object skills with one `dataiku-headless` router
  skill — a SKILL.md, five objective playbooks, and an on-demand references tree
- **config**: drop the four dead `DKU_DEFAULT_*` fields (connection,
  folder_connection, llm, embedding_llm) with zero runtime consumers, and trim
  `get_current_instance` to the public name/url/description identity

### Feat

- **cobuild**: run each turn in a process-local retained daemon thread keyed by
  a `turn_id`; a client wait that expires returns `status=timeout` and the new
  `get_cobuild_turn_status` polls for the terminal outcome, so a timed-out
  mutation is polled, never resent. One in-flight turn per conversation and a
  global concurrency cap, both in-process; conversations and turns are
  process-local and a restart drops them (start a new one)
- **execution**: add `build_datasets`, `run_recipe`, and `run_scenario` — the
  three fixed deterministic executions of existing assets, with boundary
  validation and an optional bounded inline wait
- **context**: add `get_project_overview` and `get_flow_graph` — two dense
  one-call orientation tools with per-section failure isolation and node/edge
  ceilings — replacing the `list_*` fan-out and `get_flow_items_in_traversal_order`
- **audit**: add a read-only, fail-closed `audit_project` gate carrying only
  proof-bearing checks (flow consistency, caller output contract, structure and
  documentation presence); advisory naming heuristics are cut, while sampled-value
  column smells (e.g. all-null or constant terminal columns) remain as
  WARN-severity advisory findings that never block the gate
- **boundary**: `upload_file_to_managed_folder` gains `overwrite: bool = False`
  (membership check against the folder listing, root rejection, fail-closed on
  an unreadable listing); `list_data_collection_objects` gains bounded
  `max_items` with a 3-field identity projection and truncation metadata
- **contract**: generate `references/tool-index.md` from the live registry with
  a drift test, and enforce skill links and tool-shaped names under pytest
- **skills**: add an on-demand `soul.md` judgment layer, gated by the SKILL.md
  multi-stage clause so it stays out of the one-shot-read context budget

### Fix

- **runtime**: resolve config away from the installed source tree, parse
  `no_check_certificate` through a closed true/false vocabulary that raises on
  garbage instead of fail-open disabling TLS, guard the instance registry with a
  lock, and propagate request context into `run_blocking` worker threads so an
  in-flight `switch_instance` cannot retarget a running turn
- **secrets**: consolidate redaction to one field-name helper
  (`utils/redaction.py`) consumed by connections, project variables, and the
  generic `get_object_settings` read

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
