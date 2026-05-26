# dku-cli AI, Apps, and Analytics Command Syntax

Exact command syntax for AI, ML, app, dashboard, and analysis surfaces. For platform design guidance read the `dataiku` references.

## model

```bash
dku model list [-P PROJECT] [-o FORMAT]
dku model get MODEL_ID [-P PROJECT] [-o FORMAT]
dku model versions MODEL_ID [-P PROJECT] [-o FORMAT]
dku model set-active-version MODEL_ID VERSION_ID [-P PROJECT]
dku model metrics MODEL_ID [--version VERSION_ID] [-P PROJECT] [-o FORMAT]
dku model delete-version MODEL_ID --version VERSION_ID [--version VERSION_ID2] [-P PROJECT]
dku model delete MODEL_ID [-P PROJECT]
dku model usages MODEL_ID [-P PROJECT] [-o json]
dku model set-metadata MODEL_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
dku model create-mlflow NAME [-t PREDICTION_TYPE] [-P PROJECT] [-o FORMAT]
dku model import-mlflow MODEL_ID -v VERSION_ID --path PATH [--code-env ENV] [--set-active/--no-set-active] [-P PROJECT]
dku model create-external NAME -t PREDICTION_TYPE --protocol PROTO [--connection CONN] [--region REGION] [--config JSON] [-P PROJECT] [-o FORMAT]
```

- `set-active-version` activates a version; downstream prediction recipes and API endpoints use it
- `metrics` shows performance metrics (AUC, accuracy, RMSE, etc.) for the active version by default. `--version` inspects a specific version
- `delete-version --version` is repeatable to delete multiple versions at once
- `delete` removes the entire saved model
- `usages` shows where the model is used (recipes, endpoints, etc.) as JSON
- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- `create-mlflow` creates a saved model for MLflow pyfunc models. Prediction type optional (BINARY_CLASSIFICATION, MULTICLASS, REGRESSION). Follow with `import-mlflow` to import a version
- `import-mlflow` imports a MLflow model version from a local path. Model must have been created with `create-mlflow`. `--code-env` defaults to active env; set `INHERIT` for project default
- `create-external` creates a saved model for remote endpoints (SageMaker, Databricks, Azure ML, Vertex AI). `--protocol` is required. Use `--config` for full JSON config override

## ml

Train visual-ML models (prediction, clustering, timeseries, causal). Prefer these over Python.

```bash
dku ml create-prediction --input DS --target COL [--name NAME] [-P PROJECT]
dku ml create-clustering --input DS [--name NAME] [-P PROJECT]
dku ml create-timeseries --input DS --target COL --time-col COL [-P PROJECT]
dku ml create-causal --input DS --treatment COL --outcome COL [-P PROJECT]
dku ml list [-P PROJECT] [-o FORMAT]
dku ml status ANALYSIS MLTASK [-P PROJECT]
dku ml settings ANALYSIS MLTASK [-P PROJECT] [-o FORMAT]
dku ml algorithms ANALYSIS MLTASK [-P PROJECT] [-o FORMAT]
dku ml set-algorithm ANALYSIS MLTASK [--enable ALG]... [--disable ALG]... [--disable-all] [-P PROJECT]
dku ml set-feature ANALYSIS MLTASK FEATURE --role INPUT|REJECT|TARGET|WEIGHT [-P PROJECT]
dku ml train ANALYSIS MLTASK [-P PROJECT] [--wait]
dku ml models ANALYSIS MLTASK [-P PROJECT] [-o FORMAT]
dku ml details MODEL_ID [-P PROJECT] [-o FORMAT]
dku ml deploy MODEL_ID --name NAME [-P PROJECT]
dku ml redeploy MODEL_ID --saved-model-id SM_ID [-P PROJECT]
dku ml delete ANALYSIS MLTASK [--yes|-y] [-P PROJECT]
```

- **After `create-prediction`, ALWAYS audit `dku ml settings`** for label-leaking columns. Auto-guess does not detect leakage. Reject leaky columns with `dku ml set-feature ANALYSIS MLTASK COL --role REJECT` before training
- `set-feature --role REJECT` disables a column as input without rebuilding the upstream dataset. Use for label leakage, post-event columns, high-cardinality IDs
- `delete` prompts for confirmation; use `--yes` / `-y` for non-interactive
- To apply a saved clustering/prediction model to a dataset, see `references/recipe-decision.md` → "Scoring a Saved Model"

## llm

```bash
dku llm list [-P PROJECT] [--purpose PURPOSE] [-o FORMAT]
dku llm completion LLM_ID MESSAGE [-P PROJECT] [--system MSG] [--json-output] [--json-schema JSON] [-o text|json]
dku llm embeddings LLM_ID --text TEXT [-P PROJECT]
dku llm generate-image LLM_ID --prompt TEXT [--negative-prompt TEXT] [--dest FILE] [-P PROJECT]
dku llm rerank LLM_ID --query TEXT --doc TEXT [--doc TEXT ...] [-P PROJECT] [-o FORMAT]
```

- LLM IDs follow `provider:connection:model` pattern (e.g., `openai:MyConnection:gpt-4o-mini`)
- `completion -o json` returns text + usage stats
- **Finding embedding models:** `dku llm list` defaults to `--purpose GENERIC_COMPLETION` which only shows chat/completion models. To find embedding models, you MUST use:
  ```bash
  dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJECT
  ```
  Valid `--purpose` values: `GENERIC_COMPLETION`, `TEXT_EMBEDDING_EXTRACTION`, `IMAGE_EMBEDDING_EXTRACTION`, `RERANKING`, `IMAGE_GENERATION`
- `completion --json-schema` uses `with_json_output(schema=...)` for structured output. The LLM must support JSON mode with schema
- `embeddings` rejects LLM IDs that are not available for `TEXT_EMBEDDING_EXTRACTION` in the target project
- `generate-image` requires an IMAGE_GENERATION LLM. `--dest` saves to file, otherwise prints base64 preview. Use `--negative-prompt` to exclude elements
- `rerank` requires a RERANKING LLM. Pass multiple `--doc` flags. Results sorted by relevance score descending

### LLM Completion Patterns

**When to use `dku llm completion` vs a Prompt recipe:**

| Use case | Use `dku llm completion` | Use Prompt recipe (DSS UI) |
|----------|-------------------------|---------------------------|
| One-off query during automation | Yes | No |
| Repeatable pipeline step | No | Yes — becomes a flow node |
| Needs dataset input/output | No | Yes |
| Quick test/validation | Yes | No |
| Prompt engineering iteration | No | Yes — has prompt studio |

**Freeform JSON output:**
```bash
# Ask the LLM to respond in JSON (adds prompt instruction)
dku llm completion LLM_ID "List 3 colors" --json-output -P PROJ -o json
```

**Structured output with schema enforcement:**
```bash
# Schema-enforced JSON — the LLM MUST conform to the schema
dku llm completion LLM_ID "Extract the person's name and age" \
  --json-schema '{"type":"object","properties":{"name":{"type":"string"},"age":{"type":"integer"}},"required":["name","age"]}' \
  -P PROJ -o json
```

**With system message for role/context:**
```bash
dku llm completion LLM_ID "Summarize this data" \
  --system "You are a data analyst. Be concise." \
  -P PROJ
```

**Cost-conscious pattern:** Use `-o json` to see token usage:
```bash
dku llm completion LLM_ID "test" -P PROJ -o json | jq '.total_usage'
```

## webapp

```bash
dku webapp list [-P PROJECT] [-o FORMAT]
dku webapp create NAME [-P PROJECT] [--type TYPE]
dku webapp start WEBAPP_ID [-P PROJECT]
dku webapp restart WEBAPP_ID [-P PROJECT]
dku webapp stop WEBAPP_ID [-P PROJECT]
dku webapp status WEBAPP_ID [-P PROJECT]
dku webapp get-definition WEBAPP_ID [-P PROJECT] [-o json]
dku webapp set-definition WEBAPP_ID --definition JSON [-P PROJECT]
```

- `create` supports types: STANDARD (default), BOKEH, DASH, STREAMLIT, SHINY. Case-insensitive.
- `get-definition` returns full webapp settings including source code in `params` (html, css, js, python)
- `set-definition` accepts JSON string, `@file.json`, or `-` for stdin
- To edit webapp code: `get-definition` → modify `params` → `set-definition`
- No `delete` via API yet (DSS 14.5 returns 405). Delete webapps in the DSS UI.

## dashboard

```bash
dku dashboard list [-P PROJECT] [-o FORMAT]
dku dashboard get DASHBOARD_ID [-P PROJECT] [-o FORMAT]
dku dashboard create NAME [-P PROJECT] [--definition JSON] [--if-not-exists]
dku dashboard delete DASHBOARD_ID [-P PROJECT]
dku dashboard get-definition DASHBOARD_ID [-P PROJECT] [-o json]
dku dashboard set-definition DASHBOARD_ID --definition JSON [-P PROJECT]
dku dashboard set-metadata DASHBOARD_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
```

- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- No create via API for individual tiles/charts — manage via the raw JSON definition
- `get-definition` returns full dashboard JSON including `pages` array with embedded tiles
- Tiles live at `pages[i].grid.tiles` (NOT `pages[i].tiles`). Uses 36-column grid: `box: {top, left, width, height}`
- **URL anatomy:** `/dashboards/<dashboardId>_<slug>/view/<pageId>` maps to `dashboard.id` and `pages[].id`. Paste the URL path to locate a specific page in `get-definition` output
- **Filter-page dataset binding** can live at `pages[i].filtersParams.datasetSmartName`, not only inside filter insight definitions. Check both paths when tracing which dataset a filter targets
- **Always verify after `set-definition`** — DSS normalizes the payload on save. `TEXT` tile `tileParams.htmlContent` can be silently dropped. Follow every `set-definition` with a `get-definition` re-read and `diff` to confirm what actually persisted
- `set-definition` accepts JSON string, `@file.json`, or `-` for stdin
- See `skills/dataiku/references/dashboard-charts.md` for full chart JSON anatomy

## evaluation-store

```bash
dku evaluation-store list [-P PROJECT] [-o FORMAT] [--flavor FLAVOR]
dku evaluation-store create NAME [-P PROJECT] [-o FORMAT] [--flavor FLAVOR] [--if-not-exists]
dku evaluation-store get STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store evaluations STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store latest STORE_ID [-P PROJECT]
dku evaluation-store build STORE_ID [-P PROJECT] [--wait/--no-wait]
dku evaluation-store delete STORE_ID [-P PROJECT]
```

- `--flavor` on `create` specifies the store type: `TABULAR` (default), `LLM`, or `AGENT`. LLM eval recipes need `--flavor LLM`, agent eval recipes need `--flavor AGENT`
- `--flavor` on `list` filters by store flavor; omit to list all flavors
- `list` shows id, name, and flavor columns
- `create --if-not-exists` skips creation if a store with the same name already exists
- `latest` returns the most recent evaluation in a store (exits with error if empty)
- `build` waits for completion by default; use `--no-wait` for async

**End-to-end LLM evaluation:**
```bash
dku evaluation-store create my_eval --flavor LLM -P PROJ && \
dku dataset create eval_scored --type Filesystem -c filesystem_managed -P PROJ && \
dku dataset create eval_metrics --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create-llm-eval rag_eval \
  --input qa_responses --eval-store my_eval \
  --output-ds eval_scored --output-metrics eval_metrics \
  --task-type QUESTION_ANSWERING \
  --metrics "answerRelevancy,faithfulness" \
  --completion-llm "openai:gpt-4o" -P PROJ && \
dku recipe run rag_eval -P PROJ --wait
```

## insight

```bash
dku insight list [-P PROJECT] [-o FORMAT]
dku insight get INSIGHT_ID [-P PROJECT] [-o FORMAT]
dku insight create NAME [--type TYPE] [--dataset DS] [-P PROJECT] [--definition JSON] [--if-not-exists]
dku insight delete INSIGHT_ID [-P PROJECT]
dku insight get-definition INSIGHT_ID [-P PROJECT] [-o json]
dku insight set-definition INSIGHT_ID --definition JSON [-P PROJECT]
dku insight validate INSIGHT_ID [-P PROJECT]
dku insight set-metadata INSIGHT_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
```

- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- `create` defaults to `--type dataset_table`. Common types: `chart`, `dataset_table`, `report`, `scenario_last_runs`, `metrics`, `eda`, `jupyter`
- `--dataset` / `--ds` binds the insight to a dataset (sets `params.datasetSmartName`). Required for chart/dataset_table types
- `--definition` overrides/extends creation info (merged with `--type` and name)
- `validate` checks chart column references against the dataset schema (client-side). Reports mismatches with fuzzy suggestions
- **Never hand-write a full `dataset_table` payload.** DSS's `shakerScript` schema has nested objects that vary across versions (e.g. `columnOrder` expects objects, not strings). Clone the live default first: `dku insight create NAME --type dataset_table --dataset DS -P PROJ && dku insight get-definition ID -P PROJ -o json > table.json`, then only edit `params.shakerScript.columnsSelection` / `sorting` / `previewMode` before `set-definition`. See `skills/dataiku/references/dashboard-charts.md` for the safe-to-edit field list

## macro

```bash
dku macro list [-P PROJECT] [-o FORMAT]
dku macro run MACRO_ID [-P PROJECT]
```

## agent

```bash
dku agent list [-P PROJECT] [-o FORMAT]
dku agent create NAME [--type TOOLS_USING_AGENT] [-P PROJECT]
dku agent get AGENT_ID [-P PROJECT] [-o FORMAT]
dku agent delete AGENT_ID [-P PROJECT]
dku agent wake-up AGENT_ID [-P PROJECT]
dku agent shutdown AGENT_ID [-P PROJECT]
dku agent status AGENT_ID [-P PROJECT] [-o FORMAT]
dku agent add-tool AGENT_ID --tool TOOL_ID [--new-version] [--activate] [-P PROJECT]
dku agent set-llm AGENT_ID --llm-id LLM_ID [--new-version] [--activate] [-P PROJECT]
dku agent set-prompt AGENT_ID --prompt PROMPT [--new-version] [--activate] [-P PROJECT]
dku agent test AGENT_ID QUERY [-P PROJECT] [-o text|json]
dku agent set-metadata AGENT_REF [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
dku agent list-versions AGENT_ID [-P PROJECT] [-o FORMAT]
dku agent create-version AGENT_ID [--from VERSION_ID] [--activate] [-P PROJECT]
dku agent set-active-version AGENT_ID VERSION_ID [-P PROJECT]
```

- `create --type` defaults to TOOLS_USING_AGENT. Options: TOOLS_USING_AGENT, PYTHON_AGENT, PLUGIN_AGENT, STRUCTURED_AGENT
- `set-llm`, `add-tool`, and `set-prompt` operate on the active version by default. Pass `--new-version` to publish the change as a fresh version (reversible, preserves history); add `--activate` to make the new version active immediately. Without these flags the active version is mutated in place — fine for trivial edits, but not for prompt iteration where you may want to roll back.
- `set-prompt --prompt` accepts literal string, `@file.txt`, or `-` for stdin. Auto-detects agent type: uses `systemPrompt` for simple agents, `systemPromptAppend` for structured agents
- `test` sends a query to the agent and displays the response. ALWAYS test agents after creation or modification. `-o json` returns agent_id, query, response, and success status
- `set-metadata` updates description, short description, and/or tags. Accepts agent ID or name. Provide at least one of `--description`, `--short-desc`, `--tags`. Metadata is agent-level (not per-version), so it has no `--new-version` flag
- `list-versions` shows all versions with the active one marked. Use before `set-active-version` to confirm the target version id exists
- `create-version` deep-copies the source version (active by default, or `--from VID`). The new id is `vN` where N is the next integer not in use. With `--activate`, flips active via the saved-model API
- `set-active-version` validates the version id exists, then uses `proj.get_saved_model(agent_id).set_active_version(vid)`. Setting `activeVersion` in raw settings does not persist on the server — this is the only working path

## agent-block

Manage visual agent block graphs (structured visual agents). Blocks live inside `STRUCTURED_AGENT` agents (DSS 14.5+). Do NOT use `TOOLS_USING_AGENT` for block graphs — blocks silently fail to persist.

```bash
dku agent-block list AGENT_ID [-P PROJECT] [--version VER] [-o FORMAT]
dku agent-block get AGENT_ID BLOCK_ID [-P PROJECT] [--version VER] [-o FORMAT]
dku agent-block add AGENT_ID --block/-b JSON [--set-start] [-P PROJECT] [--version VER]
dku agent-block remove AGENT_ID BLOCK_ID [-P PROJECT] [--version VER]
dku agent-block connect AGENT_ID --from BLOCK_A --to BLOCK_B [-P PROJECT] [--version VER]
dku agent-block disconnect AGENT_ID BLOCK_ID [-P PROJECT] [--version VER]
dku agent-block set-start AGENT_ID BLOCK_ID [-P PROJECT] [--version VER]
dku agent-block set-mode AGENT_ID SIMPLE|BLOCKS_GRAPH [-P PROJECT] [--version VER]
dku agent-block get-graph AGENT_ID [-P PROJECT] [--version VER] [-o json]
dku agent-block set-graph AGENT_ID --definition/-d JSON [-P PROJECT] [--version VER]
```

- `--block` and `--definition` accept inline JSON, `@file.json`, or `-` for stdin
- `add` auto-switches agent to `BLOCKS_GRAPH` mode if currently `SIMPLE`
- `add --set-start` sets the new block as starting block (auto-set for first block)
- `connect` sets `nextBlock` on the source block (for ROUTING clauses use `get-graph`/`set-graph`)
- `remove` warns about dangling references from other blocks
- `--version` defaults to active version
- 13 block types: SET_STATE_ENTRIES, LLM_REQUEST, ROUTING, EMIT_OUTPUT, STANDARD_REACT, MANUAL_TOOL_CALL, MANDATORY_TOOL_CALL, PARALLEL, FOR_EACH, PYTHON_CODE, REFLECTION, DELEGATE_TO_OTHER_AGENT, GENERATE_ARTIFACT
- See `docs/block-graph-api.md` for full schema of each block type

**Example: Build an SVA from scratch:**
```bash
dku agent create "My SVA" --type STRUCTURED_AGENT -P PROJ
dku agent-block add My_SVA --set-start -b '{"type":"SET_STATE_ENTRIES","id":"init","entriesToSet":[{"secret":false,"key":"status","value":"'\''ready'\''"}],"nextBlock":"classify"}' -P PROJ
dku agent-block add My_SVA -b '{"type":"LLM_REQUEST","id":"classify","llmId":"openai:conn:gpt-4.1-mini","passConversationHistory":true,"systemPromptAfterHistory":"Classify intent","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputKey":"intent","nextBlock":"respond"}' -P PROJ
dku agent-block add My_SVA -b '{"type":"EMIT_OUTPUT","id":"respond","templateType":"CEL_EXPANSION","template":"Intent: {{state.intent}}","addToMessages":true}' -P PROJ
dku agent-block list My_SVA -P PROJ
```

**Critical block requirements (DSS 14.5+):**
- Every CORE_LOOP / LLM_REQUEST / MANDATORY_TOOL_CALL block needs `"llmId"`
- Every block with `"outputMode": "SAVE_TO_STATE"` needs `"outputKey"` (or `"outputStateKey"`)
- SET_STATE_ENTRIES `"value"` fields are CEL — never use `""` (empty), use `"''"` instead

## agent-review

Manage agent reviews — evaluate agent quality with LLM-as-judge traits, test cases, and evaluation runs.

```bash
dku agent-review list [-P PROJECT] [-o FORMAT]
dku agent-review create NAME [-P PROJECT]
dku agent-review get REVIEW_ID [-P PROJECT] [-o FORMAT]
dku agent-review delete REVIEW_ID [-P PROJECT]
dku agent-review set-agent REVIEW_ID --agent AGENT_ID [-P PROJECT]
dku agent-review set-llm REVIEW_ID --llm LLM_ID [-P PROJECT]
dku agent-review add-trait REVIEW_ID --name NAME [--description DESC] [--criteria CRITERIA] [--llm LLM_ID] [-P PROJECT]
dku agent-review list-tests REVIEW_ID [-P PROJECT] [-o FORMAT]
dku agent-review create-test REVIEW_ID --query QUERY [--reference ANSWER] [--expectations EXPECT] [-P PROJECT]
dku agent-review import-tests REVIEW_ID --dataset DS --query-column COL [--reference-column COL] [--expectations-column COL] [--top-n N] [-P PROJECT]
dku agent-review export-tests REVIEW_ID --dataset DS [--create-new] [--connection CONN] [-P PROJECT]
dku agent-review run REVIEW_ID [--wait/--no-wait] [--name NAME] [-P PROJECT]
dku agent-review list-runs REVIEW_ID [-P PROJECT] [-o FORMAT]
dku agent-review results REVIEW_ID --run RUN_ID [-P PROJECT] [-o FORMAT]
```

- `REVIEW_ID` accepts review ID or name (resolved automatically)
- `add-trait`: `--criteria` is the evaluation prompt for the LLM judge (e.g. "Does the answer directly address the user's question?")
- `import-tests`: bulk-creates test cases from dataset rows; each row becomes one test
- `run`: executes all tests, sending each query to the agent and scoring responses against configured traits
- `results`: shows per-test evaluation results including trait pass/fail status

---

## agent-tool

Manage agent tools (create, configure, run, inspect).

```bash
dku agent-tool list [-P PROJECT] [-o FORMAT] [--own-only]   # Includes foreign/shared tools by default; PROJECT column shows source
dku agent-tool get TOOL_ID [-P PROJECT] [-o FORMAT]
dku agent-tool create NAME --type TYPE [--knowledge-bank KB_ID] [--dataset DS] [--llm LLM_ID] [-P PROJECT]
dku agent-tool set-definition TOOL_ID --definition JSON [-P PROJECT]
dku agent-tool run TOOL_ID [--input JSON] [-P PROJECT] [-o FORMAT]
dku agent-tool types [-o FORMAT]
dku agent-tool delete TOOL_ID [-P PROJECT]
```

- `create --type` accepts built-in types (`DatasetRowLookup`, `VectorStoreSearch`, `LLMMeshLLMQuery`) or plugin types (`Custom_agent_tool_<plugin>_<tool>`). Run `dku agent-tool types` to list built-in types.
- `create --knowledge-bank` / `--kb` required for `VectorStoreSearch`.
- `create --dataset` / `--ds` sets `datasetSmartName` for `DatasetRowLookup`.
- `create --llm` sets `llmId` for `LLMMeshLLMQuery`.
- `set-definition` accepts JSON as literal string, `@file.json`, or `-` for stdin. Merges into existing settings (shallow — replaces top-level keys).
- `types` does NOT accept `-P` (project-independent).
- For custom Python tools, build a plugin with `python-agent-tools/` and deploy via `dku plugin push`.

## knowledge

Knowledge banks.

```bash
dku knowledge list [-P PROJECT] [-o FORMAT]
dku knowledge create NAME --embedding-llm LLM_ID [--vector-store-type CHROMA|FAISS|PINECONE|...] [--if-not-exists] [-P PROJECT]
dku knowledge get KB_REF [-P PROJECT] [-o FORMAT]
dku knowledge set-definition KB_REF --definition JSON|@file.json|- [-P PROJECT]
dku knowledge build KB_REF [-P PROJECT] [--wait]
dku knowledge search KB_REF --query TEXT [--max N] [-P PROJECT] [-o FORMAT]
dku knowledge delete KB_REF [--yes|-y] [-P PROJECT]
```

- All commands (except `list`, `create`) accept knowledge bank ID **or name** — name is resolved via list fallback
- `create` requires `--embedding-llm` (use `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` to find one)
- `create --vector-store-type` defaults to CHROMA. Options: CHROMA, FAISS, PINECONE, ELASTICSEARCH, AZURE_AI_SEARCH, VERTEX_AI_GCS_BASED, QDRANT_LOCAL, MILVUS_LOCAL, MILVUS_REMOTE
- `set-definition` merges JSON into current settings (shallow merge). Get current: `dku knowledge get KB -o json`
- `get` expects JSON from DSS; on getitstarted instances the sleep/wake page can intercept the request and return HTML instead

## semantic-model

Semantic models map business context (entities, attributes, relationships) onto datasets, enabling text-to-SQL via the Semantic Model Query agent tool. DSS 14.4+.

```bash
dku semantic-model list [-P PROJECT] [-o FORMAT]
dku semantic-model create NAME [--if-not-exists] [-P PROJECT]
dku semantic-model get SM_REF [-P PROJECT] [-o FORMAT]
dku semantic-model delete SM_REF [-P PROJECT]
dku semantic-model versions SM_REF [-P PROJECT] [-o FORMAT]
dku semantic-model get-version SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
dku semantic-model create-version SM_REF VERSION_ID [--duplicate-of VID] [-P PROJECT]
dku semantic-model set-version SM_REF --definition JSON|@file.json|- [--version VID] [-P PROJECT]
dku semantic-model set-active-version SM_REF VERSION_ID [-P PROJECT]
dku semantic-model distinct-values SM_REF [--version VID] [--entity E --attribute A] [--max N] [-P PROJECT] [-o FORMAT]
dku semantic-model update-index SM_REF [--version VID] [--wait] [-P PROJECT]

# Splice-level mutation verbs (preferred over raw set-version)
dku semantic-model add-entity SM_REF --from-dataset DS [--name N] [--pk COL[,COL2]] \
  [--index-values COL1,COL2] [--resolve-values COL1,COL2] [--description D] [--tags t1,t2] \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-entity SM_REF ENTITY_NAME [--version VID] [-P PROJECT]

dku semantic-model add-relationship SM_REF --from A --to B (--on COL[,COL2] | --expression "left.x = right.x") \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-relationship SM_REF --from A --to B [--version VID] [-P PROJECT]

dku semantic-model add-glossary-term SM_REF --term T [--description D] [--synonyms s1,s2] \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-glossary-term SM_REF --term T [--version VID] [-P PROJECT]

dku semantic-model list-entities SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
dku semantic-model list-relationships SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
dku semantic-model list-glossary SM_REF [--version VID] [-P PROJECT] [-o FORMAT]

# Entity-scoped: metrics (aggregates) and filters (predicates)
dku semantic-model add-metric SM_REF --entity E --name N --expression "COUNT(*)" \
  [--description D] [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-metric SM_REF --entity E --name N [--version VID] [-P PROJECT]
dku semantic-model list-metrics SM_REF --entity E [--version VID] [-P PROJECT] [-o FORMAT]

dku semantic-model add-filter SM_REF --entity E --name N --expression "col = 'x'" \
  [--description D] [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-filter SM_REF --entity E --name N [--version VID] [-P PROJECT]
dku semantic-model list-filters SM_REF --entity E [--version VID] [-P PROJECT] [-o FORMAT]

# Attribute-scoped: curated enum values
dku semantic-model set-manual-values SM_REF --entity E --attribute A \
  (--values "a,b,c" | --clear) [--version VID] [-P PROJECT]

# Version-scoped: golden queries (NL→SQL few-shot examples)
dku semantic-model add-golden-query SM_REF --name N --question Q --sql SQL \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-golden-query SM_REF --name N [--version VID] [-P PROJECT]
dku semantic-model list-golden-queries SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
```

- All commands accept semantic model ID **or name** — name resolved via list fallback
- `create` returns auto-generated ID (not name) — capture it
- `--version` defaults to the active version when omitted
- `create-version` does NOT persist until the server is called — `new_version().save()` is handled internally
- `create-version --duplicate-of` clones an existing version's configuration
- `set-version` **shallow-merges** JSON into current version settings at the TOP level. This means passing `{"relationships":[{...}]}` **REPLACES the entire relationships array**, not appends. Always read current, modify, then save:
  ```bash
  dku semantic-model get-version SM -P PROJ -o json > sm.json
  jq '.relationships += [{"firstEntity":"A","secondEntity":"B","pseudoSQLExpression":"left.id = right.id"}]' sm.json > sm_new.json
  dku semantic-model set-version SM --definition @sm_new.json -P PROJ
  ```
- **Relationship JSON shape** (verified on DSS 14.4.3): `{"firstEntity":"name","secondEntity":"name","pseudoSQLExpression":"left.col = right.col"}`. Three fields. No cardinality. See `dataiku` skill's `references/semantic-models.md` for entity/glossary shapes.
- **Never guess inner JSON shapes.** `dataikuapi` treats entities/relationships/glossary as opaque dicts with no inner class definitions. Build one example in the DSS UI → export with `get-version -o json` → templatize.
- **Prefer splice verbs over `set-version` for mutations.** `add-entity`/`add-relationship`/`add-glossary-term` load the current version, splice the array, and save — no shallow-merge hazard. Use raw `set-version` only for bulk replace or top-level field changes (`description`, `indexingSettings`).
- **`add-entity --from-dataset DS`** auto-generates all attribute definitions from the dataset schema (column names, DSS types, descriptions). Pass `--index-values COL1,COL2` to enable distinct-value indexing + fuzzy resolution on specific columns. Default PK is the first dataset column — override with `--pk COL`.
- **`add-relationship --on COL`** builds `left.COL = right.COL`. Comma-separated for composite joins (`--on ACCOUNT_SK,MONTH` → `left.ACCOUNT_SK = right.ACCOUNT_SK AND left.MONTH = right.MONTH`). Use `--expression` for computed predicates (`LOWER(left.x) = LOWER(right.y)`).
- **Entity metrics/filters are pseudo-SQL.** Metrics are aggregates (`COUNT(*)`, `SUM(Amount)`, `COUNT(DISTINCT CustomerID)`). Filters are predicates (`Subscribed = 'true'`, `Date >= CURRENT_DATE - INTERVAL '30 days'`). These become the **approved** building blocks the text-to-SQL agent composes — without them the agent hand-rolls SQL from scratch, which is worse.
- **`set-manual-values` flips the attribute to curated-enum mode.** Automatically sets `distinctValuesHandlingMode=MANUAL`, `indexDistinctValues=true`, `resolveInUserRequests=true` so the agent resolves user strings ("high risk" → `RiskTolerance = 'High'`). Use `--clear` to revert to indexed scan (`mode=NONE`).
- **Golden queries drive quality more than any other single input.** Add real NL questions + the canonical SQL. The agent uses these as few-shot examples, learning join style + your column conventions.
- **From-scratch workflow, high-quality** (verified DSS 14.4.3):
  ```bash
  dku semantic-model create "My Model" -P PROJ
  dku semantic-model create-version $SM_ID v1 -P PROJ
  dku semantic-model set-active-version $SM_ID v1 -P PROJ

  # Entities (auto-generate attributes from datasets)
  dku semantic-model add-entity $SM_ID --from-dataset Customers --pk CustomerID --index-values Name,RiskTolerance -P PROJ
  dku semantic-model add-entity $SM_ID --from-dataset Orders --pk OrderID -P PROJ

  # Metrics & filters (agent's approved aggregates/predicates)
  dku semantic-model add-metric $SM_ID --entity customers --name "Total Customers" --expression "COUNT(CustomerID)" -P PROJ
  dku semantic-model add-metric $SM_ID --entity customers --name "Subscribed Customers" --expression "COUNT(CASE WHEN Subscribed='true' THEN CustomerID END)" -P PROJ
  dku semantic-model add-filter $SM_ID --entity customers --name "Subscribed" --expression "Subscribed = 'true'" -P PROJ

  # Curated enums on categorical attributes
  dku semantic-model set-manual-values $SM_ID --entity customers --attribute RiskTolerance --values "Low,Medium,High" -P PROJ

  # Joins
  dku semantic-model add-relationship $SM_ID --from customers --to orders --on CustomerID -P PROJ

  # Glossary & golden queries
  dku semantic-model add-glossary-term $SM_ID --term ARR --description "Annual Recurring Revenue" --synonyms "annual recurring revenue" -P PROJ
  dku semantic-model add-golden-query $SM_ID --name "count subscribers" --question "How many subscribed customers do we have?" --sql "SELECT COUNT(*) FROM Customers WHERE Subscribed='true'" -P PROJ

  dku semantic-model update-index $SM_ID --wait -P PROJ
  ```
- `distinct-values` requires `--entity` AND `--attribute` together, or neither (for all attributes)
- `update-index` triggers distinct values indexing (async). Use `--wait` to block until complete
- **Always `update-index --wait` after changing entities/attributes.** The text-to-SQL agent only sees indexed distinct values.
- **Limitation**: `get_semantic_model()` is lazy — the CLI calls `_get_definition()` internally to verify existence

## agent-hub

Manage Agent Hub plugin webapp instances (limited surface — see notes).

```bash
dku agent-hub list [-P PROJECT] [-o FORMAT]
dku agent-hub config [--hub HUB_ID] [-P PROJECT] [-o FORMAT]
dku agent-hub set-config --definition JSON|@file.json|- [--hub HUB_ID] [-P PROJECT]
dku agent-hub start [--hub HUB_ID] [-P PROJECT]
dku agent-hub stop [--hub HUB_ID] [-P PROJECT]
```

### What's possible from the CLI

- `list` — enumerate Agent Hub webapps in a project
- `config` — read the webapp's plugin-runtime config (typically just `{log_level, storage_type}`)
- `set-config` — shallow-merge `log_level` / `storage_type` updates
- `start` / `stop` — control the hub's Flask backend

### What is NOT possible from the CLI (UI-only today)

**Verified live on DSS 14.5.1 with agent-hub plugin v1.2.4 and v1.3.2.** None of the following can be configured via the CLI / public DSS SDK. Use the DSS UI:

- Creating a new Agent Hub instance (DSS server rejects plugin webapp types on the public `/webapps/` POST endpoint)
- Setting the orchestrating LLM
- Enrolling / removing / configuring enterprise agents
- Logos and RGB branding
- Quick Agents (My Agents)
- Tools attached to the hub
- Embedding LLM (for RAG)
- Augmented LLMs

**Why**: the agent-hub plugin stores its UI configuration in a private SQLite store accessed via the webapp's Flask backend at `/web-apps-backends/{proj}/{hub}/...`. That endpoint exists but requires session-cookie auth — not the API key the public DSS SDK uses. The webapp `config` field that the SDK CAN write to holds only plugin-runtime knobs (`log_level`, `storage_type`); writing other keys appears to succeed but the plugin never reads them.

Earlier `set-llm` / `add-agent` / `remove-agent` / `set-agent` / `list-agents` verbs were removed because they wrote phantom keys with no effect — that misled agents into believing they had configured the hub. Until the plugin exposes a public REST API, hub setup remains a DSS-UI task.

### Detail notes

- `--hub` auto-detects when exactly one Agent Hub exists in the project; required when multiple exist
- `list` filters webapps by any type containing `agent-hub` (covers both `webapp_agent-hub_agent-hub` and `webapp_agent-hub_agent-hub-light`)
- `start` / `stop` are convenience wrappers around `dku webapp start/stop`

## app-designer

```bash
# Enable/disable app homepage
dku app-designer enable [-P PROJECT] [--label LABEL] [--description DESC]
dku app-designer disable [-P PROJECT]

# Get/set full manifest
dku app-designer get [-P PROJECT] [-o json]
dku app-designer set-definition [-P PROJECT] -d JSON|@file.json|-

# Section titles and text
dku app-designer set-section [-P PROJECT] -s INDEX --title "Step 1) Upload" [--text "HTML description"]

# Tile management
dku app-designer list-tiles [-P PROJECT] [-o FORMAT]
dku app-designer add-tile [-P PROJECT] -s INDEX --type TYPE [--dataset DS] [--scenario ID] [--dashboard ID] [--folder ID] [--prompt LABEL] [--help-text TEXT] [--behavior BEH] [--button-text TEXT] [--params JSON] [--code CODE] [--definition JSON]
dku app-designer remove-tile [-P PROJECT] -s SECTION -i INDEX
```

**Notes:**
- `enable` must be called before other commands on a non-app project
- `add-tile --type` supports: `SCENARIO_RUN`, `INLINE_DATASET_EDIT`, `UPLOAD_DATASET_SET_FILE`, `DOWNLOAD_DATASET`, `DASHBOARD_LINK`, `MANAGED_FOLDER_BROWSE`, `MANAGED_FOLDER_ADD_FILE`, `DOWNLOAD_MANAGED_FOLDER_FILE`, `PROJECT_VARIABLES_EDIT`, `INLINE_PYTHON_RUN`, `PERFORM_SCHEMA_PROPAGATION`, `DATASET_EDIT_SETTINGS`, `FILES_BASED_DATASET_BROWSE_AND_PREVIEW`, `DOWNLOAD_DASHBOARD_EXPORT`, `DOWNLOAD_RMARKDOWN`, `MANAGED_FOLDER_LINK`
- `--dataset` binds tile to a specific dataset (for INLINE_DATASET_EDIT, UPLOAD_DATASET_SET_FILE, DOWNLOAD_DATASET)
- `--behavior INLINE_UPLOAD_REDETECT_AND_INFER` is best for upload tiles (auto-detects schema)
- `--definition @tile.json` overrides all shortcut flags for complex tiles (e.g., PROJECT_VARIABLES_EDIT with params)
- `set-section --text` supports HTML: `<i class="icon-warning-sign"></i>`, `<b>bold</b>`, wiki links `[text](article:ID)`
- See `dataiku` skill's `references/app-designer.md` for full tile/param type reference and UX patterns

## app

```bash
dku app list [-o FORMAT]
dku app get APP_ID [-o json]
dku app list-instances APP_ID [-o FORMAT]
dku app create-instance APP_ID --key INSTANCE_KEY --name NAME [--wait/--no-wait]
```

- App ID format: `PROJECT_<project_key>` for project-based apps, `PLUGIN_<plugin>_<component>` for plugin apps
- `list` shows all app templates on the instance
- `list-instances` shows existing instances of a specific app
- `create-instance` creates a new project from the app template. `--key` must be globally unique

## rag

```bash
dku rag list [-P PROJECT] [-o FORMAT]
dku rag create NAME --kb KB_ID --llm LLM_ID [-P PROJECT] [-o FORMAT]
dku rag get RAG_ID [-P PROJECT] [-o FORMAT]
dku rag delete RAG_ID [-P PROJECT] [--yes]
dku rag get-definition RAG_ID [-P PROJECT] [-o json]
dku rag set-definition RAG_ID --definition JSON [-P PROJECT]
```

- `create` ties a knowledge bank + LLM into a RAG LLM. Use after building an embed recipe
- The LLM ID for use elsewhere is `retrieval-augmented-llm:<RAG_ID>`
- Settings are nested: `versions[0].ragllmSettings` contains `llmId` and `kbRef`

## model-comparison

```bash
dku model-comparison list [-P PROJECT] [-o FORMAT]
dku model-comparison create NAME --type PREDICTION_TYPE [-P PROJECT] [-o FORMAT]
dku model-comparison get COMPARISON_ID [-P PROJECT] [-o json]
dku model-comparison add-model COMPARISON_ID --model FULL_MODEL_ID [-P PROJECT]
dku model-comparison remove-model COMPARISON_ID --model FULL_MODEL_ID [-P PROJECT]
dku model-comparison delete COMPARISON_ID [--yes] [-P PROJECT]
```

- Types: BINARY_CLASSIFICATION, REGRESSION, MULTICLASS, TIMESERIES_FORECAST, CAUSAL_BINARY_CLASSIFICATION, CAUSAL_REGRESSION
- Full model IDs: `S-PROJ-modelId-versionId` (saved model), `A-PROJ-analysisId-taskId-...` (lab model), `ME-PROJ-storeId-evalId` (model evaluation)
- `add-model`/`remove-model` modify the comparison then save automatically

## streaming

```bash
dku streaming list [-P PROJECT] [-o FORMAT]
dku streaming create NAME --type TYPE [--connection CONN] [--topic TOPIC] [--url URL] [-P PROJECT]
dku streaming get NAME [-P PROJECT] [-o json]
dku streaming delete NAME [--yes] [-P PROJECT]
dku streaming schema NAME [-P PROJECT] [-o FORMAT]
dku streaming set-schema NAME --definition JSON [-P PROJECT]
```

- Types: kafka, httpsse, SQS, KDBPlus
- `create` for Kafka: use `--connection` + `--topic`. For HTTP SSE: use `--url`
- `schema`/`set-schema` manage the column schema independently of the endpoint settings

## wiki

```bash
dku wiki list [-P PROJECT] [-o FORMAT]
dku wiki create TITLE [--body TEXT] [-P PROJECT] [--if-not-exists]
dku wiki get ARTICLE_ID [-P PROJECT] [-o FORMAT]
dku wiki update ARTICLE_ID [--body TEXT] [--title TEXT] [-P PROJECT]
dku wiki delete ARTICLE_ID --confirm [-P PROJECT]
```

- `update` changes body and/or title. Body accepts literal, `@file.md`, or `-` for stdin.
- `delete` requires `--confirm` / `--yes` / `-y` flag.

## notebook

Manage Jupyter and SQL notebooks.

```bash
dku notebook list [--type jupyter|sql] [-P PROJECT] [-o FORMAT]
dku notebook get NAME [-P PROJECT] [-o FORMAT]
dku notebook create NAME [-P PROJECT]
dku notebook delete NAME [-P PROJECT]
dku notebook sessions [-P PROJECT] [-o FORMAT]
dku notebook stop NAME [--session SESSION_ID] [-P PROJECT]
dku notebook clear-outputs NAME [-P PROJECT]
dku notebook history NAME [-P PROJECT] [-o FORMAT]
```

- `list` combines Jupyter + SQL notebooks; use `--type` to filter
- `history` is for SQL notebooks only
- `sessions` lists all running notebook kernels in the project
- `stop` kills a notebook's kernel; `--session` targets a specific session

---

## discussion

Manage discussions/comments on any DSS object.

```bash
dku discussion list --type TYPE --name NAME [-P PROJECT] [-o FORMAT]
dku discussion get DISCUSSION_ID --type TYPE --name NAME [-P PROJECT] [-o FORMAT]
dku discussion create --type TYPE --name NAME --topic TOPIC --message MSG [-P PROJECT]
dku discussion reply DISCUSSION_ID --type TYPE --name NAME --message MSG [-P PROJECT]
```

- `--type`: dataset, recipe, scenario, model, dashboard, insight
- `--name`: the object's name/ID to attach the discussion to
- Works on any DSS object that supports `get_object_discussions()`

---
