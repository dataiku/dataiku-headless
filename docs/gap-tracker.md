# CLI & Skill Gap Tracker

> Feature gaps between `dku` CLI / agent skills and `dataikuapi`. Each entry is an issue to explore.
> **Last audited:** 2026-04-08 against dataikuapi in `.venv/lib/python3.10/site-packages/dataikuapi/`
> **Methodology:** Every claim verified by reading actual source code — CLI commands via `@app.command` grep, dataikuapi via public method extraction.

## How to use this file

- **Status**: `backlog` | `exploring` | `building` | `done` | `wont-do`
- **Type**: `cli` (missing command) | `skill` (missing agent guidance) | `both`
- **Priority**: `P0` (agents hit this weekly) | `P1` (agents hit this monthly) | `P2` (nice-to-have) | `P3` (specialized/admin)
- **Effort**: `S` (< 1hr) | `M` (1-4hr) | `L` (4hr+)

When closing an issue, add a one-line resolution note and date.

## Implementation & Testing Requirements

Every gap implementation MUST follow this sequence:

1. **Read dataikuapi source** — `.venv/lib/python3.10/site-packages/dataikuapi/`. Never guess API field names.
2. **Write unit tests** with mocks matching REAL API response shapes (verified from source).
3. **Run `uv run pytest -v`** — all must pass.
4. **Test against live DSS (MANDATORY)** — Run every new command with `uv run dku ...` against **ADVISORGPT** or **AGENTTEST** projects. Verify:
   - Table output shows real data, not blanks (field name mismatches cause this)
   - JSON field names match what DSS actually returns
   - Empty results and wrong inputs produce prescriptive error messages
5. **Fix mismatches before committing** — if live testing reveals issues, fix and re-test.
6. **Update skills (progressive disclosure):**
   - `references/commands.md` — add new command syntax + notes (layer 3, full detail)
   - `SKILL.md` Command Groups table — add new verbs (layer 2, scannable)
   - `SKILL.md` patterns section — add chaining examples ONLY if new commands enable a new workflow. Don't add per-command notes to SKILL.md — that belongs in commands.md.
7. Document which live commands were run in the commit message.

---

## P0 — Agents Hit This Weekly

### GAP-001: Dataset metrics & checks
- **Status:** `done` (partial — `info` command shipped 2026-04-08)
- **Type:** `both`
- **Effort:** `M`
- **dataikuapi:** `compute_metrics()`, `get_last_metric_values()`, `get_metric_history()`, `run_checks()`
- **CLI today:** `dku dataset info` shows row count + size from cached metrics. No way to trigger `compute_metrics()` or `run_checks()`.
- **Skill today:** Cheat sheet rule 11 says "gauge before you grab" and references `info`.
- **Remaining gap:** CLI can't *trigger* metric computation or run data checks. Agent must rely on whatever DSS auto-computed. `get_metric_history()` (trend over time) also missing.
- **Next step:** Add `dku dataset compute-metrics DS -P PROJ` and `dku dataset check DS -P PROJ`. Consider `dku dataset metrics DS -P PROJ` to show all available metric values without the info wrapper.

### GAP-002: Table/schema discovery for imports
- **Status:** `done` (2026-04-08)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `project.list_sql_schemas(connection)`, `project.list_sql_tables(connection, schema)`, `project.list_iceberg_namespaces(connection)`, `project.list_iceberg_tables(connection, namespace)`, `project.list_hive_databases()`, `project.list_hive_tables(db)`, `project.list_elasticsearch_indices_or_aliases(connection)`
- **CLI today:** `dku connection schemas CONNECTION -P PROJ` lists schemas/namespaces. `dku connection tables CONNECTION -P PROJ [--schema SCHEMA]` lists importable tables. Both auto-detect SQL vs Iceberg connection type.
- **Resolution:** Added both commands on `connection` group (requires `--project` since these are project-level APIs). SQL schemas tried first, falls back to Iceberg namespaces. Same pattern for tables. Empty results show prescriptive hints. 12 tests cover SQL, Iceberg fallback, empty, JSON, schema filter, env project.

### GAP-003: Dataset existence check
- **Status:** `done` (2026-04-08)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `dataset.exists()` — returns boolean
- **CLI today:** `dku dataset exists DS -P PROJ` — exit code 0 if exists, 1 if not. JSON output: `{"exists": bool, "name": ..., "project": ...}`.
- **Resolution:** Added `dku dataset exists` command. Uses `dataikuapi`'s `dataset.exists()` (which calls `get_metadata()` internally). Supports table and JSON output. 5 tests cover true/false, JSON, and env-based project resolution.

### GAP-004: Dataset usages & column lineage
- **Status:** `done` (2026-04-08)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `dataset.get_usages()` (what recipes/models use this dataset), `dataset.get_column_lineage(column)` (trace a column's provenance)
- **CLI today:** `dku dataset usages DS -P PROJ` shows recipes/analyses referencing a dataset. `dku dataset lineage DS --column COL -P PROJ` traces column provenance across the flow graph.
- **Resolution:** Added both commands. `usages` renders type/id/project table or raw JSON. `lineage` renders source→target column relations with --max-datasets option. Both handle empty results with informational messages. 10 tests cover table/JSON, empty, env project, and edge cases.

---

## P1 — Agents Hit This Monthly

### GAP-005: RAG LLM (Retrieval Augmented LLM)
- **Status:** `done` (2026-04-09)
- **Type:** `both`
- **Effort:** `M`
- **dataikuapi:** `project.list_retrieval_augmented_llms()`, `project.create_retrieval_augmented_llm(name, kb_ref, llm_id)`, `project.get_retrieval_augmented_llm(id)`, `rag.get_settings()`, `rag.delete()`, `rag.as_llm()`
- **CLI today:** New `dku rag` command group: list, create, get, delete, get-definition, set-definition. Completes the RAG pipeline: KB → embed → build → RAG LLM → attach to agent.
- **Resolution:** Added full command group. Live testing on AGENTKBBUILT revealed: (1) `name` field missing from list API response — handled with graceful fallback; (2) `llmId` and `kbRef` nested under `versions[0].ragllmSettings`, not top-level — `get` extracts from correct location. 11 tests. Live-verified: list (4 RAGs on AGENTKBBUILT), get (shows LLM ID, KB Ref, active version), JSON output.

### GAP-006: Plugin install from store/git
- **Status:** `done` (2026-04-08)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.install_plugin_from_store(plugin_id)`, `client.install_plugin_from_git(repo_url, checkout, subpath)`, `plugin.update_from_store()`, `plugin.update_from_git(repo_url, checkout, subpath)`
- **CLI today:** Four new commands: `install-from-store`, `install-from-git`, `update-from-store`, `update-from-git`. All support `--wait/--no-wait`, git commands support `--checkout` and `--subpath`.
- **Resolution:** All four commands implemented with DSSFuture handling. `install-from-store` shows code-env creation hint after install. 9 tests cover all commands with wait/no-wait and parameter passing. Live-verified: `update-from-store geocoder --no-wait` on DSS 14.5.

### GAP-007: API service typed endpoints
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `settings.add_prediction_endpoint()`, `add_clustering_endpoint()`, `add_forecasting_endpoint()`, `add_causal_prediction_endpoint()`, `publish_package()`, `delete_package()`
- **CLI today:** Four new commands: `add-endpoint` (prediction/clustering/forecasting/causal), `list-endpoints`, `publish-package`, `delete-package`. Completes the deployment pipeline.
- **Resolution:** Added all four commands. `add-endpoint` validates type against supported set, calls the appropriate dataikuapi method, then saves. `list-endpoints` reads from settings. `publish-package` supports `--published-service` for custom deployer target. 9 tests. Live-verified: create service, list-endpoints (empty + prescriptive hint), JSON empty list, all help commands.

### GAP-008: Streaming endpoints
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L`
- **dataikuapi:** Full CRUD on `DSSStreamingEndpoint`, Kafka/HTTP SSE creators, schema management, zone ops
- **CLI today:** Zero. No `dku streaming` group. Recipe type "streaming" is recognized but no endpoint management.
- **Next step:** Add `dku streaming` group: list, create, get, delete, schema, set-schema. Support `--type kafka --connection CONN --topic TOPIC` and `--type httpsse --url URL`.

### GAP-009: Model MLflow import & external models
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `project.create_mlflow_pyfunc_model()`, `saved_model.import_mlflow_version_from_path()`, `project.create_external_model()`
- **CLI today:** Three new commands: `create-mlflow`, `import-mlflow`, `create-external`. Supports SageMaker, Databricks, Azure ML, Vertex AI protocols.
- **Resolution:** Added all three commands. `create-mlflow` creates the model container, `import-mlflow` imports a version from a local path with code-env and set-active options, `create-external` supports all 4 protocols with `--config` JSON override. 10 tests. Live-verified: create-mlflow on AGENTTEST (created + deleted), JSON output, invalid type error.

### GAP-010: Recipe rename & status
- **Status:** `done` (2026-04-08)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `recipe.rename(new_name)`, `recipe.get_status()` → `DSSRecipeStatus` (engines, messages, severity)
- **CLI today:** `dku recipe rename RECIPE --name NEW -P PROJ` renames a recipe. `dku recipe status RECIPE -P PROJ` shows engine, severity, and check messages.
- **Resolution:** Added both commands. `rename` catches same-name ValueError with prescriptive error. `status` extracts engine from `get_selected_engine_details()`, severity from `get_status_severity()`, messages from `get_status_messages()`. 8 tests. Live-verified: SQL engine on Prepare recipe, DSS engine on prompt recipe, rename round-trip on AGENTTEST.

### GAP-011: Scenario run details
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `scenario.get_runs_by_date(from, to)`, `scenario.get_last_successful_run()`, `scenario.get_average_duration()`, `run.get_log(step_id)`
- **CLI today:** `runs` now supports `--from`/`--to` date filters and shows duration. `last-run` supports `--successful`. New: `avg-duration` and `run-log` commands.
- **Resolution:** Enhanced `runs` (date filter + duration column), `last-run` (--successful flag), added `avg-duration` (with human-readable formatting), and `run-log` (full run or step-scoped). 11 tests. Live-verified: runs/avg-duration/last-run on ISCAGENT.WEEKLYRUN (no runs — empty/error cases), all help commands render correctly.

### GAP-012: LLM advanced features
- **Status:** `backlog`
- **Type:** `both`
- **Effort:** `L`
- **dataikuapi:** `completion.with_json_output(schema)`, `completion.with_structured_output(model_type)`, `completion.with_tool_calls()`, `completion.execute_streamed()`, `llm.new_images_generation()`, `llm.new_reranking()`
- **CLI today:** `dku llm completion` does basic text completion only. No structured output, tool calls, image generation, or reranking.
- **Skill today:** No guidance on structured output patterns or cost-optimal LLM usage in DSS.
- **Next step:** Add `--json-schema` flag to `dku llm completion`. Add `dku llm generate-image` and `dku llm rerank`. Update skill with structured output examples.

---

## P2 — Nice-to-Have

### GAP-013: Apps & Business Apps
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L`
- **dataikuapi:** `client.list_apps()`, `client.get_app()`, `app.create_instance()`, `app.list_instances()`, `app.get_manifest()`, `client.list_business_apps()`, `business_app.create_instance()`, `business_app.get_settings()`
- **CLI today:** Zero. No `dku app` group.
- **Next step:** Add `dku app` group: list, get, create-instance, list-instances, manifest.

### GAP-014: Project folder management
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `client.get_root_project_folder()`, `folder.list_child_folders()`, `folder.list_project_keys()`, `folder.create_sub_folder()`, `project.move_to_folder()`
- **CLI today:** New `dku project-folder` group: list, create, move-project.
- **Resolution:** Added command group with recursive tree listing (indented hierarchy), subfolder creation, and project relocation. 5 tests. Live-verified: list shows full folder tree with 6 folders and all projects, JSON output correct.

### GAP-015: Model comparisons
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `project.list_model_comparisons()`, `project.create_model_comparison()`, `comparison.get_settings()`, `settings.add_compared_item()`, `settings.remove_compared_item()`, `comparison.delete()`
- **CLI today:** New `dku model-comparison` group: list, create, get, add-model, remove-model, delete.
- **Resolution:** Added full command group. List fetches settings for each comparison to show name + type. Add/remove model auto-saves. 9 tests. Live-verified: list empty on ADVISORGPT/AGENTTEST, JSON empty list, create help renders correctly.

### GAP-016: Continuous activities
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `project.list_continuous_activities()`, `activity.start()`, `activity.stop()`, `activity.get_status()`
- **CLI today:** New `dku continuous` group: list, start, stop, status.
- **Resolution:** Added full command group. `list` uses `as_objects=False` for raw dict access. `status` shows desiredState and mainLoopState.state. 7 tests. Live-verified: list on ADVISORGPT/AGENTTEST (empty state), JSON empty list, help renders correctly.

### GAP-017: Plugin file ops & parameter sets
- **Status:** `done` (2026-04-09, partial — file ops only, presets deferred)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `plugin.rename_file()`, `plugin.move_file()` — file ops done. `settings.list_parameter_sets()`, `param_set.list_presets()`, `param_set.create_preset()`, `param_set.delete_preset()` — presets deferred (complex get→modify→save flow).
- **CLI today:** `dku plugin rename-file` and `dku plugin move-file` added. Dev plugins only.
- **Resolution:** Added rename-file and move-file commands. Preset management deferred — it requires DSSPluginSettings get→modify→save flow which is more complex. 2 tests. Live-verified: help renders, non-dev plugin gives clear error, dev plugin file listing works.

### GAP-018: Dataset zone operations
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `dataset.get_zone()`, `dataset.share_to_zone()`, `dataset.unshare_from_zone()`
- **CLI today:** `dku dataset zone DS -P PROJ` queries zone. `dku dataset share DS --zone ZONE -P PROJ` shares. `dku dataset unshare DS --zone ZONE -P PROJ` unshares. `dku flow move` still handles full relocations.
- **Resolution:** Added 3 commands to dataset group. `zone` returns zone name+ID. `share` uses `share_to_zone()`. `unshare` uses `unshare_from_zone()`. 4 tests. Live-verified: zone on ADVISORGPT datasets (Default zone, scoring zone), JSON output correct.

### GAP-019: Project AI description & timeline
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `project.generate_ai_description(language, purpose, length, save_description)`, `project.get_timeline(item_count)`
- **CLI today:** `dku project ai-describe` with --purpose, --length, --language, --save. `dku project timeline` with --limit.
- **Resolution:** Added both commands. `ai-describe` supports 4 purposes and 3 lengths. `timeline` formats timestamps from millis, shows contributors + modification history. Live testing revealed timeline items use `time/user/action/objectId` fields (not `when/who/what/on`). 7 tests. Live-verified: ai-describe on ADVISORGPT (detailed multi-zone description), timeline showing real modification history.

### GAP-020: Schema detection & autodetect
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `dataset.autodetect_settings(infer_storage_types)` → `DSSDatasetSettings`
- **CLI today:** `dku dataset detect DS -P PROJ [--save] [--infer-types]` — standalone format/schema detection.
- **Resolution:** Added `detect` command using `autodetect_settings()`. Shows format type + detected columns. `--save` persists, `--infer-types` infers numeric/date types. Catches empty dataset and managed SQL errors with prescriptive messages. 5 tests. Live-verified: empty filesystem dataset (prescriptive error), managed SQL (ClassCastException caught), help renders correctly.

### GAP-021: Plugin download
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.download_plugin_to_file(plugin_id, path)`
- **CLI today:** `dku plugin download PLUGIN_ID [--dest PATH]` — downloads dev plugin as ZIP. Default: `<plugin_id>.zip`.
- **Resolution:** Added `download` command using `download_plugin_to_file()`. Shows file size after download. Only works for dev plugins (store plugins throw "not a dev plugin" error). 2 tests. Live-verified: `download dq-centralise --dest /tmp/dq-centralise.zip` → 23.7 KB, `download geocoder` → prescriptive "not a dev plugin" error.

### GAP-022: Workspaces & data collections
- **Status:** `done` (2026-04-09, workspaces only — data collections deferred)
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `client.list_workspaces()`, `client.create_workspace()`, `client.get_workspace()`, `workspace.list_objects()`, `workspace.delete()`
- **CLI today:** New `dku workspace` group: list, create, get, list-objects, delete. Data collections deferred.
- **Resolution:** Added workspace command group. Instance-level (no project). `list-objects` shows datasets/dashboards/articles. 10 tests. Live-verified: list shows 3 workspaces with colors, list-objects shows datasets/dashboards/articles from multiple projects, get returns full settings with permissions, JSON correct.

### GAP-023: MLflow extension
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L`
- **dataikuapi:** `DSSMLflowExtension` — list experiments, list models, deploy run models, import analyses, experiment tracking datasets
- **CLI today:** Zero. Can't manage MLflow experiments from CLI.
- **Next step:** Add `dku mlflow` group if MLflow adoption is significant.

---

## P3 — Specialized / Admin

### GAP-024: Cluster management
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L`
- **dataikuapi:** `client.list_clusters()`, `cluster.start()`, `cluster.stop()`, `cluster.run_kubectl()`, `cluster.delete_finished_pods()`, `client.create_cluster()`
- **Next step:** Add `dku cluster` group if K8s management via CLI is needed.

### GAP-025: Global/Personal API keys
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** Full CRUD on global and personal API keys
- **Next step:** Add `dku api-key` group: list, create, delete, get.

### GAP-026: Meanings (data dictionary)
- **Status:** `done` (2026-04-09)
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.list_meanings()`, `client.get_meaning()`, `client.create_meaning()`, `meaning.set_definition()`
- **CLI today:** New `dku meaning` group: list, get, create, update.
- **Resolution:** Added full command group. Instance-level (no project context). 4 types supported. 7 tests. Live-verified: list shows 2 PATTERN meanings (SSN, US post code), get returns full definition with regex pattern, JSON output correct.

### GAP-027: Messaging channels
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** CRUD + `mail_channel.send()`, SMTP/mail creators
- **Next step:** Add `dku messaging` group if notification automation is needed.

### GAP-028: Instance logs & admin
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.list_logs()`, `client.get_log()`, `client.get_global_usage_summary()`, `client.get_general_settings()`, `client.get_instance_info()`, `client.perform_instance_sanity_check()`
- **Next step:** Add `dku admin` group: logs, usage, settings, sanity-check, instance-info.

### GAP-029: Unified monitoring
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `DSSUnifiedMonitoring` — monitored project deployments, API endpoints, activity metrics
- **Next step:** Add `dku monitoring` group if deployment monitoring via CLI is needed.

### GAP-030: Project standards
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `DSSProjectStandardsCheck`, `DSSProjectStandardsScope` — quality checks, scopes
- **Next step:** Add `dku standards` group if governance automation is needed.

### GAP-031: Document extractor
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L`
- **dataikuapi:** `DocumentExtractor` — VLM extract, structured extract, text extract, PDF conversion, screenshots
- **Next step:** Add `dku document` group if document processing pipelines need CLI automation.

### GAP-032: User advanced ops
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `user.get_activity()`, `user.get_client_as()` (impersonation), `user_settings.add_secret()`, batch `create_users()`/`edit_users()`, `client.get_authorization_matrix()`
- **Next step:** Extend `dku user` with `activity`, `impersonate`, `secrets`. Add batch ops if needed.

### GAP-033: Connection advanced ops
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `connection.get_location_info()`, `connection.sync_root_acls()`, `connection.sync_datasets_acls()`, `client.list_connections_names(type)`
- **Next step:** Add `--type` filter to `dku connection list`. Add `dku connection sync-acls CONN`.

### GAP-034: Feature store
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.get_feature_store()`, `feature_store.list_feature_groups()`
- **Next step:** Tiny API. Add `dku feature-store list` if feature store usage grows.

### GAP-035: Statistics worksheets
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `dataset.list_statistics_worksheets()`, `dataset.create_statistics_worksheet()`, `worksheet.run_worksheet()`, `worksheet.run_card()`
- **Next step:** Add `dku statistics` group if statistical analysis via CLI is needed.

### GAP-036: Enterprise asset library
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.get_enterprise_asset_library()`, `library.list_collections()`, `library.list_prompts()`
- **Next step:** Add `dku assets` group: list-collections, list-prompts.

### GAP-037: External clients (API Node, Fleet, Govern, Launchpad)
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L` (each)
- **dataikuapi:** `APINodeClient` (predict, lookup), `APINodeAdminClient` (service management), `FMClient` (cloud instances), `GovernClient` (governance), `LaunchpadClient` (invites)
- **These are separate clients connecting to separate services**, not the main DSS instance. They'd need their own auth flow.
- **Next step:** Only pursue if there's specific demand. API Node testing (`dku apinode predict`) could be valuable for deployment validation.

---

## Skill-Only Gaps (no CLI change needed)

### SKILL-001: Complete RAG pipeline documentation
- **Status:** `done` (2026-04-09)
- **Type:** `skill`
- **Effort:** `S`
- **Gap:** Skills documented KB creation and embed recipes separately but didn't show the complete pipeline.
- **Resolution:** Added "Complete RAG Pipeline (KB → Embed → RAG LLM → Agent)" pattern to dku-cli SKILL.md with full chaining example. Also added Model Deployment Pipeline, Flow Investigation Pattern, and Plugin Installation Pattern. Unblocked by GAP-005.

### SKILL-002: Structured output patterns for LLM completion
- **Status:** `backlog`
- **Type:** `skill`
- **Effort:** `S`
- **Gap:** `dku llm completion` exists but skills don't show JSON mode, multi-turn patterns, or when to use completion vs. prompt recipes.
- **Next step:** Add "LLM Completion Patterns" section to dku-cli SKILL.md. Blocked partially by GAP-012 for structured output.

### SKILL-003: Cost estimation reference
- **Status:** `done` (2026-04-08)
- **Type:** `skill`
- **Gap:** Added "Cost Consciousness" section to dataiku SKILL.md with compute cost table, LLM cost optimization rules, and escalation template.
- **Resolution:** Shipped in dataiku SKILL.md "Working with Existing Projects" section.

---

## Changelog

| Date | Issue | Action |
|------|-------|--------|
| 2026-04-08 | GAP-001 | Shipped `dku dataset info` (row count, size, type, connection, build status). Partial — `compute_metrics()` and `run_checks()` still missing. |
| 2026-04-08 | SKILL-003 | Added cost consciousness and exploration protocol to dataiku SKILL.md |
| 2026-04-09 | GAP-022 | Added `dku workspace` group (list, create, get, list-objects, delete) — 10 tests |
| 2026-04-09 | GAP-015 | Added `dku model-comparison` group (list, create, get, add/remove-model, delete) — 9 tests |
| 2026-04-09 | GAP-017 | Added `dku plugin rename-file` and `move-file` — 2 tests (presets deferred) |
| 2026-04-09 | GAP-014 | Added `dku project-folder` group (list, create, move-project) — 5 tests |
| 2026-04-09 | GAP-018 | Added `dku dataset zone`, `share`, `unshare` — 4 tests |
| 2026-04-09 | GAP-026 | Added `dku meaning` group (list, get, create, update) — 7 tests |
| 2026-04-09 | GAP-016 | Added `dku continuous` group (list, start, stop, status) — 7 tests |
| 2026-04-09 | GAP-019 | Added `dku project ai-describe` and `timeline` — 7 tests |
| 2026-04-09 | GAP-021 | Added `dku plugin download` — dev plugin ZIP export, 2 tests |
| 2026-04-09 | GAP-020 | Added `dku dataset detect` — format/schema auto-detection, 5 tests |
| 2026-04-09 | GAP-009 | Added `dku model create-mlflow`, `import-mlflow`, `create-external` — 10 tests |
| 2026-04-09 | SKILL-001 | Added Complete RAG Pipeline, Model Deployment, Flow Investigation, Plugin Install patterns to SKILL.md |
| 2026-04-09 | GAP-007 | Added API service `add-endpoint`, `list-endpoints`, `publish-package`, `delete-package` — 9 tests |
| 2026-04-09 | GAP-005 | Added `dku rag` command group (list, create, get, delete, get/set-definition) — 11 tests |
| 2026-04-09 | GAP-011 | Enhanced `runs` (date filter, duration), `last-run` (--successful), added `avg-duration` and `run-log` — 11 tests |
| 2026-04-08 | GAP-006 | Added plugin install/update from store and git — 4 commands, 9 tests |
| 2026-04-08 | GAP-010 | Added `dku recipe rename` and `dku recipe status` — engine/severity/messages, 8 tests |
| 2026-04-08 | GAP-002 | Added `dku connection schemas` and `dku connection tables` — SQL/Iceberg discovery, 12 tests |
| 2026-04-08 | GAP-004 | Added `dku dataset usages` and `dku dataset lineage` — flow investigation commands, 10 tests |
| 2026-04-08 | GAP-003 | Added `dku dataset exists DS -P PROJ` — exit code 0/1, JSON support, 5 tests |
| 2026-04-08 | — | Initial audit: 37 CLI gaps + 3 skill gaps identified against dataikuapi |
