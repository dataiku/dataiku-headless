---
name: recipes
description: Create and update Dataiku recipes via MCP tools. Use when an agent must create recipes, inspect recipe settings, update code or visual payloads, execute recipe outputs, and verify impact in the project flow.
---

# Recipes

Recipes transform datasets / folders / models into new flow objects. The available recipe family types are: Data prep (visual), ML (visual), GenAI (visual), and Code. Visual recipe types **must** be used unless the user specifically requests transformations be performed via "code".

## Workflow for Creating or Updating Recipes

1. **Orient:** For project-wide or ambiguous work, use `get_flow_items_in_traversal_order` (+ `list_recipes` / `list_datasets` as needed). If the user already named the relevant datasets or recipe path is otherwise clear, skip broad flow discovery and go straight to `get_dataset_info` for schema and storage details, `get_dataset_profile` to explore content, and `get_dataset_sample` only when you additionally need raw value formats (date patterns, text structure, delimiters) that the profile doesn't capture. To inspect other target object types, use the appropriate skill.
   - **UploadedFiles inputs:** If any input dataset is an UploadedFiles type, call `get_dataset_profile` on it and use `set_dataset_column_storage_types` (e.g. `{"amount": "double", "date": "dateonly"}`) to correct any numeric or date columns stored as strings before building the recipe.
2. **For updates:** inspect the existing recipe first and preserve its storage context unless told otherwise.
3. **For new recipes:**
   - If outputs don't exist yet, create them first with `create_managed_dataset` / `create_managed_folder`.
   - Connection choice: user-specified → surrounding flow context (inspect adjacent datasets/folders) → `DKU_DEFAULT_CONNECTION` / `..._FOLDER_CONNECTION`.
   - Choose the recipe family before creating anything: remember, visual recipe types **must** be used unless the user specifically requests transformations be performed via "code". 
   - Call `create_recipe` with `recipe_type` and inputs/outputs.
   - `create_recipe` returns the same shape as `get_recipe_settings` (type, inputs/outputs by role, params, payload, code) plus `recipe_name`. Edit straight from those fields — no `get_recipe_settings` first.
5. **Edit:** `set_recipe_settings(project_key, recipe_name, operations=[...])` — pass an `operations` array where each element keys its data by its own action name. For a **pre-existing** recipe whose settings you don't already hold, `get_recipe_settings` first to round-trip; for one you just created, edit from the returned fields. Each action reads back what DSS persisted (`set_payload` → resulting payload for touched keys, `set_params` → resulting params, `set_inputs`/`set_outputs` → after-state), so a validation `get_recipe_settings` is not needed.
   ```json
   {"action": "set_payload",  "payload":  {...}}
   {"action": "set_params",   "params":   {...}}
   {"action": "set_code",     "code":     "..."}
   {"action": "set_inputs",   "inputs":   [...]}
   {"action": "set_outputs",  "outputs":  [...]}
   {"action": "set_code_env", "env_mode": "EXPLICIT_ENV|INHERIT|USE_BUILTIN_MODE", "env_name": "..."}
   ```

6. **Execute:** `build_datasets` for dataset outputs; `run_recipe` when the output is a folder, ML model, or other non-dataset object. Prefer `wait_for_completion=true` for the normal case with a reasonable timeout.
   - If the call reaches a terminal state, continue normally.
   - If the call times out, is interrupted, or otherwise leaves execution state unclear, do not assume failure.
   - Treat the related job as potentially still running, preserve or recover the `job_id`, and switch to `../jobs/SKILL.md` for supervision.
   - While that job remains non-terminal, do not start another build/run touching the same recipe, output dataset, or linear downstream path.
   - For a multi-output dataset recipe, trigger the recipe only once. Use exactly one output dataset as the build target.

7. **Validate:** Call `get_dataset_sample` on each output dataset to confirm data landed correctly — non-empty, expected columns, no obvious errors. For non-dataset outputs use the appropriate tool (`get_managed_folder_contents`, `get_ml_model_details`, etc.). Do not advance to the next recipe until this check passes.

8. **Describe:** After creating any recipe or dataset, call `update_flow_item` to set a `short_description` on the recipe and on each of its output datasets. One concise sentence each.

## Action Semantics

| Action | Default | Notes |
| --- | --- | --- |
| `set_payload` | `merge=false` (full replace) | Visual recipes; preferred round-trip (`get` → edit → `set`). |
| `set_payload` + `merge=true` | Top-level shallow merge | Top-level only; include full nested objects you touch. |
| `set_payload` + `merge=true, deep_merge=true` | Recursive dict merge | Targeted nested patches when full replacement is unnecessary. |
| `set_params` | `merge=true` | Focused params updates. For complex params, send full params with `merge=false`. |
| `set_code` | Full replace | Code recipes only. |
| `set_inputs` / `set_outputs` | `mode="add"` | Use `mode="replace"` only when full replacement is intended. |
| `set_code_env` | — | Code recipes only (`python`, `r`, `pyspark`, `sparkr`). `env_mode`: `EXPLICIT_ENV` (requires `env_name`) \| `INHERIT` \| `USE_BUILTIN_MODE`. Use `list_code_envs` to discover available names. |

## Recipe Best Practices

- Prefer fewer recipes when the logic can be expressed clearly. Add intermediate datasets only when they are needed for validation, branching, reuse, or to make the flow meaningfully easier to understand.
- Do not chain two `prepare` recipes in a row when one `prepare` recipe can hold the same processors cleanly.
- Prefer one multi-input `join` for lookup enrichment when several independent lookup tables all join directly to the same base dataset and no intermediate joined table is needed.
- Prefer `topn` over a separate `sort` plus downstream `sampling` when the real intent is to keep the top and/or bottom N rows sorted by one or more columns.

## Parent-Child Split

- **This (parent) skill:** flow discovery, output creation, `create_recipe`, `set_recipe_settings` semantics, execution, baseline validation.
- **Child type skill** (`recipe-types/<folder>/SKILL.md`): payload/params model, type-specific guardrails, references to load.
- Child skills should not restate shared rules unless the type introduces a real exception.

## Recipe Type Catalog

### Data prep (visual)

| Type | Use when |
| --- | --- |
| [`shaker` (prepare)](recipe-types/prepare/SKILL.md) | Column-level cleansing/enrichment with visual processors |
| [`join`](recipe-types/join/SKILL.md) | Join datasets on keys, optional pre/post filters |
| [`fuzzyjoin`](recipe-types/fuzzyjoin/SKILL.md) | Join exactly two datasets using fuzzy distances, optional text normalization, and matching-detail output |
| [`geojoin`](recipe-types/geojoin/SKILL.md) | Join datasets on geospatial predicates such as distance, containment, and intersection |
| [`grouping`](recipe-types/grouping/SKILL.md) | Aggregate rows by group keys |
| [`window`](recipe-types/window/SKILL.md) | Window analytics (rank, running totals, partitioned calcs) |
| [`sampling`](recipe-types/sampling/SKILL.md) | Dual purpose of 1) sampling rows (randomly, first N, class rebalance, etc.) and/or filtering rows (based on rules, formula, etc.) |
| [`split`](recipe-types/split/SKILL.md) | Dispatch rows of one dataset into several other datasets, based on rules |
| [`sort`](recipe-types/sort/SKILL.md) | Order rows by one or more columns |
| [`distinct`](recipe-types/distinct/SKILL.md) | Deduplicate rows |
| [`topn`](recipe-types/topn/SKILL.md) | Keep top and/or bottom N rows sorted by one or more columns |
| [`vstack`](recipe-types/vstack/SKILL.md) | Union all/append rows from multiple datasets |
| [`sync`](recipe-types/sync/SKILL.md) | Copy between storage backends |
| [`pivot`](recipe-types/pivot/SKILL.md) | Long → wide reshape |
| [`download`](recipe-types/download/SKILL.md) | Files-based connection → managed folder |
| [`export`](recipe-types/export/SKILL.md) | Dataset → files in managed folder |
| [`upsert`](recipe-types/upsert/SKILL.md) | Merge/upsert rows into a target dataset |

### ML (visual)

| Type | Use when |
| --- | --- |
| [`generate_features`](recipe-types/generate_features/SKILL.md) | Auto-generate features via joins/transforms/aggregations |
| [`prediction_scoring`](recipe-types/prediction_scoring/SKILL.md) | Score records with a trained prediction model |
| [`clustering_scoring`](recipe-types/clustering_scoring/SKILL.md) | Label records with a trained clustering model |
| [`evaluation`](recipe-types/evaluation/SKILL.md) | Evaluate a model against reference data |
| [`standalone_evaluation`](recipe-types/standalone_evaluation/SKILL.md) | Evaluate the prediction outputs of external models (no model object in the Dataiku project) |

**ML training recipes** (`prediction_training`, `clustering_training`, `causal_prediction_training`, `timeseries_forecasting_training`) appear in the flow after deploying an ML analysis. **Do not edit via `get_recipe_settings` / `set_recipe_settings`.** Use `machine-learning/SKILL.md` + ML analysis tools (`get_ml_analysis_settings`, `update_prediction_analysis`, etc.) for configuration. To run a training recipe, use `run_recipe` or `build_datasets` on the saved model output.

### GenAI (visual)

| Type | Use when |
| --- | --- |
| [`prompt`](recipe-types/prompt/SKILL.md) | Run column values through an arbitrary LLM prompt |
| [`nlp_llm_model_provided_classification`](recipe-types/nlp_llm_model_provided_classification/SKILL.md) | LLM classify text into predefined categories |
| [`nlp_llm_user_provided_classification`](recipe-types/nlp_llm_user_provided_classification/SKILL.md) | LLM classify text into user-defined classes |
| [`nlp_llm_summarization`](recipe-types/nlp_llm_summarization/SKILL.md) | LLM summarize column text |
| [`nlp_llm_rag_embedding`](recipe-types/nlp_llm_rag_embedding/SKILL.md) | Embeddings from column text → Knowledge Bank |
| [`embed_documents`](recipe-types/embed_documents/SKILL.md) | Embeddings from docs in a managed folder → folder + optional Knowledge Bank |
| [`extract_content`](recipe-types/extract_content/SKILL.md) | Extract text/images from docs in a managed folder |
| [`nlp_llm_finetuning`](recipe-types/nlp_llm_finetuning/SKILL.md) | Fine-tune LLM from prompt/completion data |
| [`nlp_llm_evaluation`](recipe-types/nlp_llm_evaluation/SKILL.md) | Evaluate LLM outputs |
| [`nlp_agent_evaluation`](recipe-types/nlp_agent_evaluation/SKILL.md) | Evaluate agent outputs incl. tool use |

### Code (use only when unless the user specifically requests transformations be performed via "code")

| Type | Use when |
| --- | --- |
| [`python`](recipe-types/python/SKILL.md) | External library / stateful / custom ML training |
| [`r`](recipe-types/r/SKILL.md) | R required |
| [`sql_query`](recipe-types/sql_query/SKILL.md) | Single-statement SELECT, DSS-managed output plumbing |
| [`sql_script`](recipe-types/sql_script/SKILL.md) | Multi-statement SQL workflow |
| [`pyspark`](recipe-types/pyspark/SKILL.md) | Spark required |
| [`spark_scala`](recipe-types/spark_scala/SKILL.md) | Spark Scala required |
| [`spark_sql_query`](recipe-types/spark_sql_query/SKILL.md) | Spark SQL required |
| [`shell`](recipe-types/shell/SKILL.md) | Shell-based flow step |

## Safety Rules

- Do not pass code payloads to visual recipe setters or JSON payloads to code recipe setters.
- Change I/O only via `set_inputs` / `set_outputs`, never payload/params.
- Avoid `merge=true` without `deep_merge=true` for nested payload edits — shallow merge drops nested keys.
- Don't use `RECURSIVE_FORCED_BUILD` unless the user explicitly asks for a full rebuild.
- If schema update fails after payload edit, report and propose a fix — don't retry blindly.
- Never call `build_datasets` with multiple dataset names from the same linear downstream path; collapse to the furthest requested target first.
- For a multi-output dataset recipe, trigger the recipe once by targeting exactly one output dataset. Do not request sibling outputs together.
- If a DSS job is already running for the recipe or its outputs, do not start another one in parallel unless the user explicitly wants concurrent builds and the targets are disjoint.
- Unknown recipe type: tell the user it's undocumented; inspect an existing instance with `get_recipe_settings` before mutating.
- Timeout is not failure. A timed-out or interrupted wait means the job may still be queued or running.
- After any uncertain execution result, switch to job supervision before attempting retries or follow-up mutations.
- Do not start overlapping jobs on the same recipe, output dataset, saved model, or direct downstream path until the prior job is confirmed terminal.
- If a job may still be active, pause flow mutations and resolve job state first.
- **Multi-recipe flows:** for linearly dependent recipes, complete the full cycle — create, configure, run, inspect output — for each recipe before starting the next. Never batch-create multiple dependent recipes and run them all at once.
- Set `appendMode: true` only on **dataset** outputs — managed folders, knowledge banks, and evaluation stores reject it (DSS errors). Default to `appendMode: false`; set `true` only when the user explicitly requests accumulation.
