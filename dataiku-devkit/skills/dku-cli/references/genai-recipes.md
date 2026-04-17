# GenAI Recipes & RAG Pipelines

GenAI recipe types, embedding models, RAG pipelines, model deployment, and flow investigation patterns.

## Finding Embedding Models (REQUIRED for GenAI workflows)

Most GenAI recipes need an embedding LLM ID. The default `dku llm list` only shows **completion** models — embedding models are hidden unless you specify `--purpose`:

```bash
# Find embedding models (REQUIRED before create-embed, knowledge create, etc.)
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ

# Get just the IDs
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[].id'
```

Use the returned ID for `--embedding-llm` flags on `recipe create-embed`, `recipe create-embed-docs`, `recipe create-llm-eval`, `recipe create-agent-eval`, and `knowledge create`.

## API-Supported Recipe Types (full CLI creation)

| Command | dataikuapi Type | Purpose |
|---|---|---|
| `create-embed` | `nlp_llm_rag_embedding` | Embed text columns -> Knowledge Bank |
| `create-embed-docs` | `embed_documents` | Extract + embed documents -> Knowledge Bank |
| `create-extract` | `extract_content` | Extract structured content from docs (VLM) |
| `create-llm-eval` | `nlp_llm_evaluation` | Evaluate LLM outputs (RAG, QA, summarization) |
| `create-agent-eval` | `nlp_agent_evaluation` | Evaluate agent tool-calling accuracy |

`create-llm-eval` and `create-agent-eval` do not create datasets for you. If you pass `--output-ds` or `--output-metrics`, those datasets must already exist in DSS. The evaluation store must also exist — create it first with `dku evaluation-store create NAME --flavor LLM` (or `--flavor AGENT`).

### `create-embed-docs` + FilesInFolder: known failure → use `create-embed` instead

`create-embed-docs` on a `FilesInFolder` dataset can fail at build time with
`managed folder does not exist: PROJ.DATASET_NAME` — DSS resolves the dataset
name as a folder name internally. When that happens, fall back to:

1. Materialize folder text into a CSV dataset with a single `content` column
   (one row per doc). A small Prepare or Python step over the FilesInFolder
   dataset works — or extract text upstream and upload as CSV.
2. Run `create-embed` (not `create-embed-docs`) on the text column:

```bash
dku recipe create-embed embed_docs \
  --input docs_text \
  --output-kb my_kb \
  --embedding-llm "$LLM_ID" \
  --text-column content -P PROJ
```

`create-embed` is stable with CSV text inputs. `create-embed-docs` is best used
when your input is already a plain dataset of document rows with a text column,
not a file-backed FilesInFolder dataset.

## Prompt Recipe — Programmatic Creation

See `references/prompt-recipe-payload.md` for the full payload schema.

```bash
# 0. Discover the LLM ID — do NOT hardcode it (varies per instance)
LLM_ID=$(dku llm list -P PROJ -o json | jq -r '.[0].id') && \

# 1. Pre-create the output dataset — Prompt Recipes do NOT auto-create outputs
dku dataset create kpi_results --type Filesystem -c filesystem_managed -P PROJ && \
# 2. Create the recipe shell
dku recipe create extract_kpis -t prompt -i input_tasks --output-ds kpi_results -P PROJ && \
# 3. Configure the payload (substitute $LLM_ID into prompt_settings.template.json first)
jq --arg llm "$LLM_ID" '.payload.llmId = $llm' prompt_settings.template.json > prompt_settings.json && \
dku recipe set-settings extract_kpis -P PROJ -s @prompt_settings.json && \
# 4. First build MUST use --auto-update-schema — `recipe run` alone returns an empty schema
dku job run --target kpi_results -P PROJ --type NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait
```

The recipe appends fixed columns `llm_output, llm_validation_status, llm_raw_response, llm_error_message, llm_raw_query` to the input dataset's columns. `llm_output` is the only one with content by default. To parse it downstream, use a Prepare recipe + JSONFlattener — no Python recipe needed:

```bash
dku recipe add-step parse_output --type JSONFlattener \
  --params '{"inCol":"llm_output","flattenArrays":false,"maxDepth":2,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}' \
  -P PROJ
```

### Batch Agent Processing via Prompt Recipe

Run an agent over every row in a dataset using a Prompt recipe:

1. Create agent: `dku agent create NAME --type STRUCTURED_AGENT -P PROJ`
2. Configure block graph, tools, and prompts via CLI
3. Create Prompt recipe: `dku recipe create batch_agent -t prompt -i input_rows --output-ds agent_outputs -P PROJ`
4. Set the Prompt recipe's LLM to `agent:AGENT_ID` (calls the agent via LLM Mesh) — patch `payload.llmId = "agent:AGENT_ID"` via `set-settings`
5. Build: `dku job run --target agent_outputs -P PROJ --type NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait`
6. Verify: `dku dataset head agent_outputs -P PROJ -n 5`

Key: `DSSAgent.as_llm()` is the programmatic interface — Prompt recipes accept `agent:AGENT_ID` as the LLM. There is no `run_conversation()` method.

## RAG Evaluation Flow (1 tool call)

```bash
# End-to-end: embed data -> create eval store + datasets -> configure -> run
dku recipe create-embed embed_step \
  --input qa_documents \
  --output-kb qa_kb \
  --embedding-llm "openai:text-embedding-3-small" \
  --text-column content \
  -P PROJ && \
dku recipe run embed_step -P PROJ --wait && \
dku evaluation-store create my_eval_store --flavor LLM -P PROJ && \
dku dataset create eval_scored --type Filesystem -P PROJ && \
dku dataset create eval_metrics --type Filesystem -P PROJ && \
dku recipe create-llm-eval rag_eval \
  --input rag_responses \
  --eval-store my_eval_store \
  --output-ds eval_scored \
  --output-metrics eval_metrics \
  --task-type QUESTION_ANSWERING \
  --metrics "answerRelevancy,faithfulness,contextRelevancy" \
  --input-col question \
  --output-col answer \
  --ground-truth-col expected \
  --context-col context \
  --completion-llm "openai:gpt-4o" \
  --embedding-llm "openai:text-embedding-3-small" \
  -P PROJ && \
dku recipe run rag_eval -P PROJ --wait
```

## LLM Evaluation Metrics

| Metric Name | Task Type | Description |
|---|---|---|
| `answerRelevancy` | QA | Answer relevance to the question |
| `faithfulness` | QA | Answer grounded in provided context |
| `contextRelevancy` | QA | Retrieved context relevant to question |
| `toolCallExactMatch` | Agent | Exact match on tool calls |
| `toolCallPartialMatch` | Agent | Partial match on tool calls |
| `toolCallPrecisionRecallF1` | Agent | Precision/Recall/F1 for tool calls |
| `agentGoalAccuracyWithoutReference` | Agent | Goal accuracy without ground truth |

## LLM Evaluation Task Types

`QUESTION_ANSWERING`, `SUMMARIZATION`, `CLASSIFICATION`, and others. Use `--task-type` to set.

## Knowledge Bank + Embed Pipeline (create -> configure -> build)

**CRITICAL: Vector store defaults to CHROMA.** FAISS can fail silently on some DSS installations.

```bash
# Step 1: Find an embedding model (REQUIRED)
EMBED_LLM=$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[0].id') && \

# Step 2: Create embed recipe with column specified
dku recipe create-embed embed_my_data \
  --input source_dataset \
  --output-kb my_kb \
  --embedding-llm "$EMBED_LLM" \
  --embed-column text_content \
  -P PROJ && \

# Step 3: Run to populate the KB
dku recipe run embed_my_data -P PROJ --wait && \

# Step 4: Verify
dku knowledge search my_kb --query "test query" -P PROJ
```

**Common mistakes:**
- Using a completion LLM ID instead of an embedding LLM ID (`--purpose TEXT_EMBEDDING_EXTRACTION`)
- Omitting `--embed-column` (build will fail with "Embedding column missing")
- Forgetting to `run` the embed recipe after creating it

## Complete RAG Pipeline (KB -> Embed -> RAG LLM -> Agent)

```bash
# 1. Create KB + embed recipe + build
dku recipe create-embed embed_docs \
  --input source_docs \
  --output-kb my_kb \
  --embedding-llm "openai:text-embedding-3-small" \
  --embed-column content \
  -P PROJ && \
dku recipe run embed_docs -P PROJ --wait && \

# 2. Get the KB ID (needed for RAG LLM creation)
KB_ID=$(dku knowledge list -P PROJ -o json | jq -r '.[] | select(.name == "my_kb") | .id') && \

# 3. Create the RAG LLM that ties KB + LLM together
dku rag create "My RAG" --kb "$KB_ID" --llm "openai:gpt-4o" -P PROJ && \

# 4. Get the RAG LLM ID for agent attachment
RAG_ID=$(dku rag list -P PROJ -o json | jq -r '.[0].id') && \

# 5. Attach to an agent as an LLM source
echo "RAG LLM ID for agent: retrieval-augmented-llm:$RAG_ID"
```

## Model Deployment Pipeline (Train -> Service -> Endpoint -> Package -> Deploy)

```bash
# 1. Create API service
dku api-service create my_predictor -P PROJ && \

# 2. Add prediction endpoint with a deployed model
dku api-service add-endpoint my_predictor \
  -e predict_churn -m saved_model_id -t prediction -P PROJ && \

# 3. Create and publish package
dku api-service create-package my_predictor -P PROJ && \
PKG_ID=$(dku api-service list-packages my_predictor -P PROJ -o json | jq -r '.[0].id') && \
dku api-service publish-package my_predictor --package "$PKG_ID" -P PROJ
```

## Flow Investigation Patterns

```bash
# What uses this dataset? (downstream recipes, analyses)
dku dataset usages my_dataset -P PROJ && \

# Where does this column come from? (upstream lineage)
dku dataset lineage my_dataset --column revenue -P PROJ && \

# Does this dataset exist before creating it?
dku dataset exists my_dataset -P PROJ && echo "exists" || echo "creating..." && \

# What tables are available in this connection?
dku connection schemas my_postgres -P PROJ && \
dku connection tables my_postgres --schema public -P PROJ
```

## Plugin Installation Pattern

```bash
# Install from Dataiku store + create code env
dku plugin install-from-store timeseries-preparation && \
dku plugin create-code-env timeseries-preparation && \

# Or install from git with specific branch
dku plugin install-from-git https://github.com/org/my-plugin.git --checkout v2.0
```
