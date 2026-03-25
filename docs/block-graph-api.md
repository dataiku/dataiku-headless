# Block Graph API — Undocumented DSS Agent Blocks Reference

> **Status:** Reverse-engineered from live DSS 13.x instances (March 2026). Not in official Dataiku docs or dataikuapi docstrings.

## How It Works

Visual agent blocks are NOT a separate agent type. They're part of `TOOLS_USING_AGENT` with a mode switch:

```
mode: "SIMPLE"        → Classic tool-using agent (LLM picks tools)
mode: "BLOCKS_GRAPH"  → Deterministic block graph (explicit control flow)
```

**There are no dedicated block/graph endpoints.** Everything flows through the standard agent settings:

```
GET  /projects/{key}/agents/{id}     → read block graph (inside settings JSON)
PUT  /projects/{key}/agents/{id}     → save block graph (full settings dict)
```

---

## API Pattern

```python
from dataikuapi import DSSClient

client = DSSClient(url, api_key=key)
proj = client.get_project("MY_PROJECT")

# Create agent
agent = proj.create_agent("My Agent", type="TOOLS_USING_AGENT")

# Get raw settings
settings = agent.get_settings()
raw = settings.get_raw()
tuas = raw["versions"][0]["toolsUsingAgentSettings"]

# Switch to block graph mode
tuas["mode"] = "BLOCKS_GRAPH"
tuas["startingBlockId"] = "first_block_id"
tuas["blocks"] = [...]  # Block definitions

# Save
settings.save()
```

### Reading blocks from existing agent

```python
agent = proj.get_agent("AGENT_ID")
settings = agent.get_settings()
raw = settings.get_raw()
tuas = raw["versions"][0]["toolsUsingAgentSettings"]

mode = tuas["mode"]            # "SIMPLE" or "BLOCKS_GRAPH"
blocks = tuas["blocks"]        # List of block dicts
start = tuas.get("startingBlockId")  # Entry point block ID
```

### Modifying blocks

```python
# Add a block
tuas["blocks"].append({...})

# Remove a block
tuas["blocks"] = [b for b in tuas["blocks"] if b["id"] != "block_to_remove"]

# Rewire connections (change nextBlock on any block)
for b in tuas["blocks"]:
    if b["id"] == "source_block":
        b["nextBlock"] = "new_target_block"

# Save ALL changes
settings.save()
```

---

## Top-Level Settings (toolsUsingAgentSettings)

| Field | Type | Description |
|-------|------|-------------|
| `mode` | `"SIMPLE"` \| `"BLOCKS_GRAPH"` | Agent mode. Must be `BLOCKS_GRAPH` for blocks. |
| `blocks` | `list[BlockDef]` | Flat list of all block definitions |
| `startingBlockId` | `string` | ID of the entry-point block |
| `nextTurnBehaviour` | `"STARTING_BLOCK"` \| `"SMART"` | Multi-turn: restart from start vs. LLM decides |
| `nextTurnSmartModeLLMId` | `string` | LLM for SMART mode next-turn routing |
| `debugMode` | `bool` | Enable debug traces |
| `shortTermMemoryEnabled` | `bool` | Persist state across conversation turns |
| `newLineAfterBlockOutput` | `bool` | Formatting option |
| `tools` | `list` | Top-level tools (usually empty in BLOCKS_GRAPH, tools go inside blocks) |
| `codeEnvSelection` | `dict` | Code env for PYTHON_CODE blocks |

---

## Block Connection Model

Blocks are a **flat list** — no nested graph structure, no separate edges array. Connections are expressed via:

1. **`nextBlock`** — Most blocks have a `nextBlock` field pointing to the next block's `id`
2. **`ROUTING` clauses** — Each clause has a `nextBlock` for conditional branching
3. **`PARALLEL.blockIds`** — Lists block IDs to run in parallel
4. **`FOR_EACH.blockIdToRepeat`** — The block to execute per iteration
5. **`exitConditions[].nextBlock`** — Where to go when a STANDARD_REACT loop exits
6. **`defaultNextBlock`** — Fallback next block on STANDARD_REACT

A block with no `nextBlock` is a **terminal block** (ends execution).

---

## All 13 Block Types

### 1. SET_STATE_ENTRIES

Initialize or update state variables. Often the first block.

```json
{
  "type": "SET_STATE_ENTRIES",
  "id": "init_state",
  "entriesToSet": [
    {"secret": false, "key": "customer_id", "value": "${id}"},
    {"secret": false, "key": "results", "value": "[]"}
  ],
  "nextBlock": "next_block_id"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `entriesToSet` | `list[{secret, key, value}]` | State entries to set. Values can use `${var}` interpolation or CEL. |
| `nextBlock` | `string?` | Next block ID |

---

### 2. LLM_REQUEST

Call an LLM (non-agentic, no tools). Used for classification, extraction, summarization.

```json
{
  "type": "LLM_REQUEST",
  "id": "classify_intent",
  "llmId": "openai:SE_OpenAI_v2:gpt-4.1-mini",
  "passConversationHistory": true,
  "systemPromptAfterHistory": "Classify intent. Return JSON: {\"intent\": \"...\"}",
  "completionSettings": {
    "stopSequences": [],
    "responseFormat": {"type": "json", "strict": true, "compatible": true},
    "outputTrajectory": true
  },
  "streamOutput": false,
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "classification",
  "nextBlock": "route_block"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `llmId` | `string` | LLM connection ID (format: `provider:connection:model`) |
| `passConversationHistory` | `bool` | Include conversation history in prompt |
| `systemPromptAfterHistory` | `string` | System prompt (supports `{{state.key}}` templating) |
| `completionSettings` | `dict` | LLM settings: responseFormat, stopSequences, reasoningEffort |
| `streamOutput` | `bool` | Stream output to user |
| `outputMode` | `"SAVE_TO_STATE"` \| `"ADD_TO_MESSAGES"` | Where output goes |
| `outputStateKey` | `string` | State key (when outputMode=SAVE_TO_STATE) |
| `nextBlock` | `string?` | Next block ID |

---

### 3. ROUTING

Conditional branching using CEL expressions or LLM-based decisions.

```json
{
  "type": "ROUTING",
  "id": "route_intent",
  "routingMode": "CLAUSES",
  "clausesBasedDecisions": [
    {
      "clause": {
        "type": "EXPRESSION",
        "expression": {"language": "CEL", "expression": "state[\"intent\"] == \"billing\""}
      },
      "nextBlock": "billing_handler"
    },
    {
      "clause": {
        "type": "LLM_BASED",
        "passConversationHistory": true,
        "systemPromptAfterHistory": "Has the user provided an order ID?"
      },
      "nextBlock": "order_lookup"
    }
  ],
  "defaultNextBlockIfNoClauseMatch": "fallback_block",
  "llmId": "openai:...:gpt-4.1",
  "resultDispatch": [],
  "validNextBlocksFromExpression": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `routingMode` | `"CLAUSES"` | Routing strategy |
| `clausesBasedDecisions` | `list` | Ordered list of clause→nextBlock pairs |
| `clause.type` | `"EXPRESSION"` \| `"LLM_BASED"` | CEL expression or LLM decision |
| `clause.expression` | `{language: "CEL", expression: string}` | For EXPRESSION type |
| `clause.passConversationHistory` | `bool` | For LLM_BASED type |
| `clause.systemPromptAfterHistory` | `string` | For LLM_BASED type |
| `defaultNextBlockIfNoClauseMatch` | `string` | Fallback block ID |
| `llmId` | `string?` | Required when using LLM_BASED clauses |

---

### 4. EMIT_OUTPUT

Output a message to the user. Can be terminal or chain to next block.

```json
{
  "type": "EMIT_OUTPUT",
  "id": "greet_user",
  "templateType": "CEL_EXPANSION",
  "template": "Hello! Your classification: {{state.classification.intent}}",
  "addToMessages": true,
  "nextBlock": "optional_next_block"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `templateType` | `"CEL_EXPANSION"` | Template engine |
| `template` | `string?` | Message template with `{{state.key}}` interpolation. Omit for empty. |
| `addToMessages` | `bool` | Add output to conversation history |
| `nextBlock` | `string?` | Next block (omit for terminal) |

---

### 5. STANDARD_REACT

ReAct loop — LLM reasons and calls tools iteratively. The core agentic block.

```json
{
  "type": "STANDARD_REACT",
  "id": "faq_agent",
  "tools": [
    {
      "type": "EXPLICIT_TOOL",
      "toolRef": "PROJ.toolId",
      "forwardContext": true,
      "returnArtifacts": true,
      "returnSources": true,
      "enableSetArgs": false,
      "setArgs": [],
      "outputHandling": "ADD_TO_MESSAGES",
      "treatAsJSON": false
    }
  ],
  "maxLoopIterations": 25,
  "maxParallelToolExecutions": 2,
  "stateAware": true,
  "scratchpadAware": false,
  "exitConditions": [
    {
      "type": "STATE_HAS_KEYS",
      "stateKeys": ["result"],
      "nextBlock": "process_result"
    }
  ],
  "defaultNextBlock": "after_react",
  "llmId": "openai:SE_OpenAI_v2:gpt-4.1",
  "passConversationHistory": true,
  "systemPromptAfterHistory": "You are a helpful agent. Use tools to answer.",
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "streamOutput": true,
  "outputMode": "ADD_TO_MESSAGES"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tools` | `list[ToolRef]` | Tools available to the LLM |
| `tools[].toolRef` | `string` | Tool ID (local or `PROJECT.toolId` for foreign) |
| `tools[].enableSetArgs` | `bool` | Pre-set tool arguments |
| `tools[].setArgs` | `list[{key, value}]` | Preset args when enableSetArgs=true |
| `maxLoopIterations` | `int` | Max ReAct iterations |
| `maxParallelToolExecutions` | `int` | Concurrent tool calls |
| `stateAware` | `bool` | LLM can read/write state |
| `scratchpadAware` | `bool` | LLM can use scratchpad |
| `exitConditions` | `list` | Conditions that break the loop |
| `exitConditions[].type` | `"STATE_HAS_KEYS"` | Exit when state has these keys |
| `exitConditions[].stateKeys` | `list[string]` | Keys to check |
| `exitConditions[].nextBlock` | `string` | Where to go on exit |
| `defaultNextBlock` | `string?` | Block after loop completes normally |
| `llmId` | `string` | LLM for reasoning |
| `systemPromptAfterHistory` | `string` | System prompt (supports `{{state.key}}`) |
| `streamOutput` | `bool` | Stream to user |
| `outputMode` | `"ADD_TO_MESSAGES"` \| `"SAVE_TO_STATE"` | Where output goes |
| `outputStateKey` | `string?` | State key (when outputMode=SAVE_TO_STATE) |

---

### 6. MANUAL_TOOL_CALL

Call a tool directly with preset arguments — no LLM involved.

```json
{
  "type": "MANUAL_TOOL_CALL",
  "id": "fetch_customer",
  "tool": {
    "type": "EXPLICIT_TOOL",
    "toolRef": "kk98dZA",
    "setArgs": [
      {
        "secret": false,
        "key": "filter",
        "value": "{\"column\": \"customer_id\", \"operator\": \"EQUALS\", \"value\": state[\"customer_id\"]}"
      }
    ]
  },
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "customer_info",
  "nextBlock": "process_customer"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tool` | `ToolRef` | Tool reference with preset args |
| `tool.setArgs` | `list[{secret, key, value}]` | Tool arguments (values can reference state) |
| `outputMode` | `"SAVE_TO_STATE"` \| `"ADD_TO_MESSAGES"` | Where output goes |
| `outputStateKey` | `string?` | State key for output |
| `nextBlock` | `string?` | Next block |

---

### 7. MANDATORY_TOOL_CALL

LLM must call a specific tool — it generates the arguments, but the tool call is guaranteed.

```json
{
  "type": "MANDATORY_TOOL_CALL",
  "id": "create_ticket",
  "tool": {
    "type": "EXPLICIT_TOOL",
    "toolRef": "eD8A9ae",
    "forwardContext": true,
    "returnArtifacts": true,
    "returnSources": true,
    "enableSetArgs": false,
    "setArgs": [],
    "outputHandling": "ADD_TO_MESSAGES",
    "treatAsJSON": false
  },
  "llmId": "openai:SE_OpenAI_v2:gpt-4.1",
  "systemPrompt": "Create a support ticket. Customer: {{state.customer_info}}",
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "stateAware": false,
  "outputMode": "ADD_TO_MESSAGES",
  "nextBlock": "after_ticket"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tool` | `ToolRef` | The tool that MUST be called |
| `llmId` | `string` | LLM that generates the arguments |
| `systemPrompt` | `string` | Prompt for the LLM (supports `{{state.key}}`) |
| `stateAware` | `bool` | LLM can read state |
| `outputMode` | `string` | Where output goes |
| `nextBlock` | `string?` | Next block |

---

### 8. PARALLEL

Run multiple blocks concurrently. Waits for all to finish before proceeding.

```json
{
  "type": "PARALLEL",
  "id": "gather_data",
  "blockIds": ["fetch_customer", "fetch_transactions", "search_policy"],
  "maxThreads": 32,
  "generatedOutputStorageLocation": "STATE",
  "targetOutputKey": "parallel_results",
  "generatedStateKeys": [],
  "generatedScratchpadKeys": [],
  "nextBlock": "process_results"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `blockIds` | `list[string]` | Block IDs to run in parallel |
| `maxThreads` | `int` | Max concurrent threads |
| `generatedOutputStorageLocation` | `"STATE"` \| `"SCRATCHPAD"` | Where parallel outputs go |
| `targetOutputKey` | `string` | Key for combined output |
| `nextBlock` | `string` | Block after all parallel blocks finish |

---

### 9. FOR_EACH

Iterate over a list, executing a block for each item.

```json
{
  "type": "FOR_EACH",
  "id": "process_articles",
  "sourceExpression": "state[\"articles\"]",
  "blockIdToRepeat": "analyze_article",
  "forEachInputKey": "article",
  "generatedOutputStorageLocation": "STATE",
  "targetOutputKey": "article_results",
  "generatedStateKeys": [],
  "generatedScratchpadKeys": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sourceExpression` | `string` | CEL expression returning a list |
| `blockIdToRepeat` | `string` | Block to execute per item |
| `forEachInputKey` | `string?` | Key in scratchpad for current item (default: `forEachInput`) |
| `generatedOutputStorageLocation` | `"STATE"` \| `"SCRATCHPAD"` | Where iteration outputs go |
| `targetOutputKey` | `string` | Key for collected results |

Access current item in child blocks via: `scratchpad["forEachInput"]` (or custom key).

---

### 10. PYTHON_CODE

Execute arbitrary Python code.

```json
{
  "type": "PYTHON_CODE",
  "id": "custom_logic",
  "code": "from dataiku.llm.python.blocks_graph import NextBlock\n\ndef process(trace):\n    yield \"Processing complete\"\n    # yield NextBlock(\"target_block\") for dynamic routing",
  "functionName": "process",
  "validNextBlocksFromCode": ["block_a", "block_b"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | `string` | Python source code |
| `functionName` | `string` | Entry point function (usually `process`) |
| `validNextBlocksFromCode` | `list[string]` | Block IDs that code can route to via `NextBlock()` |

The `process(trace)` generator can yield:
- `str` — text output streamed to user
- `dict` — structured output chunk
- `NextBlock("block_id")` — dynamic routing

---

### 11. REFLECTION

Multi-perspective synthesis or self-critique loop.

```json
{
  "type": "REFLECTION",
  "id": "synthesize",
  "mode": "SYNTHESIZE",
  "llmId": "openai:SE_OpenAI_v2:gpt-4.1",
  "streamOutput": true,
  "outputMode": "ADD_TO_MESSAGES",
  "critiqueCompletionSettings": {"stopSequences": [], "outputTrajectory": true},
  "critiqueMaxIterations": 3,
  "failOnMaxIterations": true,
  "synthesizeCompletionSettings": {"stopSequences": [], "outputTrajectory": true},
  "synthesizeIterations": 3,
  "maxThreads": 32
}
```

| Field | Type | Description |
|-------|------|-------------|
| `mode` | `"SYNTHESIZE"` \| `"CRITIQUE"` | Reflection strategy |
| `synthesizeIterations` | `int` | Number of synthesis passes |
| `critiqueMaxIterations` | `int` | Max critique rounds |
| `failOnMaxIterations` | `bool` | Error if max iterations hit |

---

### 12. DELEGATE_TO_OTHER_AGENT

Hand off to another agent in the project.

```json
{
  "type": "DELEGATE_TO_OTHER_AGENT",
  "id": "call_specialist",
  "agentRef": "OTHER_AGENT_ID",
  "streamOutput": true,
  "outputMode": "ADD_TO_MESSAGES",
  "outputStateKey": "",
  "nextBlock": "after_delegation"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `agentRef` | `string` | Target agent ID (same project) |
| `streamOutput` | `bool` | Stream delegated agent output |
| `outputMode` | `string` | Where output goes |
| `nextBlock` | `string?` | Block after delegation returns |

---

### 13. GENERATE_ARTIFACT

Generate a document (DOCX, PDF) from a Jinja template.

```json
{
  "type": "GENERATE_ARTIFACT",
  "id": "create_report",
  "templateType": "DOCX_JINJA",
  "template": "# Report\n{{ state.summary }}",
  "managedFolderRef": "FOLDER_ID",
  "templateFilename": "template.docx",
  "outputFormat": "DOCX",
  "outputManagedFolderRef": "FOLDER_ID",
  "outputFilename": "report.pdf",
  "nextBlock": "notify_user",
  "description": "Generate compliance report"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `templateType` | `"DOCX_JINJA"` | Template format |
| `template` | `string` | Jinja template content |
| `managedFolderRef` | `string` | Source folder for template file |
| `templateFilename` | `string` | Template filename in folder |
| `outputFormat` | `"DOCX"` \| `"PDF"` | Output format |
| `outputManagedFolderRef` | `string` | Destination folder |
| `outputFilename` | `string` | Output filename |

---

## Tool Reference Format

Tools referenced in blocks use this structure:

```json
{
  "type": "EXPLICIT_TOOL",
  "toolRef": "toolId",
  "forwardContext": true,
  "returnArtifacts": true,
  "returnSources": true,
  "enableSetArgs": false,
  "setArgs": [],
  "outputHandling": "ADD_TO_MESSAGES",
  "treatAsJSON": false
}
```

- `toolRef`: Local tool ID or `PROJECT_KEY.toolId` for cross-project tools
- `enableSetArgs`: When true, `setArgs` provides preset argument values
- `setArgs[].value`: Can reference state: `state["key"]` or `scratchpad["key"]`

---

## State & Scratchpad

- **State** (`state["key"]`): Persistent across the conversation turn. Shared between blocks.
- **Scratchpad** (`scratchpad["key"]`): Temporary, scoped to current execution branch. Used by FOR_EACH for iteration items.

Access in templates: `{{state.key}}` or `{{scratchpad.forEachInput}}`
Access in CEL: `state["key"]`, `scratchpad["key"]`

---

## Common Graph Patterns

### Intent Classification + Routing
```
SET_STATE_ENTRIES → LLM_REQUEST (classify) → ROUTING → [branch blocks]
```

### Parallel Data Gathering
```
PARALLEL [fetch_a, fetch_b, fetch_c] → ROUTING (based on results) → handler
```

### ReAct with Exit Conditions
```
STANDARD_REACT (with exitConditions: STATE_HAS_KEYS) → next_block
```

### For-Each Processing
```
FOR_EACH (over state["items"], repeat: process_item) → synthesize
```

### Multi-Agent Delegation
```
ROUTING → DELEGATE_TO_OTHER_AGENT (specialist_a) | DELEGATE_TO_OTHER_AGENT (specialist_b)
```

---

## CLI Commands (Implemented)

The `dku agent-block` command group provides full block graph management:

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
- `add` auto-switches to BLOCKS_GRAPH mode if agent is in SIMPLE mode
- Full command reference: `skills/dku-cli/references/commands.md`

---

## Verified Against

| Project | Agent | Blocks | Block Types Used |
|---------|-------|--------|-----------------|
| CUSTOMERSUPPORTFEATURETTE | TbqX3xCD | 14 | SET_STATE, LLM_REQUEST, ROUTING, EMIT_OUTPUT, STANDARD_REACT, REFLECTION, PARALLEL, MANUAL_TOOL_CALL, MANDATORY_TOOL_CALL |
| CUSTOMERSUPPORTFEATURETTEV2HITL | TbqX3xCD | 17 | (extended version with HITL) |
| GARTNERDEMO2026 | A2STEjD2 | 12 | LLM_REQUEST, ROUTING, EMIT_OUTPUT, STANDARD_REACT, PYTHON_CODE |
| REGULATORYCHANGEIMPACTANALYST | u7y9lP18 | 13 | All 13 types |
| REGULATORYCHANGEIMPACTANALYST | l7qm5P3m | 3 | MANUAL_TOOL_CALL, EMIT_OUTPUT, DELEGATE_TO_OTHER_AGENT |
| MGPRODUCTRECOMENDATIONENGINE | d28ScEGI | 5 | SET_STATE, LLM_REQUEST, ROUTING, EMIT_OUTPUT, STANDARD_REACT |
