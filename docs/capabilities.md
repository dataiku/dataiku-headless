# Headless capability matrix

Quick reference for what Headless inspects, what Cobuild builds, and what can be
re-run. For the operating workflow, start with
[`skills/dataiku-headless/SKILL.md`](../skills/dataiku-headless/SKILL.md) and load
its object-specific references as directed.

## The rule

**Flow and analytic assets are always built by Cobuild.** Headless has no tool to create
or modify a recipe, ML analysis, dashboard, insight, agent, agent tool, scenario, webapp,
wiki article, data quality rule, knowledge bank, semantic model, or evaluation store.

Headless writes Dataiku objects directly in three cases: **bootstrap** (get a project
or local content onto the instance so Cobuild has something to work with),
**cross-project**, and **instance-level administration**. It also re-runs assets that
already exist. Some bootstrap writes do land inside a project — see the table below.
Local profile actions are listed separately because they only change which Dataiku
instance the local client targets.


## Surface

**124 tools** · 91 read · 20 direct Dataiku write · 6 Cobuild · 3 execute · 3 local
profile · 1 connection test

| Bucket | # | Scope |
|---|---|---|
| Read / inspect | 91 | Never mutates |
| Direct Dataiku write | 20 | Bootstrap, cross-project, admin only |
| Cobuild conversation | 6 | All flow and analytic building |
| Execute | 3 | `build_datasets`, `run_recipe`, `run_scenario` |
| Local profile action | 3 | `configure_instance`, `switch_instance`, `delete_instance` |
| Connection test | 1 | `test_connection` |

Buckets count each tool once by what it does. The tables below group by area instead, so a
tool can appear in the **Local instance targeting** section while counting in a different
bucket here.

## Built by Cobuild — Headless only inspects

Two partial exceptions: Headless can create a dataset from a local file and create an
empty managed folder (see *Handled directly by Headless*). It cannot build anything else here.

| Area | Inspect | Run |
|---|---|---|
| Datasets | `list_datasets`, `get_dataset_info`, `get_dataset_sample`, `get_dataset_profile`, `get_dataset_metrics`, `get_dataset_column_descriptions`, `export_dataset` | `build_datasets` |
| Recipes | `list_recipes`, `get_recipe_settings` | `run_recipe` |
| Flow & zones | `get_flow_graph`, `list_flow_zones`, `get_flow_object_metadata` | — |
| ML analyses | `list_ml_analyses`, `get_ml_analysis_summary`, `get_ml_analysis_settings`, `list_ml_analysis_models`, `get_ml_model_details` | — |
| Saved models | `list_saved_models`, `list_saved_model_versions`, `get_saved_model_version_details` | — |
| Agents | `list_agents`, `get_agent_settings`, `list_agent_versions`, `list_agent_tools`, `get_agent_tool_settings` | — |
| Agent reviews | `list_agent_reviews`, `get_agent_review`, `list_agent_review_tests`, `list_agent_review_runs`, `get_agent_review_run_results` | — |
| Scenarios | `list_scenarios`, `get_scenario_settings`, `get_scenario_run_history`, `list_messaging_channels` | `run_scenario` |
| Dashboards & insights | `list_dashboards`, `get_dashboard_settings`, `list_insights`, `get_insight_settings` | — |
| Webapps | `list_webapps`, `get_webapp_settings`, `get_webapp_state` | — |
| Wikis | `list_wiki_articles`, `get_wiki_article` | — |
| Data quality | `list_data_quality_rules`, `get_data_quality_status`, `get_data_quality_rule`, `get_data_quality_rule_results`, `get_data_quality_rule_history` | — |
| LLMs & knowledge banks | `list_llms`, `get_llm_info`, `list_knowledge_banks`, `get_knowledge_bank_settings`, `search_knowledge_bank`, `list_retrieval_augmented_llms`, `get_retrieval_augmented_llm_settings` | — |
| Semantic models | `list_semantic_models`, `get_semantic_model_version_settings` | — |
| Evaluation stores | `list_evaluation_stores`, `get_evaluation_store_details` | — |

## Driving Cobuild

| Tool | Use |
|---|---|
| `start_cobuild_conversation` | Open a retained conversation on a project |
| `send_cobuild_message` | Ask Cobuild to build or change something |
| `answer_cobuild_question` | Answer a question Cobuild asked |
| `answer_cobuild_confirmation` | Approve or reject a proposed action |
| `get_cobuild_turn_status` | Poll a turn; recovers after a timeout or cancellation |
| `list_cobuild_conversations` | Find existing conversations for this instance and project |

## Handled directly by Headless

No Cobuild involved. Scope says what kind of access, and where a write lands.

| Area | Inspect | Act | Scope |
|---|---|---|---|
| Projects | `count_projects`, `list_projects`, `get_project_metadata`, `get_project_variables` | `create_project`, `set_project_variables` | Bootstrap — `create_project` precedes the conversation, variables are **in-project** |
| Datasets from local files | — | `create_upload_dataset` | Bootstrap, **in-project** — needs your filesystem |
| Managed folders | `list_managed_folders`, `get_managed_folder_info`, `get_managed_folder_contents` | `create_managed_folder`, `upload_file_to_managed_folder` | Bootstrap, **in-project** — needs your filesystem |
| Project libraries | `list_project_library`, `read_project_library_file`, `search_project_library`, `validate_project_library_file` | `write_project_library_file` | Bootstrap, **in-project** — needs your filesystem |
| Project folders | `list_project_folders`, `get_project_folder` | `create_project_folder`, `move_project_to_folder`, `delete_project_folder` | Cross-project |
| Code environments | `list_code_envs` | `create_code_env`, `update_code_env`, `delete_code_env` | Instance-level |
| Plugins | `list_plugins` | `install_plugin_from_store`, `update_plugin_from_store` | Instance-level |
| Users | `list_users` | `create_user`, `update_user`, `delete_user` | Instance-level |
| Groups | `list_groups` | `create_group`, `update_group`, `delete_group` | Instance-level |
| Jobs | `list_jobs`, `get_job_status`, `get_job_log`, `get_future_status`, `wait_for_job` | `build_datasets`, `run_recipe`, `run_scenario` | Execution — re-runs assets that already exist |
| Connections | `list_connections`, `get_connection_info`, `test_connection` | — | Read-only |
| Instance settings | `list_container_exec_configs`, `list_spark_configs`, `get_licensing_status` | — | Read-only |
| Data collections & sharing | `list_data_collections`, `list_data_collection_objects`, `list_shared_objects` | — | Read-only |

The **in-project** writes above are containers and content, not built logic: an empty
folder, an uploaded file, a library file, a variable, a dataset pointing at a file you
supplied. None of them build a recipe, a model, or an agent.

## Local instance targeting

Local client configuration, not Dataiku objects.

| Tool | Effect |
|---|---|
| `configure_instance` | Connect an instance; opens a local page for URL + API key |
| `switch_instance` | Change which configured instance subsequent calls target |
| `list_instances`, `get_current_instance` | Show configured instances and the active one |
| `delete_instance` | Removes a **saved connection profile from the local config file**. Does not touch the Dataiku instance. |
