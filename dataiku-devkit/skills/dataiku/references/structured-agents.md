# Structured Visual Agents — Design Guide

Build production-grade AI agents using Dataiku's deterministic block graph. Unlike free-form agents that loop indefinitely with variable results, structured visual agents (SVAs) guarantee consistent, auditable outputs through explicit control flow.

> **API reference:** Block type schemas and connection models are documented inline below.
> **CLI reference:** For `dku agent-block` commands, see `skills/dku-cli/references/commands.md`.
> **Custom plugin blocks:** For building your own block types as plugins, see `references/visual-agent-blocks.md`.
>
> **Version caveat:** Block type names differ across DSS versions. DSS 13.x uses `STANDARD_REACT` / `EMIT_OUTPUT`.
> DSS 14.5+ uses `CORE_LOOP` / `GENERATE_OUTPUT`. Settings path: `TOOLS_USING_AGENT` → `toolsUsingAgentSettings`,
> `STRUCTURED_AGENT` → `structuredAgentSettings`. The CLI auto-detects the correct path.
> **Always inspect a working agent on your target instance before building.**

---

## When to Use SVAs (vs Simple Agents)

| Use SVAs When | Use Simple Agents When |
|---------------|----------------------|
| Multi-step pipeline with defined stages | Single-turn Q&A or conversational |
| Compliance, audit, or regulatory workflows | Exploratory research tasks |
| Guaranteed processing of every item in a list | Ad-hoc tool usage at LLM's discretion |
| Parallel data gathering from multiple sources | Simple tool-calling pattern |
| Human-in-the-loop approval gates | No approval flow needed |
| Report/document generation at the end | Response is just text |
| Reproducible outputs across runs | Variability is acceptable |

---

## Architecture: How SVAs Work

SVAs are `TOOLS_USING_AGENT` agents. Blocks are a **flat list** with connections via `nextBlock` fields — no nested graph structure.

**DSS 14.5+:** blocks live in `structuredAgentSettings` (not `toolsUsingAgentSettings`). There is no `mode` field — block-graph mode is implicit when blocks exist.

```
Agent Settings (DSS 14.5+)
└─ versions[0].structuredAgentSettings
   ├─ startingBlockId: "first_block"
   ├─ blocks: [ ...flat list of block definitions... ]
   └─ nextTurnBehaviour: "STARTING_BLOCK" | "SMART" | "LAST_BLOCK"
```

**Important:** Always run `dku agent get <id> -o json -P PROJ` on a working agent to confirm the actual path before building — it differs from older DSS versions.

**Two storage layers:**
- **State** (`state["key"]`) — Persistent across the turn. Shared between all blocks. Use for accumulated results, final outputs.
- **Scratchpad** (`scratchpad["key"]`) — Temporary. Scoped to current execution branch. Use for intermediate parsing, loop iteration items.

---

## Block Types (19 in DSS 14.5+) — When and Why

### Decision Framework

```
Need to call an LLM?
├─ No tools needed → LLM_REQUEST
├─ Tools, LLM decides when → STANDARD_REACT / CORE_LOOP
├─ Must call one specific tool → MANDATORY_TOOL_CALL
└─ Multi-perspective analysis → REFLECTION

Need to call a tool WITHOUT an LLM?
└─ Preset arguments → MANUAL_TOOL_CALL

Need control flow?
├─ Conditional branch → ROUTING
├─ Run blocks concurrently → PARALLEL
├─ Iterate over a list → FOR_EACH
└─ Custom logic / dynamic routing → PYTHON_CODE

Need data management?
├─ Initialize or update state → SET_STATE_ENTRIES
├─ Initialize or update scratchpad → SET_SCRATCHPAD_ENTRIES
└─ Compress long conversations → CONTEXT_COMPRESSION

Need output?
├─ Message to user → EMIT_OUTPUT / GENERATE_OUTPUT
├─ Document (DOCX/PDF) → GENERATE_ARTIFACT
└─ Hand off to another agent → DELEGATE_TO_OTHER_AGENT

Need prompt rewriting?
└─ Modify user message before LLM → EDIT_LAST_USER_MESSAGE

Need plugin-defined behavior?
└─ Custom block from plugin → CUSTOM (see references/visual-agent-blocks.md)
```

---

### 1. LLM_REQUEST — Non-Agentic LLM Call

**WHY:** Call an LLM for a single-shot task — classification, extraction, summarization, analysis. No tools, no loops. The LLM processes input and returns structured or free-text output.

**WHEN TO USE:**
- Document parsing / structured extraction (with `responseFormat: json`)
- Intent classification for routing decisions
- Summarizing accumulated results at the end
- Gap analysis when all data is already in state/scratchpad

**WHEN NOT TO USE:**
- Need to search a knowledge bank → use STANDARD_REACT with KB tool
- Need multiple tool calls → use STANDARD_REACT
- Need guaranteed tool execution → use MANDATORY_TOOL_CALL

**KEY FIELDS:**
- `outputMode: "SAVE_TO_STATE"` or `"SAVE_TO_SCRATCHPAD"` — for downstream blocks
- `outputMode: "ADD_TO_MESSAGES"` — for user-facing output
- `responseFormat: {type: "json", strict: true}` — forces schema compliance
- `passConversationHistory: false` — for stateless analysis blocks (faster, cheaper)
- `streamOutput: true` — only when `outputMode: "ADD_TO_MESSAGES"` (streaming to state is wasted)

**PATTERN — Parse then route:**
```
LLM_REQUEST (parse, save to scratchpad) → ROUTING (branch on parsed type)
```

---

### 2. ROUTING — Conditional Branching

**WHY:** Direct the workflow down different paths based on data. The deterministic alternative to letting an LLM decide what to do next.

**WHEN TO USE:**
- Branch on document type (amendment vs. new regulation)
- Route based on classification results
- Gate on validation status (approved vs. rejected)
- Skip processing when data is missing

**TWO CLAUSE TYPES:**

| Type | Use When | Example |
|------|----------|---------|
| `EXPRESSION` (CEL) | Exact value checks, comparisons, boolean logic | `state["intent"] == "billing"` |
| `LLM_BASED` | Fuzzy/semantic decisions that can't be expressed as rules | "Has the user provided enough information?" |

**CEL EXPRESSION SYNTAX:**
```
state["classification"]["intent"] == "question"
scratchpad["amendment"]["document_type"] == "AMENDMENT"
state["risk_score"] > 0.7
state["items"].size() > 0
```

**DESIGN RULE:** Prefer `EXPRESSION` over `LLM_BASED`. CEL expressions are deterministic, fast, and free. Only use LLM-based clauses for genuinely ambiguous decisions.

---

### 3. SET_STATE_ENTRIES — Initialize or Update Variables

**WHY:** Explicitly set state/scratchpad values. The only way to initialize accumulators before loops or pass computed values between branches.

**WHEN TO USE:**
- Initialize empty arrays before FOR_EACH loops (`"grouped_results": "[]"`)
- Set context variables from user input (`"customer_id": "${id}"`)
- Clear ephemeral variables after processing
- Transform data between blocks (limited — use PYTHON_CODE for complex transforms)

**CRITICAL PATTERN — Loop accumulator init:**
```json
{"entriesToSet": [{"key": "all_results", "value": "[]"}], "nextBlock": "for_each_loop"}
```
Without this, the first iteration's spread operator (`...(state.all_results || [])`) works but is fragile.

**CRITICAL — `"[]"` stores a JSON string, not a Python list.** When a PYTHON_CODE block reads state initialized with `"value": "[]"`, it receives the string `"[]"`, not an empty list. Calling `.append()` or `.extend()` on it will crash with `AttributeError`. Always deserialize before use:

```python
# Safe accumulation pattern in PYTHON_CODE blocks
def process(trace):
    existing = state.get("all_discovered_events", "[]")
    if isinstance(existing, str):
        existing = json.loads(existing)
    existing.extend(new_items)
    state["all_discovered_events"] = existing
```

---

### 4. EMIT_OUTPUT — Message to User

**WHY:** Send a message to the user. Can be terminal (end the flow) or intermediate (then continue to next block).

**WHEN TO USE:**
- Rejection messages ("Please submit an amendment")
- Progress indicators ("Analyzing 12 articles...")
- Final results summary
- Error messages from routing fallbacks

**TEMPLATE SYNTAX:** Uses `{{state.key}}` and `{{scratchpad.key}}` for interpolation.

**DESIGN RULE:** Make rejection messages informative — include what was detected, not just "invalid input":
```
"This document was classified as {{scratchpad.parsed.document_type}}, not an AMENDMENT."
```

---

### 5. STANDARD_REACT — Agentic Loop with Tools

**WHY:** The core agentic block. An LLM reasons about a task, decides which tools to call, processes results, and iterates until done. This is where intelligence lives.

**WHEN TO USE:**
- Knowledge bank / vector store search (LLM formulates queries)
- Multi-tool orchestration (LLM decides tool order)
- Tasks requiring iterative refinement
- Any task where the LLM needs to "think" about which tools to use

**WHEN NOT TO USE:**
- You know exactly which tool to call with which arguments → MANUAL_TOOL_CALL
- You need exactly one tool call guaranteed → MANDATORY_TOOL_CALL
- No tools needed → LLM_REQUEST

**KEY FIELDS:**
- `tools[]` — Tools the LLM can use
- `maxLoopIterations` — Safety limit (default 25)
- `stateAware: true` — LLM can read/write agent state (powerful but expensive)
- `exitConditions` — Break the loop when state has specific keys
- `defaultNextBlock` — Where to go after the loop completes (**not** `nextBlock` — STANDARD_REACT is the only block type that uses `defaultNextBlock` instead of `nextBlock`)

**PATTERN — KB search with structured output:**
```json
{
  "type": "STANDARD_REACT",
  "tools": [{"toolRef": "kb_search_tool", "type": "EXPLICIT_TOOL", "forwardContext": true, "returnSources": true, "enableSetArgs": false, "setArgs": [], "outputHandling": "ADD_TO_MESSAGES", "treatAsJSON": false}],
  "systemPromptAfterHistory": "Search the KB for original article text...",
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "search_results",
  "streamOutput": false,
  "defaultNextBlock": "next_block_id"
}
```

**PATTERN — Plugin tool (e.g., web search, geocoder):**

Plugin-based agent tools (created via `dku agent-tool create`) require specific fields in the `tools` array. The `toolRef` is the tool ID returned by `dku agent-tool create`.

```json
{
  "type": "STANDARD_REACT",
  "tools": [
    {
      "toolRef": "<tool-id-from-agent-tool-create>",
      "type": "EXPLICIT_TOOL",
      "forwardContext": true,
      "returnSources": true,
      "enableSetArgs": false,
      "setArgs": [],
      "outputHandling": "ADD_TO_MESSAGES",
      "treatAsJSON": false
    }
  ],
  "systemPromptAfterHistory": "Use the web search tool to find current information about {{state.topic}}.",
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "search_results",
  "streamOutput": false,
  "defaultNextBlock": "analyze_results"
}
```

**PROMPT GUIDELINES:**
- Be specific about what to search for and what to return
- Include context from state/scratchpad via `{{state.key}}`
- Use `responseFormat: json` when saving to state
- Set `passConversationHistory: false` for stateless analysis blocks
- Set `streamOutput: false` when saving to state (streaming to state is wasted)

---

### 6. MANUAL_TOOL_CALL — Direct Tool Call (No LLM)

**WHY:** Call a tool directly with predetermined arguments. No LLM involved — fastest and cheapest way to invoke a tool. Arguments can reference state/scratchpad values.

**WHEN TO USE:**
- Dataset lookups with known filter criteria
- Fetching records by ID from state
- Any tool call where arguments are fully determined by prior blocks

**WHEN NOT TO USE:**
- Arguments need to be generated by an LLM → MANDATORY_TOOL_CALL
- Tool selection is uncertain → STANDARD_REACT

**PATTERN — Dataset lookup with state-derived filter:**
```json
{
  "type": "MANUAL_TOOL_CALL",
  "tool": {
    "toolRef": "dataset_lookup_tool",
    "setArgs": [
      {"key": "filter", "value": "{\"column\": \"regulation_id\", \"operator\": \"EQUALS\", \"value\": scratchpad[\"amendment\"][\"parent_id\"]}"}
    ]
  },
  "outputMode": "SAVE_TO_SCRATCHPAD",
  "outputScratchpadKey": "existing_records"
}
```

---

### 7. MANDATORY_TOOL_CALL — LLM-Generated Args, Guaranteed Execution

**WHY:** When you need a specific tool called but the LLM must generate the arguments. The tool call is guaranteed (unlike STANDARD_REACT where the LLM might skip it).

**WHEN TO USE:**
- Creating tickets/records where content must be LLM-generated
- Validation tools where the LLM must format the payload
- Write operations that must always execute

**PATTERN — Create support ticket:**
```json
{
  "type": "MANDATORY_TOOL_CALL",
  "tool": {"toolRef": "create_ticket"},
  "llmId": "openai:conn:gpt-4.1",
  "systemPrompt": "Create a ticket. Customer: {{state.customer_info}}. Issue: {{state.issue_summary}}"
}
```

---

### 8. PARALLEL — Concurrent Execution

**WHY:** Run multiple independent blocks simultaneously. The key performance optimization — instead of sequential A→B→C, run A+B+C together and combine results.

**WHEN TO USE:**
- Fetching data from multiple sources (KB search + dataset lookup)
- Independent analyses that don't depend on each other
- Any two branches that read from the same input but write to different outputs

**WHEN NOT TO USE:**
- Branches depend on each other's output (must be sequential)
- Only one thing to do (just use nextBlock)

**CRITICAL DESIGN RULE:** Blocks inside PARALLEL branches must write to **different** state/scratchpad keys. If two branches write to the same key, last-write-wins (race condition).

**PATTERN — Parallel data gathering:**
```json
{
  "type": "PARALLEL",
  "blockIds": ["kb_search_branch", "policy_analysis_branch"],
  "nextBlock": "merge_and_analyze"
}
```

The block after PARALLEL can read outputs from both branches since all state/scratchpad writes are visible.

---

### 9. FOR_EACH — Iterate Over a List

**WHY:** Process every item in a list with guaranteed coverage. Unlike an LLM analyzing a list in one shot (which may skip items), FOR_EACH executes the target block once per item.

**WHEN TO USE:**
- Per-article analysis in a regulation
- Per-customer processing in a batch
- Any array where each item needs independent analysis

**WHEN NOT TO USE:**
- Holistic analysis that needs to see all items at once → LLM_REQUEST
- Items depend on each other's results → STANDARD_REACT with stateAware

**KEY FIELDS:**
- `sourceExpression` — CEL expression returning a list: `scratchpad["amendment"]["article_changes"]`
- `blockIdToRepeat` — Block to execute per item
- `forEachInputKey` — Key in scratchpad for current item (default: `"forEachInput"`)

**Accessing the current item in child blocks:**
- In LLM prompts: use `{{forEachInputKey}}` directly — e.g., if `forEachInputKey: "article"`, use `{{article.field_name}}`
- For **string items** (not objects): use `{{current_event_type}}` directly — no field access, no `scratchpad.` prefix
- In PYTHON_CODE: use `scratchpad["article"]` or `scratchpad["forEachInput"]`

**Rule:** The `forEachInputKey` value is placed directly in scratchpad AND is accessible directly in LLM prompt templates without the `scratchpad.` prefix. `{{article.article_ref}}` works; `{{scratchpad.article.article_ref}}` does NOT.

**ACCUMULATION PATTERN (Critical):**

For Each doesn't automatically collect results. You need a PYTHON_CODE or SET_STATE_ENTRIES block at the end of each iteration to accumulate:

```python
# PYTHON_CODE block at end of loop body
def process(trace):
    current = json.loads(scratchpad["current_result"])
    state["all_results"].append(current)
```

Always initialize the accumulator BEFORE the FOR_EACH:
```
SET_STATE_ENTRIES (all_results: []) → FOR_EACH → [analysis block → accumulate block]
```

---

### 10. PYTHON_CODE — Custom Logic

**WHY:** Escape hatch for logic that can't be expressed with other block types. Parse JSON, transform data, accumulate loop results, make API calls, implement complex routing.

**WHEN TO USE:**
- Accumulating results in FOR_EACH loops (append to state array)
- Data transformation between blocks
- Custom validation logic
- Dynamic routing via `NextBlock("target_id")`
- External API calls

**ENTRY POINT:**
```python
from dataiku.llm.python.blocks_graph import NextBlock
import json

def process(trace):
    # Read from state/scratchpad (available as globals)
    raw = scratchpad.get("current_article", "{}")
    try:
        article = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        article = {"status": "ERROR", "issue": "Parse failed"}

    state["all_results"].append(article)

    # Optional: yield text to stream to user
    yield "Processed article"

    # Required for routing: yield NextBlock to specify where to go next
    yield NextBlock("next_block_id")
```

**CRITICAL — `nextBlock` field does NOT persist for PYTHON_CODE blocks.** Unlike other block types, setting `nextBlock` in the JSON definition of a PYTHON_CODE block has no effect. The only way to control routing is by yielding `NextBlock("target_id")` from the `process()` function. You must also declare `validNextBlocksFromCode: ["target_id"]` in the block definition so DSS validates the target:

```json
{
  "type": "PYTHON_CODE",
  "id": "my_python_block",
  "validNextBlocksFromCode": ["next_block_id"],
  "code": "..."
}
```

**DESIGN RULE:** Always wrap `json.loads()` in try/except — LLM outputs are not guaranteed valid JSON even with `strict: true`.

---

### 11. REFLECTION — Multi-Perspective Analysis

**WHY:** Generate multiple independent analyses then synthesize them, or iteratively critique and refine output. Produces higher quality results than a single LLM pass.

**WHEN TO USE:**
- Complex analysis requiring multiple viewpoints
- Self-critique loops for quality improvement
- Consensus-building across perspectives

**MODES:**
- `SYNTHESIZE` — Run N parallel analyses, then synthesize into one result
- `CRITIQUE` — Generate → critique → refine loop (up to N iterations)

---

### 12. DELEGATE_TO_OTHER_AGENT — Agent Handoff

**WHY:** Route to a specialist agent for a sub-task. The delegated agent runs independently and returns its result.

**WHEN TO USE:**
- Different parts of the workflow need different tools/LLMs
- Reusable sub-agents (e.g., a "summarizer" agent used by multiple SVAs)
- Separating concerns across agent boundaries

**KEY FIELD:** `agentRef` — the target agent's ID (must be in the same project).

---

### 13. GENERATE_ARTIFACT — Document Generation

**WHY:** Create a downloadable DOCX or PDF from a Jinja template. The final deliverable in many compliance/audit workflows.

**WHEN TO USE:**
- Compliance reports, impact assessments
- Generated documents from analyzed data
- Any workflow that ends with a formatted deliverable

**TEMPLATE SYNTAX (Jinja):**
```
# Report: {{ scratchpad.amendment.amendment_id }}

{% for gap in state.all_results %}
| {{ gap.article_ref }} | {{ gap.status }} | {{ gap.issue }} |
{% endfor %}

Remediation items: {{ state.all_results | selectattr('status', 'ne', 'ALIGNED') | list | length }}
```

**DESIGN RULE:** All data the template references must be in state/scratchpad BEFORE this block runs. Build the template last — design the data pipeline first.

---

### DSS 14.5+ Additional Block Types

The following block types were added in DSS 14.5+:

**14. CUSTOM** — Plugin-defined blocks. Executes a `BlockHandler` subclass from an installed plugin. Use when you need behavior that no built-in block provides. See `references/visual-agent-blocks.md` for the full plugin development guide.

**15. CONTEXT_COMPRESSION** — Compresses conversation context to reduce token count in long conversations. Place before a CORE_LOOP to keep context within token budgets.

**16. SET_SCRATCHPAD_ENTRIES** — Like SET_STATE_ENTRIES but targets the temporary scratchpad instead of persistent state. Use for intermediate values scoped to the current execution branch.

**17. EDIT_LAST_USER_MESSAGE** — Rewrites or augments the last user message before LLM processing. Use for prompt injection, context augmentation, or query rewriting.

**Aliases:** `CORE_LOOP` = `STANDARD_REACT` (DSS 14.5+ name). `GENERATE_OUTPUT` = `EMIT_OUTPUT` (DSS 14.5+ name). Both old and new names are accepted.

---

## Common Graph Patterns

### Pattern A: Parse → Route → Branch

The most common SVA pattern. Extract structured data, route based on type.

```
LLM_REQUEST (parse) → ROUTING
  ├─ Type A → [processing blocks] → EMIT_OUTPUT
  ├─ Type B → [different blocks] → EMIT_OUTPUT
  └─ Default → EMIT_OUTPUT (rejection)
```

### Pattern B: Parallel Data Gathering → Analysis

Fetch data from multiple sources concurrently, then analyze the combined results.

```
MANUAL_TOOL_CALL (fetch context) → PARALLEL
  ├─ STANDARD_REACT (KB search)
  └─ SET_STATE_ENTRIES → FOR_EACH → [per-item analysis]
→ LLM_REQUEST (cross-reference analysis) → EMIT_OUTPUT
```

### Pattern C: For Each with Accumulation

Process each item and collect results into a single array.

```
SET_STATE_ENTRIES (init: all_results=[]) → FOR_EACH (items)
  └─ STANDARD_REACT (analyze item) → PYTHON_CODE (accumulate)
→ LLM_REQUEST (summarize all_results)
```

### Pattern D: Full Pipeline (Regulatory Impact Example)

```
LLM_REQUEST (parse regulation)
  → ROUTING (AMENDMENT?)
    ├─ No → EMIT_OUTPUT (reject)
    └─ Yes → MANUAL_TOOL_CALL (fetch existing tests)
      → PARALLEL
        ├─ STANDARD_REACT (KB: find original articles)
        └─ SET_STATE_ENTRIES → FOR_EACH (articles)
            └─ STANDARD_REACT (policy KB search) → PYTHON_CODE (accumulate)
      → LLM_REQUEST (test gap analysis)
      → MANUAL_TOOL_CALL (validate findings)
      → GENERATE_ARTIFACT (PDF report)
      → LLM_REQUEST (summarize for user)
```

---

## State Management

### Storage Decision

| Store in State | Store in Scratchpad |
|----------------|-------------------|
| Accumulated results (arrays built across iterations) | Parsed input from first LLM call |
| Final analysis outputs | Loop iteration items |
| Anything the report template reads | Intermediate per-item results |
| Data that persists across conversation turns | Temporary data within a branch |

### Naming Convention

| Prefix | Scope | Example |
|--------|-------|---------|
| `all_*` | Accumulated across iterations | `all_results`, `all_gaps` |
| `current_*` | Current loop item (ephemeral) | `current_article`, `current_analysis` |
| `validated_*` | Post-HITL approved data | `validated_findings` |

---

## Common Pitfalls

### 1. Streaming to State
**Wrong:** `streamOutput: true` with `outputMode: "SAVE_TO_STATE"` — streaming is wasted since output goes to state, not the user.
**Fix:** `streamOutput: false` when saving to state/scratchpad. Only stream when `outputMode: "ADD_TO_MESSAGES"`.

### 2. Lost State in Loop Accumulation
**Wrong:** `state["all_results"] = state["current_results"]` — overwrites previous iterations.
**Fix:** Use PYTHON_CODE with `.append()` or spread operators in SET_STATE_ENTRIES.

### 3. Duplicate Block IDs
**Wrong:** Two blocks with the same `id` — DSS may pick the wrong one.
**Fix:** Every block ID must be unique. Use descriptive snake_case names.

### 4. PARALLEL Branches Writing Same Key
**Wrong:** Two parallel branches both write to `state["result"]`.
**Fix:** Each branch writes to a unique key. Merge after PARALLEL completes.

### 5. Missing Error Handling in PYTHON_CODE
**Wrong:** `json.loads(scratchpad["value"])` without try/except.
**Fix:** Always handle parse errors with a fallback value.

### 6. passConversationHistory on Analysis Blocks
**Wrong:** `passConversationHistory: true` on blocks that only need state/scratchpad data.
**Fix:** Set to `false` for pure analysis blocks — faster, cheaper, and avoids context pollution.

### 7. No Fallback on Routing
**Wrong:** ROUTING block with clauses but no `defaultNextBlockIfNoClauseMatch`.
**Fix:** Always set a default — at minimum an EMIT_OUTPUT with a clear error message.

### 8. PYTHON_CODE nextBlock in JSON is ignored
**Wrong:** Setting `"nextBlock": "target"` in the PYTHON_CODE block definition and expecting it to route there.
**Fix:** Yield `NextBlock("target")` from `process()`, and declare `"validNextBlocksFromCode": ["target"]` in the block JSON.

### 9. STANDARD_REACT uses `defaultNextBlock`, not `nextBlock`
**Wrong:** Setting `"nextBlock": "next_block"` on a STANDARD_REACT block — it has no effect.
**Fix:** Use `"defaultNextBlock": "next_block"`. This is the only block type that uses `defaultNextBlock` instead of `nextBlock`.

### 10. SET_STATE_ENTRIES `"[]"` is a string in PYTHON_CODE
**Wrong:** `state["results"].extend(items)` — crashes if `results` was initialized as `"[]"` (a JSON string).
**Fix:** Always deserialize: `existing = json.loads(state["results"]) if isinstance(state["results"], str) else state["results"]`.

### 11. connect fails for PYTHON_CODE blocks
**Wrong:** Using `dku agent-block connect` to wire PYTHON_CODE blocks — `nextBlock` is ignored by DSS for this type.
**Fix:** The CLI rejects `connect` for PYTHON_CODE with a prescriptive error. Use `validNextBlocksFromCode` in the block JSON and `yield NextBlock()` from `process()`. Push via `set-graph`. Note: `connect` works correctly for STANDARD_REACT (automatically sets `defaultNextBlock`).

---

## Scaling Guidance

| Items in Loop | Expected | Recommendation |
|---------------|----------|----------------|
| 1–50 | Fast | Standard pattern |
| 50–200 | Noticeable latency | Monitor runtime |
| 200–500 | Slow, possible timeouts | Batch into sub-arrays |
| 500+ | Risk of failure | Split into multiple agents |

**State size:** Keep under 1MB total. Don't store raw document text — extract only structured fields.

---

## CLI Workflow

### Recommended: get-graph → patch JSON → set-graph

**This is the reliable pattern for complex graphs.** `dku agent-block connect` does not support `PYTHON_CODE` blocks (exits with an error). For `STANDARD_REACT`, `connect` works correctly (sets `defaultNextBlock`). For non-trivial graphs, use the patch-and-push workflow:

```bash
# 1. Create agent and add blocks
dku agent create "My SVA" -P PROJ
dku agent-block add AGENT_ID --set-start -b @parse_block.json -P PROJ && \
dku agent-block add AGENT_ID -b @routing_block.json -P PROJ && \
dku agent-block add AGENT_ID -b @react_block.json -P PROJ

# 2. Export the graph
dku agent-block get-graph AGENT_ID -P PROJ -o json > /tmp/graph.json

# 3. Patch block connections (nextBlock, defaultNextBlock, validNextBlocksFromCode)
python3 -c "
import json
g = json.load(open('/tmp/graph.json'))
blocks = {b['id']: b for b in g['blocks']}
blocks['parse']['nextBlock'] = 'routing'
blocks['react']['defaultNextBlock'] = 'emit_output'
json.dump(g, open('/tmp/graph.json', 'w'))
"

# 4. Push patched graph
dku agent-block set-graph AGENT_ID -d @/tmp/graph.json -P PROJ

# 5. Verify
dku agent-block list AGENT_ID -P PROJ
```

### Convenience: connect (simple cases only)

`dku agent-block connect` works reliably for `LLM_REQUEST` and `ROUTING` blocks. Use it only for simple wiring, and always verify the graph afterwards:

```bash
dku agent-block connect AGENT_ID --from parse --to routing -P PROJ
# Verify the connection persisted:
dku agent-block get-graph AGENT_ID -P PROJ -o json | jq '.blocks[] | {id, nextBlock, defaultNextBlock}'
```

See block type definitions in the sections above for the complete schema of each block type.
