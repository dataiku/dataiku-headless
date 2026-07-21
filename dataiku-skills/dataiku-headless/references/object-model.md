# Object model and inspection routes

Use this reference to discover the right read tool and decide whether a requested
change routes through Cobuild, a bootstrap action, or direct execution. Exact
parameters live in the live tool schema.

## Route meanings

- **Cobuild** — project-asset creation, change, move, activation, or deletion.
- **Bootstrap** — a narrow direct action needed before Cobuild can continue or to
  transfer caller-owned data into DSS.
- **Direct execution** — run behavior that is already designed.
- **Read-only** — this server can inspect the object but does not change it.

## Settings and runtime evidence are different

`get_object_settings` consolidates equivalent settings reads for 13 object
types: `agent`, `agent_review`, `agent_tool`, `dashboard`,
`evaluation_store`, `insight`, `knowledge_bank`, `ml_analysis`,
`retrieval_augmented_llm`, `saved_model`, `semantic_model`, `webapp`,
and `wiki_article`. It redacts secret-shaped values and has a hard response
ceiling.

Use discovery calls to obtain ids before calling it. Use dedicated runtime,
search, result, and history tools when saved settings cannot answer the question.

| Object | Inspect or discover with | Change or execute route |
|---|---|---|
| Project | `list_projects`, `count_projects`, `get_project_overview`, `get_project_metadata`, `get_project_variables` | Create with `create_project`; later changes through Cobuild |
| Dataset | `list_datasets`, `get_dataset_info`, `get_dataset_sample`, `get_dataset_profile`, `get_dataset_metrics` | Cobuild |
| Uploaded Files dataset | Same dataset reads | Bootstrap with `create_upload_dataset`; later changes through Cobuild |
| Recipe | `list_recipes`, `get_recipe_settings` | Cobuild; execute existing behavior with `run_recipe` |
| Flow and zones | `get_flow_graph`, `list_flow_zones`, `get_flow_object_metadata` | Cobuild |
| Job or future | `list_jobs`, `get_job_status`, `get_job_log`, `wait_for_job`, `get_future_status` | Read-only record of execution |
| Scenario | `list_scenarios`, `get_scenario_settings`, `get_scenario_run_history`, `list_messaging_channels`; lifecycle facts in `objects/scenarios.md` | Cobuild; execute an existing scenario with `run_scenario` |
| Connection | `list_connections`, `get_connection_info`, `test_connection` | Read-only in this surface |
| Managed folder | `list_managed_folders`, `get_managed_folder_info`, `get_managed_folder_contents` | Cobuild; caller-owned file placement can use the bootstrap upload |
| Project library | `list_project_library`, `read_project_library_file` | Cobuild; caller-owned single-file placement can use the bootstrap write (`write_project_library_file`) |
| Code environment | `list_code_envs`; selection constraints in `objects/code-environments.md` | Read-only in this surface |
| Data Quality rule | `list_data_quality_rules`, `get_data_quality_rule`, `get_data_quality_rule_results`, `get_data_quality_rule_history`, `get_data_quality_status`; types in `objects/data-quality-rule-types.md` | Cobuild |
| ML analysis | `list_ml_analyses`, `get_ml_analysis_summary`, `get_object_settings(object_type="ml_analysis")` | Cobuild |
| Trained analysis model | `list_ml_analysis_models`, `get_ml_model_details` | Cobuild |
| Saved model | `list_saved_models`, `get_object_settings(object_type="saved_model")`; pass `version_id` for one version | Cobuild |
| Evaluation store | `list_evaluation_stores`, `get_object_settings(object_type="evaluation_store")` | Cobuild |
| LLM | `list_llms`, `get_llm_info` | Read-only reference in this surface |
| Knowledge Bank | `list_knowledge_banks`, `get_object_settings(object_type="knowledge_bank")`, `search_knowledge_bank` | Cobuild |
| Retrieval-Augmented LLM | `list_retrieval_augmented_llms`, `get_object_settings(object_type="retrieval_augmented_llm")` | Cobuild |
| Agent | `list_agents`, `get_object_settings(object_type="agent")`; pass `version_id` for one version | Cobuild |
| Agent tool | `list_agent_tools`, `get_object_settings(object_type="agent_tool")` | Cobuild |
| Agent Review | `list_agent_reviews`, `get_object_settings(object_type="agent_review")`, `list_agent_review_tests`, `list_agent_review_runs`, `get_agent_review_run_results` | Cobuild |
| Semantic model | `list_semantic_models`, `get_object_settings(object_type="semantic_model")`; pass `version_id` for one version; concepts in `objects/semantic-models.md` | Cobuild |
| Wiki article | `list_wiki_articles`, `get_object_settings(object_type="wiki_article")`; hierarchy and link syntax in `objects/wiki-content.md` | Cobuild |
| Dashboard | `list_dashboards`, `get_object_settings(object_type="dashboard")`; dashboard/insight relationship in `objects/dashboards-and-insights.md` | Cobuild |
| Insight | `list_insights`, `get_object_settings(object_type="insight")`; types in `objects/dashboards-and-insights.md` | Cobuild |
| WebApp | `list_webapps`, `get_object_settings(object_type="webapp")`, `get_webapp_state`; frameworks in `objects/webapps.md` | Cobuild |
| Data collection | `list_data_collections`, `list_data_collection_objects` | Read-only catalog |
| Shared object | `list_shared_objects`; ownership and permission facts in `objects/cross-project-sharing.md` | Sharing changes through Cobuild |

## Common distinctions

- Uploaded Files is the only dataset family with a direct creation path here.
  Inspect detected types and delegate later schema or metadata changes.
- A configured Data Quality rule with no computed result is not a passing rule.
- A trained model is a candidate inside an analysis; a saved model is a deployed,
  versioned artifact.
- A dashboard page contains tiles that reference insights. Dashboard settings do
  not replace insight discovery or settings.
- WebApp settings are static configuration. `get_webapp_state` is the separate
  runtime signal.
- Data collection membership does not grant project access. Cross-project sharing
  remains a separate relationship.
- Semantic models are versioned. Discover the active and available versions before
  requesting a change.
- Wiki object links use real object ids. Discover the id rather than deriving one
  from a display name.
