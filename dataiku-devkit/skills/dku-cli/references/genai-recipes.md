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

### `create-embed-docs`: prefer `--input-folder` for DSS 14.5+ (canonical folder→KB pattern)

DSS 14.5+ wires the `embed_documents` recipe's `inputs.main` to a managed folder
ref directly — no FilesInFolder wrapper dataset needed. The CLI exposes this
via `--input-folder FOLDER_ID`. This is what CHATTERBOX, ATU_CONTRACTS and other
modern RAG flows use.

```bash
# Capture the folder ID once:
FOLDER_ID=$(dku folder list -P PROJ -o json | jq -r '.[] | select(.name=="pdf_inbox").id')

dku recipe create-embed-docs embed_pdfs \
  --input-folder "$FOLDER_ID" \
  --output-kb my_kb \
  --embedding-llm "$EMBED_LLM" \
  --vlm "$VLM_LLM" -P PROJ
```

For DSS 14.4 and earlier, or if you already have a FilesInFolder dataset, the
legacy `--input DATASET` path still works:

```bash
dku folder create-dataset pdf_inbox --dataset pdf_files -P PROJ
dku recipe create-embed-docs embed_pdfs \
  --input pdf_files \
  --output-kb my_kb \
  --embedding-llm "$EMBED_LLM" -P PROJ
```

If neither `--input` nor `--input-folder` is given, the CLI exits with a
prescriptive error showing both invocation shapes.

### `create-embed-docs` + FilesInFolder: known failure (DSS 14.4 / legacy path) → use `create-embed` instead

On DSS 14.4 with a `FilesInFolder` dataset, the build can fail with
`managed folder does not exist: PROJ.DATASET_NAME` — DSS resolves the dataset
name as a folder name internally. The fix is now `--input-folder FOLDER_ID`
(no dataset wrapper). If you're stuck on legacy versions, fall back to:

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

### Custom-metric authoring on `nlp_agent_evaluation`: unwrap the JSON envelope FIRST

`nlp_agent_evaluation` hard-pins its `outputColumnName` to `llm_raw_response`,
and that column is **not** plain text — it's a JSON envelope:

```json
{"ok": true, "text": "## 1. Summary\n## 4. Action items\n..."}
```

A regex-based metric that targets the agent's actual output **must** unwrap the
`text` field first. Otherwise the `##` and `\n` characters are JSON-escaped
(`\\#\\#` etc.) and your regex matches nothing — silently. (Symptom: pass-rates
stuck at ~10–20% even when the agent's outputs look perfect.)

Boilerplate every custom metric should start with:

```python
import json
import re

def _extract_text(raw):
    """Unwrap nlp_agent_evaluation's JSON envelope. Returns plain text or raw."""
    if not raw:
        return ""
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict) and "text" in decoded:
            return decoded["text"]
    except (json.JSONDecodeError, TypeError):
        pass
    return raw

# Example: "agent specified an action in Section 4"
_PAT = re.compile(r"##\s*4\.")

def score(row):
    text = _extract_text(row.get("llm_raw_response", ""))
    return 1.0 if _PAT.search(text) else 0.0
```

Two more `nlp_agent_evaluation` traps — both now surface as CLI errors instead
of silent breakage:

1. **You cannot change `outputColumnName`** via `dku recipe set-settings`. DSS
   silently reverts the edit at save time. The CLI catches that pattern
   pre-send and exits with a prescriptive error pointing here.
2. **The `"""` JSON-escape trap.** If you build metric Python via a JSON
   payload (`set_payload(json.dumps(...))`), `"""docstrings"""` round-trip as
   `\"\"\"` — invalid Python. Use `'''` triple-strings or `# comments`. When
   `dku evaluation-store build` fails, the CLI auto-extracts the activity log
   and tags this pattern when it sees `unexpected character after line
   continuation character`.

### Agent-review runtime semantics (DSS 14.5+)

`dku agent-review run REV --wait` **re-executes the agent fresh** per test case.
It does NOT re-score a pre-computed `agent_answers` dataset. Implications:

- A slow agent → a slow review. A 20-test × 8-trait review against a semantic-
  model-query agent that takes 30 s per test will take ~10 minutes.
- If your test set hits remote APIs, every review run consumes API quota.
- For iteration, prefer `--no-wait` and poll via `dku agent-review list-runs`:

```bash
dku agent-review run REV --no-wait -P PROJ
# Then later:
dku agent-review list-runs REV -P PROJ
dku agent-review results REV --run RUN_ID --by-trait -P PROJ
```

Use `dku agent-review compare REV --runs RUN_A,RUN_B,RUN_C -P PROJ` to drive
the 4-stage iteration loop (baseline → prompt iter → architectural fix →
re-eval). See `references/iteration-loop.md` for the canonical workflow.

### `create-embed-docs` rule filters: synthetic columns use SPACES, not underscores

When a `embed_documents` recipe has per-file rules (`params.rules[]`) gating which
extraction or VLM strategy applies, the `filter.uiData.conditions[].col` fields
that target file metadata are **synthetic columns named with spaces**:

- `"file name"` (not `file_name`)
- `"file extension"` (not `file_extension`)
- `"last modified"` (not `last_modified`)
- `"file size"` (not `file_size`)

Guess the underscore form and DSS silently never matches the rule — the file
falls through to `params.allOtherRule` with no warning. If a sweep "applies VLM
to PDFs only" is silently scanning every file, this is almost always why.
Verify by `dku recipe get-settings RECIPE -o json | jq '.params.rules'` and
checking the actual `conditions[].col` strings.

### `create-embed-docs` payload knobs (DSS 14.5)

The vector-store sync field is `payload.vectorStoreUpdateMethod` on DSS 14.5+
(replaces older `syncMode`). Patching `syncMode` is a no-op on current
instances. Other top-level knobs:

- `documentSplittingMode` ∈ `{"NONE", "RECURSIVE", "PARAGRAPH", "SENTENCE"}`
- `chunkSizeCharacters`, `chunkOverlapCharacters` — chunker config
- `params.extractionMode`, `params.defaultVlmId`, `params.allOtherRule` — global defaults
- `params.rules[]` — per-pattern overrides; each rule has `filter.uiData.conditions[]` (see above) and its own `extractionMode` / `vlmId` / `prompt`

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
