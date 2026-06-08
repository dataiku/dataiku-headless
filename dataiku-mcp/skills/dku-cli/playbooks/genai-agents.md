# GenAI & Agents

Build LLM-over-rows, RAG, and agents with `dku`. Pick the lowest rung that fits:
prompt/LLM recipe → embed + KB + RAG → visual (tool-using) agent → structured
(deterministic multi-step) agent. Get exact flags from `--help`; open
`references/agent-blocks.md` for block/graph/tool JSON.

**Discover IDs first, never hardcode.** LLM IDs are `provider:connection:model` and
instance-specific.
- Completion: `dku llm list -P PROJ -o json | jq -r '.[].id'`
- Embedding (REQUIRED for embed/KB/eval — hidden by default):
  `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ`
- Agent-as-LLM: `agent:AGENT_ID`. RAG-as-LLM: `retrieval-augmented-llm:RAG_ID`.

**Expose Mesh LLMs to external tools (DSS 14+):** every project has an OpenAI-compatible
endpoint at `<DSS_HOST>/public/api/projects/<PROJECT_KEY>/llms/openai/v1/`. Point any
OpenAI-API tool at it to route completions through DSS with governance / guardrails / cost
controls applied. Auth with a DSS API key as bearer token. DSS can also be exposed as an
**A2A server** (JSON-RPC / HTTP-SSE) so external agent frameworks call DSS agents as remote
agents.

## Canonical commands

```bash
# LLM / Prompt recipe
dku llm list -P PROJ -o json | jq -r '.[].id'
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ
dku recipe create-prompt NAME -i INPUT --output-ds OUT --completion-llm LLM_ID --prompt '...{{var}}...' --input-var NAME=COL -P PROJ
dku job run --target OUT --type NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait -P PROJ

# Embed → Knowledge Bank
dku recipe create-embed NAME --input DS --output-kb KB --embedding-llm LLM_ID --embed-column COL -P PROJ
dku recipe run NAME -P PROJ --wait
dku knowledge search KB --query "..." -P PROJ
dku rag create NAME --kb KB_ID --llm LLM_ID -P PROJ

# Visual agent (TOOLS_USING_AGENT)
dku agent create NAME -P PROJ
dku agent add-tool AGENT_ID --tool TOOL_ID -P PROJ
dku agent set-prompt AGENT_ID --prompt @sys.txt --new-version --activate -P PROJ

# Structured agent (deterministic blocks)
dku agent create NAME --type STRUCTURED_AGENT -P PROJ
dku agent-block add AGENT_ID --set-start -b @block.json -P PROJ
dku agent-block get-graph AGENT_ID -P PROJ -o json
dku agent-block set-graph AGENT_ID -d @graph.json -P PROJ
dku agent-block get-graph AGENT_ID -P PROJ -o json | jq '.blocks[]|{id,nextBlock,defaultNextBlock}'

# Agent evaluation
dku evaluation-store create NAME --flavor LLM --task-type QUESTION_ANSWERING -P PROJ
dku agent-review create REV_NAME -P PROJ
dku agent-review run REV_NAME -P PROJ --wait
dku agent-review results REV_NAME --run RUN_ID --by-trait -P PROJ
```

---

## 1. LLM / Prompt recipe over rows

**When:** classify, extract, summarize, or transform every row with one LLM call per row.
This is the default for "run an LLM over a dataset".

**Sequence** (`dku recipe create-prompt` — the dedicated command, TEXT-only mode):
1. Discover `LLM_ID`.
2. `dku recipe create-prompt NAME -i INPUT --output-ds OUT --completion-llm "$LLM_ID"
   --prompt 'PROMPT with {{var}}' --input-var NAME=COLUMN -P PROJ` — it AUTO-CREATES the
   output dataset and binds `{{var}}` template placeholders to input columns via
   `--input-var`. Flags live in `--help`; deeper payload schema →
   `references/prompt-recipe-payload.md` (agent block graphs are in
   `references/agent-blocks.md`).
3. First build (single fresh recipe): `dku job run --target OUT --type
   NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait`. Use `RECURSIVE_BUILD` instead
   when upstream datasets must build too.
4. Verify: `dku dataset head OUT -P PROJ -n 5`, and confirm the recipe shape with
   `dku recipe get-definition NAME -o json` (`prompt.promptMode=PROMPT_TEMPLATE_TEXT`,
   `llmId`, `textPromptTemplateInputs`).

Multi-line prompts: pass `@file.txt` or `-` (stdin) to `--prompt` — a backslash `\n`
inside a literal string stays literal.

**Gotchas + fix:**
- `recipe run` alone returns an empty output schema → always use `job run
  --auto-update-schema` on first build.
- `resultValidation.expectedFormat: "JSON"` crashes at build (NPE) → use `"NONE"`
  and parse `llm_output` downstream with a Prepare recipe + `JSONFlattener` step.
- `{{var}}` rendering literally → the placeholder has no matching
  `textPromptTemplateInputs` entry, or its `datasetColumnName` is absent from the
  input schema. Cross-check `dku dataset schema INPUT`.
- Output always appends 5 fixed columns; only `llm_output` has content. Drop the
  rest with `add-delete-columns` in a Prepare recipe.

**Batch an agent over rows:** set the prompt recipe's `payload.llmId =
"agent:AGENT_ID"` (agent exposed via LLM Mesh). No `run_conversation()` API exists.

**Enterprise Asset Library (governed prompts):** the `dku eal` group manages
instance-scoped, reusable governed prompts (no `-P`). `eal get-prompt -o json` returns
`content` — reuse a governed prompt instead of re-writing it inline. Prompt Studios are
UI-only (no CLI/`dataikuapi` surface); for programmatic prompt work use `dku llm
completion` (ad-hoc), `dku recipe create-prompt` (in-flow), and `dku eal` (governed).

---

## 2. Embed → Knowledge Bank → RAG retrieval

**When:** semantic search / RAG over a text column or document folder.

**Sequence (text column → KB):**
1. `EMBED_LLM=$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[0].id')`
2. `dku recipe create-embed NAME --input DS --output-kb KB --embedding-llm "$EMBED_LLM" --embed-column COL -P PROJ`
3. `dku recipe run NAME -P PROJ --wait` — **the KB is empty until this runs.**
4. Verify: `dku knowledge search KB --query "test" -P PROJ`.

**Document folder → KB (DSS 14.5+, canonical):** use `create-embed-docs --input-folder
FOLDER_ID` (wires `embed_documents.inputs.main` straight to the managed folder; pass
`--vlm` for scanned PDFs). Get the ID with
`dku folder list -P PROJ -o json | jq -r '.[]|select(.name=="x").id'`.

**RAG LLM (KB + completion LLM bundled):**
`KB_ID=$(dku knowledge list -P PROJ -o json | jq -r '.[]|select(.name=="KB").id')` →
`dku rag create "My RAG" --kb "$KB_ID" --llm "$LLM_ID" -P PROJ`. Attach to an agent as
LLM source `retrieval-augmented-llm:RAG_ID`, or expose to a STANDARD_REACT block via a
VectorStoreSearch tool (section 5).

**Gotchas + fix:**
- Vector store defaults to CHROMA; FAISS can fail silently on some installs — leave the default.
- Omitting `--embed-column` → build fails "Embedding column missing".
- Using a completion LLM as `--embedding-llm` → must use a `TEXT_EMBEDDING_EXTRACTION` ID.
- `create-embed-docs` with a legacy FilesInFolder dataset (DSS 14.4) fails "managed
  folder does not exist" → use `--input-folder`, or fall back to materializing text into
  a CSV and running plain `create-embed`.
- Per-file rules: `filter` conditions target synthetic columns with SPACES (`"file
  name"`, `"file extension"`) — underscore forms silently never match.

**Chunk/embedding tuning (choices `--help` can't make for you):**
- Target **256–512 tokens** per chunk, **10–20% overlap** — but the `create-embed-docs`
  fields are in **characters** (`chunkSizeCharacters`/`chunkOverlapCharacters`), so
  multiply by ~4 (≈1024–2048 chars, ≈10–20% overlap). Chunking mode by content —
  Sentence (prose), Paragraph (structured docs), Recursive (mixed), Semantic (topic).
- Embedding model dims are **fixed per KB and unchangeable after embedding** — pick up
  front: text-embedding-3-large=3072, -small=1536, Cohere embed-v3=1024, Titan=1536.
- **Vector store + similarity metric are fixed at KB creation** — KBs support Milvus/Zilliz
  (besides Chroma); similarity metric (cosine / dot product / Euclidean) is chosen up front
  and unchangeable after.

**Mesh capability facts (DSS 14):**
- **Reranking** (`llm.new_reranking()`, e.g. Cohere) improves RAG *precision* — reach for it
  when retrieval recall is fine but the top-K is noisy, not when recall is the problem.
- **Image generation** via `llm.new_images_generation()` routes through the Mesh like any
  completion.
- `create-embed-docs` recipe-settings knobs (patch via `set-settings`): vector-store sync
  is `payload.vectorStoreUpdateMethod` on **14.5+** (`syncMode` is a silent no-op now);
  `documentSplittingMode ∈ {NONE,RECURSIVE,PARAGRAPH,SENTENCE}`, `chunkSizeCharacters`,
  `chunkOverlapCharacters`; per-pattern VLM overrides in `params.rules[]` (each with its
  own `extractionMode`/`vlmId`/`prompt`), global defaults `params.extractionMode`/
  `params.defaultVlmId`/`params.allOtherRule`.

---

## 3. Visual agent (conversational / tool-using)

**When:** single-turn Q&A, conversational, or ad-hoc tool use where the LLM decides when
to call tools. `TOOLS_USING_AGENT` is the simple, reliable default — the right choice for
a basic "LLM + tools" agent.

**`agent add-tool` ONLY works on `TOOLS_USING_AGENT`** — it errors on `STRUCTURED_AGENT`
("add-tool only supports TOOLS_USING_AGENT"). Structured agents attach tools *inside*
their blocks (a `CORE_LOOP` with `tools:[{type:"EXPLICIT_TOOL","toolRef":ID}]` +
`passConversationHistory:true`); a lone `CORE_LOOP` with no emit/output path returns
`response:null`. See section 4 and `references/agent-blocks.md`.

**Sequence:**
1. `dku agent create NAME -P PROJ` (default type), set LLM and system prompt.
2. Create/attach tools (section 5): `dku agent add-tool AGENT_ID --tool TOOL -P PROJ`.
3. For RAG, set the agent's LLM to `retrieval-augmented-llm:RAG_ID`, or attach a
   VectorStoreSearch tool.

**Versioning gotcha + fix:** never edit the active version in place when iterating
prompts. Use `dku agent set-prompt AGENT_ID --prompt @sys.txt --new-version --activate`
(also on `set-llm`/`add-tool`). Setting `activeVersion` in raw JSON alone does NOT
persist server-side — the CLI handles deep-copy + saved-model activation.

---

## 4. Structured agent (deterministic multi-step / SVA)

**When:** multi-step pipeline with defined stages, guaranteed coverage of every item,
audit/compliance, HITL gates, parallel gathering, or report generation. `STRUCTURED_AGENT`.

**Sequence (get-graph → patch → set-graph is the reliable path):**
1. `dku agent create NAME --type STRUCTURED_AGENT -P PROJ` — **must be this type or
   blocks add (exit 0) but never persist.**
2. Add blocks: `dku agent-block add AGENT_ID --set-start -b @block.json -P PROJ` (one
   `--set-start`). Block JSON schemas → `references/agent-blocks.md`.
3. `dku agent-block get-graph AGENT_ID -P PROJ -o json > /tmp/g.json`.
4. Patch wiring in Python (`nextBlock` / `defaultNextBlock` / `validNextBlocksFromCode`
   / ROUTING clauses), then `dku agent-block set-graph AGENT_ID -d @/tmp/g.json -P PROJ`.
5. Verify: `dku agent-block get-graph AGENT_ID -o json | jq '.blocks[]|{id,nextBlock,defaultNextBlock}'`.

`connect` is a convenience shortcut for simple `LLM_REQUEST`/`ROUTING`/`STANDARD_REACT`
wiring only — it errors on PYTHON_CODE (by design).

**Gotchas + fix (the load-bearing ones):**
- **Wiring:** most blocks use `nextBlock`; STANDARD_REACT/CORE_LOOP uses
  `defaultNextBlock`; PYTHON_CODE ignores both — `yield NextBlock("id")` from
  `process()` and declare `validNextBlocksFromCode: ["id"]`.
- **CORE_LOOP with no `defaultNextBlock` returns `response:null` silently** —
  always set `defaultNextBlock` to an `EMIT_OUTPUT` block. Verify wiring with
  `dku agent-block get-graph AGENT_ID -o json | jq '.blocks[]|{id,nextBlock,defaultNextBlock}'`.
- **Every CORE_LOOP / LLM_REQUEST / MANDATORY_TOOL_CALL needs its own `llmId`** — the
  agent-level LLM is NOT inherited (DSS 14.5+). Runtime error: "Please select a valid LLM".
- **Unique block IDs** — duplicates make DSS pick the wrong one.
- **ROUTING needs `defaultNextBlockIfNoClauseMatch`** — at minimum an EMIT_OUTPUT.
- **`SAVE_TO_STATE` needs `outputKey`** (14.5+) / `outputStateKey` (13.x) or output is lost.
- **`SET_STATE_ENTRIES` empty value crashes CEL** → use `"''"`, `"0"`, `"[]"`, never `""`.
- **`"[]"` is a JSON string, not a list** — PYTHON_CODE must
  `json.loads()` before `.append()`/`.extend()`.
- **First block needs `passConversationHistory: true`** if it must see the user query,
  else the LLM replies "Please provide..."; set `false` on pure-analysis blocks to save tokens/cost.
- **PARALLEL branches must write distinct keys** — same key = last-write-wins race.
- **FOR_EACH doesn't accumulate** — init the array with SET_STATE_ENTRIES before the
  loop, append in a PYTHON_CODE block per iteration. Access the item via
  `{{forEachInputKey}}` (no `scratchpad.` prefix).
- Streaming to state is wasted → `streamOutput: false` unless `ADD_TO_MESSAGES`.
- **Scale:** FOR_EACH loops are fine to ~50 items; 200–500 risks timeouts (batch into
  sub-arrays); 500+ → split across agents. Keep total state **< 1 MB** — store extracted
  structured fields, never raw document text (oversized state fails at runtime, not at build).

---

## 5. Agent tools

**When:** give an agent a capability (KB search, dataset lookup, web search, semantic
model query, custom Python).

**Sequence:**
1. List built-in types: `dku agent-tool types` (no `-P`; project-independent).
2. Create: `dku agent-tool create NAME --type TYPE [type-specific flags] -P PROJ`.
3. Attach to agent (section 3/4) or reference by tool ID in a STANDARD_REACT block.
4. Tweak params: `dku agent-tool set-definition TOOL_ID -d '{"params":{...}}'` (shallow merge).

**Common tools:**
- `VectorStoreSearch --kb NAME_OR_ID` — RAG retrieval. CLI resolves name→ID into
  `params.knowledgeBankRef`; verify it's the ID, not the display name, or the tool
  breaks at test time with "knowledge bank does not exist".
- `DatasetRowLookup --dataset DS` — structured lookups.
- Plugin tools use `Custom_agent_tool_<plugin>_<tool>` type names.

**Gotchas + fix:**
- **No built-in `PythonFunction` tool type.** Custom Python tools must be built as a
  plugin (`python-agent-tools/` folder) and pushed with `dku plugin push`. Tool/plugin
  JSON + `BaseAgentTool` lifecycle → `references/agent-blocks.md`.
- To discover any tool's exact `params` shape, build it once in the DSS UI then
  `dku agent-tool get TOOL_ID -o json`.

---

## 6. Agent evaluation

**RAG / LLM output quality (`create-llm-eval`):** eval store + scored/metrics datasets
must already exist. Create store with `dku evaluation-store create NAME --flavor LLM`
(or `AGENT`). Metrics: `answerRelevancy`, `faithfulness`, `contextRelevancy` (QA);
`toolCallExactMatch`, `toolCallPartialMatch`, `agentGoalAccuracyWithoutReference`
(agent). Task types: `QUESTION_ANSWERING`, `SUMMARIZATION`, `CLASSIFICATION`.

**Agent quality, LLM-as-judge (`agent-review`):**
1. `create` → `set-agent` → `set-llm` → `add-trait` (×N) → `create-test` / `import-tests` → `run`.
2. **Wire each trait to the fields it scores:** every trait defaults to
   needs-reference=ON / needs-expectations=OFF regardless of wording. Tone/format/safety
   traits need `--no-needs-reference`; expectation-scored traits need
   `--needs-expectations`. Mismatch = traits silently skip tests.
3. Results: `dku agent-review results REV --run RUN_ID --by-trait`.

**Gotchas + fix:**
- `agent-review run` **re-executes the agent fresh per test** (does not re-score a
  cached dataset). A slow agent → a slow review and burns API quota → iterate with
  `--no-wait` + `list-runs`, compare runs with `agent-review compare --runs A,B,C`.
- `nlp_agent_evaluation` pins `outputColumnName=llm_raw_response`, a JSON envelope
  `{"ok":true,"text":"..."}` — custom regex metrics MUST unwrap `text` first or match
  nothing (symptom: pass-rate stuck ~10–20%). You cannot change `outputColumnName`
  (DSS reverts it). In metric Python avoid `"""docstrings"""` (JSON-escape breaks them)
  — use `'''` or `#`.

**Eval-store traps (verified live, DSS 14.6):**
- **`llmTaskType` is required** — without `--task-type` the build fails late "You need
  to select a Task".
- **`groundTruthColumnName` must be ABSENT, never `""`** — an empty string triggers a
  column lookup and fails. The CLI omits it when `--ground-truth-col` is unset; patching
  JSON, delete the key rather than blanking it.
- **Plain-text logs → `nlp_llm_evaluation` with `inputFormat: "CUSTOM"`** —
  `nlp_agent_evaluation` runs `ast.literal_eval` on the query column and crashes on plain
  text (it expects serialized message structures).
- **Built-in RAGAS metrics (answerRelevancy, faithfulness, …) error without a context
  column.** For evals over raw query/response logs use `customMetrics` (deterministic
  Python) + `customTraits` (LLM-judge) instead of the built-ins.
- **Column mapping re-derives from the dataset** — if `inputColumnName`/`outputColumnName`
  keep reverting, name the columns `llm_raw_query` / `llm_raw_response` (the convention DSS
  derives) and the mapping sticks.
- **Judge/trait LLM must support JSON output** (Anthropic rejects it → traits SKIPPED) —
  see the `responseFormat` caveat in `references/agent-blocks.md`. Agent-review traits
  snapshot their LLM at `add-trait` time → pass `--llm` per trait, or run `agent-review
  set-llm` which back-fills traits with a null `llmId`.
- **Build the store with `dku evaluation-store build <id>`** (or `recipe run <eval_recipe>`
  — its output resolves as MODEL_EVALUATION_STORE; older CLIs failed "dataset does not
  exist: <store_id>").
