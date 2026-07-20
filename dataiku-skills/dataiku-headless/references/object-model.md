# Object model

The single home for what each DSS object type *is*, which read tool inspects it,
and whether Cobuild builds it. Open this when you don't know which tool to reach for
or whether a change is a delegation or a bootstrap write. Parameters for each tool
live in its schema (rule 7).

**Route column:** *Cobuild* = all creation/changes go through a Cobuild
conversation (rule 2). *Bootstrap* = the one direct-write exception, then Cobuild
downstream. *Read-only* = instance/catalog infra you inspect but don't build here.
*Direct-exec* = existing asset you may execute with a direct tool.

**The read surface is deliberately shallow, but never Cobuild-only.** The MCP
surface gives you `list_*` discovery plus deep reads. The objects a supervisor
inspects most (projects, datasets, recipes, flow, jobs, scenarios, connections,
folders, DQ) each have a purpose-built deep read. Every *other* buildable object
type — agents, dashboards, wikis, semantic models, insights, WebApps, knowledge
banks, RAG LLMs, agent tools, agent reviews, ML analyses, saved-model versions,
evaluation stores — is read through the single generic
[`get_object_settings`](tool-index.md) `(project_key, object_type, object_id)`
tool, which returns that object's type-specific deep-read payload (secrets
redacted, final payload byte-bounded). Usually that payload is the raw settings
dict, but a few types return a purpose-shaped payload: `saved_model` returns a
version snippet, `wiki_article` a name+body, and `ml_analysis` / an agent
`version_id` read / `evaluation_store` a small composed envelope (the last folds
in the evaluation summary — ids, labels, metrics). The versioned types (`agent`,
`saved_model`, `semantic_model`) take an optional `version_id`: given it returns
that version's detail; omitted it returns a version-discovery payload (metadata +
available version ids + active flags) so you can find the id without a separate
list tool. This exists precisely so verification never depends on Cobuild
grading its own homework: Cobuild's report is testimony, and `get_object_settings`
is the independent read that turns it into evidence (rule: *verify with your own
reads*). Raw settings are static config, though — for **runtime state** they don't
capture (a WebApp's live backend, an agent review's run outcomes, a job's
progress) fall back to a **read-only Cobuild turn** (`send_cobuild_message` with
`allow_edit_project=false`) or the flow artifacts an object produces (metrics,
evaluation stores, scored outputs). Rows below name the deep read to reach for.

| Object | What it is | Inspect with | Route |
|---|---|---|---|
| Project | The boundary for all assets, Flow, variables, metadata. Key is the stable id; display name is human-facing | `get_project_overview`, `get_project_metadata`, `get_project_variables` | Bootstrap (`create_project`), then Cobuild |
| Dataset (managed / external) | Tabular data; type + connection decide where data lives and who owns its lifecycle | `get_dataset_info`, `get_dataset_sample`, `get_dataset_profile`, `get_dataset_metrics` | Cobuild |
| Dataset (Uploaded Files) | User-supplied files/rows entering the project | same as above | Bootstrap (`create_upload_dataset` / `create_upload_dataset_from_rows`), then Cobuild |
| Recipe | A Flow transformation consuming objects and producing outputs | `list_recipes`, `get_recipe_settings` | Cobuild (execute existing → Direct-exec) |
| Flow zone | Visual grouping of related Flow items; no effect on technical dependencies | `list_flow_zones`, `get_flow_graph` | Cobuild |
| Job | Execution record for a build/run/train/deploy; the unit of supervision | `list_jobs`, `get_job_status`, `get_job_log`, `wait_for_job`, `get_future_status` | Read-only (produced by execution) |
| Scenario | Automation: ordered steps + triggers + reporters. `active` gates triggers, doesn't delete it | `list_scenarios`, `get_scenario_settings`, `get_scenario_run_history` | Cobuild (run existing → Direct-exec) |
| Connection | Shared config for storage/DB/LLM/service access; available ≠ usable in a given project | `list_connections`, `get_connection_info`, `test_connection` | Read-only (see connections-and-storage.md) |
| Managed folder | Connection-backed store for arbitrary/binary files, exports, artifacts | `list_managed_folders`, `get_managed_folder_info`, `get_managed_folder_contents` | Cobuild (file placement → Bootstrap `upload_file_to_managed_folder`) |
| Project library | Per-project source tree (Python/R/SQL/fixtures); may include git-imported external libs | `list_project_library`, `read_project_library_file` | Cobuild (single file write → Bootstrap `write_project_library_file`) |
| Code environment | Language runtime + dependency set for code work | `list_code_envs` | Read-only (select; changes via Cobuild) |
| ML analysis | Training/experimentation config: task, features, algorithms, validation | `list_ml_analyses` (discovery); `get_object_settings(object_type="ml_analysis")` for raw task settings | Cobuild |
| Trained model | A candidate result inside an analysis | no direct read — inspect via a read-only Cobuild turn, or read its evaluation artifacts in the flow | Cobuild |
| Saved model | Deployed, versioned model artifact | `list_saved_models` (discovery); `get_object_settings(object_type="saved_model")` lists versions, add `version_id=…` for a version's detail | Cobuild |
| LLM | A configured model with specific purposes (completion, embedding, rerank, image) | `list_llms` (discovery); no per-object settings — inspect via a read-only Cobuild turn | Read-only (referenced in prompts) |
| Knowledge Bank | Indexed content for retrieval; config sets embedding + vector-store behavior | `get_object_settings(object_type="knowledge_bank")` | Cobuild |
| Retrieval-Augmented LLM | LLM + Knowledge Bank + retrieval settings | `get_object_settings(object_type="retrieval_augmented_llm")` | Cobuild |
| Agent | LLM-driven agent; `agent_type` is `TOOLS_USING_AGENT` / `STRUCTURED_AGENT` / `PYTHON_AGENT` | `list_agents` (discovery); `get_object_settings(object_type="agent")` for settings/versions (optional `version_id`) | Cobuild |
| Agent tool | Project-level tool an agent calls, referenced by stable id | `get_object_settings(object_type="agent_tool")` | Cobuild |
| Agent review | Evaluates one agent vs test queries and named traits, over runs | `get_object_settings(object_type="agent_review")` for its config/traits; run *outcomes* are runtime — read via a read-only Cobuild turn | Cobuild |
| Semantic model | Business meaning over data for NL→query; container of versions, one active | `get_object_settings(object_type="semantic_model")` lists versions, add `version_id=…` for a version's settings | Cobuild |
| Data quality rule | Dataset-level check; outcomes OK/WARNING/ERROR/EMPTY | `list_data_quality_rules`, `get_data_quality_status` | Cobuild |
| Wiki article | Markdown doc in a parent/child tree; one home article | `get_object_settings(object_type="wiki_article")` (returns name + markdown body) | Cobuild |
| Dashboard | Owns pages, layout, page filters, tiles; not the underlying insight content | `get_object_settings(object_type="dashboard")` | Cobuild |
| Insight | Reusable view bound to a source object (by `insightId`), a dashboard building block | `get_object_settings(object_type="insight")` | Cobuild |
| WebApp | Interactive app (STANDARD/DASH/BOKEH/SHINY/STREAMLIT); settings ≠ backend state | `get_object_settings(object_type="webapp")` for settings; backend *state* is runtime — read via a read-only Cobuild turn | Cobuild |
| Data collection | Curated cross-project catalog of datasets; membership ≠ access | `list_data_collections`, `list_data_collection_objects` | Read-only (catalog) |
| Shared object | Outbound cross-project exposure: source owns, target uses read-only | `list_shared_objects` | Cobuild (sharing changes) |

## Concept gotchas (non-obvious, easy to get wrong)

- **Uploaded Files is the only dataset you create directly.** Managed and external
  datasets, and every later schema/metadata change, route through Cobuild. Upload
  autodetects columns as STRING (numeric, date, boolean, categorical) — inspect the
  profile and delegate any retype; don't infer a type from a column name.
- **Absent is not passing.** A configured DQ rule with no result (not yet computed
  for the partition) is not an OK. An ERROR rule can fail builds when it runs
  automatically after a build.
- **A saved model is deployed; a trained model is a candidate.** Scoring and
  retraining are Flow concerns (recipes + Cobuild), not model-object edits.
- **Semantic models version deliberately.** Prefer creating a non-active version for
  review over editing the active one that consumers depend on.
- **Data collection membership grants nothing.** To use a cataloged dataset from
  another project, the source project must share it (cross-project sharing is
  outbound and needs Read/Write-project-conf on the source).
- **A dashboard doesn't own its insights.** An insight tile references an existing
  insight by `insightId` — the insight must exist first. A page filter applies to the
  page; a filter dataset that mismatches a tile's insight silently empties the tile.
- **A WebApp's backend state is separate from its settings.**
  `get_object_settings(object_type="webapp")` reads the static config; the live
  backend (running or not) is runtime state it does not carry — diagnose
  availability via a read-only Cobuild turn, and don't infer framework or backend
  needs from the name.
- **Wiki references are typed:** `[[Article Name]]` links an article; an object
  reference is a markdown link whose target has the form `object_type:id` — types
  `dataset:`, `recipe:`, `saved_model:`, `analysis:`, `ai_agent:`, `agent_tool:`,
  `scenario:`, `dashboard:`. Discover each id via a `list_*` read or a read-only
  Cobuild turn; never invent one.
