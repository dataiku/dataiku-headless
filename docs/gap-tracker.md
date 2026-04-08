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
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `project.list_sql_schemas(connection)`, `project.list_sql_tables(connection, schema)`, `project.list_iceberg_namespaces(connection)`, `project.list_iceberg_tables(connection, namespace)`, `project.list_hive_databases()`, `project.list_hive_tables(db)`, `project.list_elasticsearch_indices_or_aliases(connection)`
- **CLI today:** Zero. Agents must guess table names or ask users.
- **Why P0:** When agents need to import data from SQL/Iceberg connections, they have no way to discover what tables exist. This causes failed `dataset create` attempts with wrong table names.
- **Next step:** Add `dku connection schemas CONNECTION` and `dku connection tables CONNECTION --schema SCHEMA`. Keep it on `connection` group (it's about what's *in* a connection, not project-specific). Also consider `dku connection discover CONNECTION` as a one-shot "list schemas + sample tables" combo.

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
- **Status:** `backlog`
- **Type:** `both`
- **Effort:** `M`
- **dataikuapi:** `project.list_retrieval_augmented_llms()`, `project.create_retrieval_augmented_llm(name, kb_ref, llm_id)`, `project.get_retrieval_augmented_llm(id)`, `rag.get_settings()`, `rag.delete()`, `rag.as_llm()`
- **CLI today:** Can create knowledge banks and embed recipes, but can't create the RAG LLM that ties them together. The pipeline is incomplete.
- **Skill today:** No mention of RAG LLM as a concept. KB creation is documented but not the full RAG pipeline.
- **Next step:** Add `dku rag` command group (list, create, get, delete, set-definition). Update both skills with "Complete RAG pipeline" pattern: create KB → embed recipe → build → create RAG LLM → attach to agent.

### GAP-006: Plugin install from store/git
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.install_plugin_from_store(plugin_id)`, `client.install_plugin_from_git(repo_url, checkout, subpath)`, `plugin.update_from_store()`, `plugin.update_from_git(repo_url, checkout, subpath)`
- **CLI today:** `dku plugin push` handles zip install/update only. Agents can't install plugins from the Dataiku plugin store or from git repos.
- **Next step:** Add `dku plugin install-from-store PLUGIN_ID` and `dku plugin install-from-git REPO_URL [--checkout BRANCH]`. Also add `dku plugin update-from-store PLUGIN_ID` and `dku plugin update-from-git PLUGIN_ID REPO_URL`.

### GAP-007: API service typed endpoints
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `settings.add_prediction_endpoint(endpoint_id, saved_model_id)`, `add_clustering_endpoint()`, `add_forecasting_endpoint()`, `add_causal_prediction_endpoint()`, `delete_package()`, `download_package_stream()`, `publish_package()`
- **CLI today:** Can create services and packages, but can't add typed endpoints or publish packages to deployer.
- **Next step:** Add `dku api-service add-endpoint SERVICE --type prediction --model MODEL_ID -P PROJ` and `dku api-service publish-package SERVICE PACKAGE_ID -P PROJ`.

### GAP-008: Streaming endpoints
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `L`
- **dataikuapi:** Full CRUD on `DSSStreamingEndpoint`, Kafka/HTTP SSE creators, schema management, zone ops
- **CLI today:** Zero. No `dku streaming` group. Recipe type "streaming" is recognized but no endpoint management.
- **Next step:** Add `dku streaming` group: list, create, get, delete, schema, set-schema. Support `--type kafka --connection CONN --topic TOPIC` and `--type httpsse --url URL`.

### GAP-009: Model MLflow import & external models
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `saved_model.import_mlflow_version_from_path()`, `...from_managed_folder()`, `...from_databricks()`, `project.create_mlflow_pyfunc_model()`, `project.create_external_model()`, `saved_model.create_external_model_version()`
- **CLI today:** Can manage saved models but can't import MLflow versions or create external models.
- **Next step:** Add `dku model import-mlflow MODEL_ID --path /path --version-id v1 -P PROJ` and `dku model create-external NAME --prediction-type BINARY_CLASSIFICATION -P PROJ`.

### GAP-010: Recipe rename & status
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `recipe.rename(new_name)`, `recipe.get_status()` (engines, messages, severity)
- **CLI today:** Must delete and recreate to rename. Can't check which engine a recipe will use.
- **Next step:** Add `dku recipe rename OLD NEW -P PROJ` and `dku recipe status RECIPE -P PROJ`.

### GAP-011: Scenario run details
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `scenario.get_runs_by_date(from, to)`, `scenario.get_last_successful_run()`, `scenario.get_average_duration()`, `run.get_step_run_report(step_id)`, `run.get_log(step_id)`
- **CLI today:** Has `runs` and `last-run` but can't filter by date, get last *successful* run, check average duration, or drill into step-level logs.
- **Next step:** Add `--from`/`--to` date filters on `dku scenario runs`, add `--successful` flag on `dku scenario last-run`, add `dku scenario step-log SCENARIO --run RUN_ID --step STEP_ID -P PROJ`.

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
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `client.get_root_project_folder()`, `folder.list_child_folders()`, `folder.list_project_keys()`, `folder.create_sub_folder()`, `folder.move_to()`, `project.move_to_folder()`
- **CLI today:** Zero. Can't organize projects into folders.
- **Next step:** Add `dku project-folder` group or extend `dku project` with `move-to-folder`, `list-folders`.

### GAP-015: Model comparisons
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `project.list_model_comparisons()`, `project.create_model_comparison()`, `comparison.get_settings()`, `settings.add_compared_item()`, `settings.remove_compared_item()`
- **CLI today:** Zero.
- **Next step:** Add `dku model-comparison` group: list, create, get, add-model, remove-model, delete.

### GAP-016: Continuous activities
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `project.list_continuous_activities()`, `activity.start()`, `activity.stop()`, `activity.get_status()`
- **CLI today:** Zero. Can't manage continuous recipes.
- **Next step:** Add `dku continuous` group: list, start, stop, status.

### GAP-017: Plugin file ops & parameter sets
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** `plugin.rename_file()`, `plugin.move_file()`, `settings.list_parameter_sets()`, `param_set.list_presets()`, `param_set.create_preset()`, `param_set.delete_preset()`
- **CLI today:** Has get-file/put-file/list-files but no rename/move. No preset management.
- **Next step:** Add `dku plugin rename-file`, `dku plugin move-file`. Consider `dku plugin presets` subgroup.

### GAP-018: Dataset zone operations
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `dataset.get_zone()`, `dataset.move_to_zone()`, `dataset.share_to_zone()`, `dataset.unshare_from_zone()`. Same on recipes, saved models, streaming endpoints, managed folders.
- **CLI today:** `dku flow move` handles zone moves. But no per-object zone query, share, or unshare.
- **Next step:** Check if `dku flow move` covers the main use case. If so, this is lower priority. If not, add `--share`/`--unshare` flags.

### GAP-019: Project AI description & timeline
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `project.generate_ai_description()`, `project.get_timeline()`
- **CLI today:** `dku dataset ai-describe` exists but no equivalent for projects. No timeline access.
- **Next step:** Add `dku project ai-describe PROJ` and `dku project timeline PROJ`.

### GAP-020: Schema detection & autodetect
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `dataset.test_and_detect()`, `dataset.autodetect_settings()`
- **CLI today:** `dku dataset upload` auto-detects on upload. But no standalone `detect` for datasets created via other means.
- **Next step:** Add `dku dataset detect DS -P PROJ` that runs `test_and_detect()` and shows detected format/schema.

### GAP-021: Plugin download
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.download_plugin_to_file(plugin_id, path)`, `client.download_plugin_stream(plugin_id)`
- **CLI today:** Can push plugins but can't download them. Useful for backup or migration.
- **Next step:** Add `dku plugin download PLUGIN_ID --dest ./plugin.zip`.

### GAP-022: Workspaces & data collections
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `M`
- **dataikuapi:** Full CRUD on `DSSWorkspace` and `DSSDataCollection`
- **CLI today:** Zero.
- **Next step:** Low priority unless agents need to organize content. Consider `dku workspace` group.

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
- **Status:** `backlog`
- **Type:** `cli`
- **Effort:** `S`
- **dataikuapi:** `client.list_meanings()`, `client.get_meaning()`, `client.create_meaning()`, `meaning.set_definition()`
- **Next step:** Add `dku meaning` group: list, get, create, update.

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
- **Status:** `backlog`
- **Type:** `skill`
- **Effort:** `S`
- **Gap:** Skills document KB creation and embed recipes separately but don't show the complete pipeline: KB → embed recipe → build → RAG LLM → attach to agent → test. The RAG LLM step is missing because GAP-005 blocks it.
- **Next step:** Blocked by GAP-005. Once RAG LLM CLI exists, add "Complete RAG Pipeline" pattern to both skills.

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
| 2026-04-08 | GAP-004 | Added `dku dataset usages` and `dku dataset lineage` — flow investigation commands, 10 tests |
| 2026-04-08 | GAP-003 | Added `dku dataset exists DS -P PROJ` — exit code 0/1, JSON support, 5 tests |
| 2026-04-08 | — | Initial audit: 37 CLI gaps + 3 skill gaps identified against dataikuapi |
