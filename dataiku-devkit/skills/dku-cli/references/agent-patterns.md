# Agent Patterns

Advanced patterns for Structured Visual Agents (SVAs), agent tools, LLM configuration, and agent evaluation.

## Quickstart Recipes

**Tool-calling agent** (create agent + tool + core loop):
```bash
dku agent create NAME --type STRUCTURED_AGENT -P PROJ
dku agent-tool create TOOL_NAME --type DatasetRowLookup --dataset DS -P PROJ
AGENT_ID=$(dku agent list -P PROJ -o json | jq -r '.[] | select(.name=="NAME") | .id')
LLM_ID=$(dku llm list -P PROJ -o json | jq -r '.[0].id')
dku agent-block add "$AGENT_ID" --set-start -b "{\"type\":\"CORE_LOOP\",\"id\":\"loop\",\"llmId\":\"$LLM_ID\"}" -P PROJ
dku agent add-tool "$AGENT_ID" --tool TOOL_NAME -P PROJ
```

**Stateful agent** (conversation memory + summarization):
```bash
dku agent create NAME --type STRUCTURED_AGENT -P PROJ
AGENT_ID=$(dku agent list -P PROJ -o json | jq -r '.[] | select(.name=="NAME") | .id')
dku agent-block add "$AGENT_ID" --set-start -b '{"type":"SET_STATE_ENTRIES","id":"memory"}' -P PROJ
dku agent-block add "$AGENT_ID" -b '{"type":"EMIT_OUTPUT","id":"output","templateType":"CEL_EXPANSION","template":"","addToMessages":true}' -P PROJ
```

For ROUTING and other non-trivial graphs, use the `get-graph` → patch → `set-graph` workflow below.

## Structured Visual Agent (SVA) Graph — Canonical Workflow

**Use `set-graph` as the primary pattern.** The `dku agent-block connect` command does not support `PYTHON_CODE` blocks (exits with an error — use `validNextBlocksFromCode` + `NextBlock()` yield instead). For `STANDARD_REACT`, `connect` works correctly (sets `defaultNextBlock` automatically). For any non-trivial graph, always use `get-graph -> patch JSON -> set-graph`:

```bash
# 1. Add all blocks
dku agent-block add AGENT_ID -b @parse_block.json --set-start -P PROJ && \
dku agent-block add AGENT_ID -b @routing_block.json -P PROJ && \
dku agent-block add AGENT_ID -b @python_code_block.json -P PROJ && \
dku agent-block add AGENT_ID -b @react_block.json -P PROJ

# 2. Export the graph
dku agent-block get-graph AGENT_ID -P PROJ -o json > /tmp/graph.json

# 3. Patch connections in Python (nextBlock, defaultNextBlock, etc.)
python3 -c "
import json
g = json.load(open('/tmp/graph.json'))
# wire blocks by editing g['blocks']
json.dump(g, open('/tmp/graph.json', 'w'))
"

# 4. Push the patched graph back
dku agent-block set-graph AGENT_ID -d @/tmp/graph.json -P PROJ
```

**`connect` is a convenience shortcut only.** Use it for simple `LLM_REQUEST -> ROUTING`, `STANDARD_REACT -> EMIT_OUTPUT`, or other direct wiring. For `PYTHON_CODE` blocks, `connect` will error — use `set-graph` with `validNextBlocksFromCode` and `NextBlock()` yield in `process()`.

## VectorStoreSearch Tool — KB Reference

`dku agent-tool create --type VectorStoreSearch --kb NAME_OR_ID` writes the
knowledge bank ID to `params.knowledgeBankRef`. The CLI resolves the name to
its ID before saving — DSS expects the ID at runtime; a raw name here breaks
the tool with "knowledge bank does not exist" at test time. Verify after
creation:

```bash
dku agent-tool get TOOL_ID -P PROJ -o json | jq .params.knowledgeBankRef
# expect the KB id (e.g. "aG2lDxD"), not the display name
```

## Plugin-Based Tools

```bash
# Plugin tools use Custom_agent_tool_<plugin>_<tool> type format
dku agent-tool create "Web Search" \
  --type Custom_agent_tool_google-search-tool_google-search-tool \
  -P PROJ
```

> **There is no built-in PythonFunction type.** Custom Python tools MUST be built as plugins (`python-agent-tools/` folder) and deployed via `dku plugin push`. See the `dataiku` skill's `references/llm-tools.md` for the full plugin tool development guide.

## Discovering Tool Types

```bash
# List built-in types (does NOT accept -P — project-independent)
dku agent-tool types
```

## Updating Tool Definitions

```bash
# Merge params (shallow merge on top-level keys)
dku agent-tool set-definition TOOL_ID -d '{"params": {"maxRecords": 10}}' -P PROJ

# From a file
dku agent-tool set-definition TOOL_ID -d @tool-config.json -P PROJ
```

> **Tip:** To discover the exact params structure for any tool type, create one in the DSS UI first, then run `dku agent-tool get TOOL_ID -P PROJ -o json` to inspect its full settings.

## LLM ID Format & Discovery

LLM IDs in DSS follow the pattern `provider:connection:model`. Use `dku llm list` to discover available IDs:

```bash
# Completion models (default)
dku llm list -P PROJ -o json | jq -r '.[].id'

# Embedding models (MUST use --purpose for GenAI workflows)
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[].id'
```

## Agent Evaluation Workflow

Use `agent-review` to evaluate agent quality with LLM-as-judge traits:

```bash
# Create review, configure, add tests, run evaluation (1 tool call)
dku agent-review create "Quality Check" -P PROJ && \
REVIEW_ID=$(dku agent-review list -P PROJ -o json | jq -r '.[0].id') && \
dku agent-review set-agent "$REVIEW_ID" --agent MY_AGENT -P PROJ && \
dku agent-review set-llm "$REVIEW_ID" --llm "openai:...:gpt-4o" -P PROJ && \
dku agent-review add-trait "$REVIEW_ID" --name "Accuracy" --criteria "Does the answer match the reference answer?" -P PROJ && \
dku agent-review add-trait "$REVIEW_ID" --name "Helpfulness" --criteria "Is the response helpful and actionable?" --no-needs-reference -P PROJ && \
dku agent-review create-test "$REVIEW_ID" -q "What is our refund policy?" -r "30-day money back guarantee" -P PROJ && \
dku agent-review run "$REVIEW_ID" -P PROJ
```

**Wire each trait to the test fields it scores against.** `add-trait` has two flags
that decide which per-test fields the judge sees — they must match how you built the
tests with `create-test --reference` / `--expectations`:

| Trait kind | Flags | Why |
|---|---|---|
| Accuracy / correctness vs a reference | (defaults) | `--needs-reference` is ON by default; the judge compares against `-r`. Only scored on tests that HAVE a reference. |
| Tone / format / safety / helpfulness | `--no-needs-reference` | These don't compare to a reference. Without this flag DSS still requires one, so they skip reference-less tests. |
| Scored against per-test expectations | `--needs-expectations` (often with `--no-needs-reference`) | OFF by default, so the judge never sees `-e` expectations unless you turn it on. |

DSS defaults **every** trait to needs-reference=ON / needs-expectations=OFF regardless
of the criteria wording, so set these explicitly or your traits and tests won't wire
together.

```bash
# Check results (tool call 2)
RUN_ID=$(dku agent-review list-runs "$REVIEW_ID" -P PROJ -o json | jq -r '.[0].id') && \
dku agent-review results "$REVIEW_ID" --run "$RUN_ID" -P PROJ -o json
```

For bulk testing, import from a dataset:
```bash
dku agent-review import-tests "$REVIEW_ID" --dataset test_cases --query-column question --reference-column answer -P PROJ
```

## Agent Hub Notes

- **Cannot create** Agent Hub via CLI (it's a plugin webapp — create in DSS UI first).
- `--hub` auto-detects when one hub exists; required when multiple exist.
- Config is shallow-merged, not replaced.
- Agent IDs use `PROJECT:agent:ID` format.
