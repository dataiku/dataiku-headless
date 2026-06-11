# Agent Blocks, Graph & Tool Schemas

Durable JSON shapes for structured-agent blocks, the block graph, visual-agent
configuration, and LLM tool definitions. Workflow lives in
`playbooks/genai-agents.md`; exact CLI flags come from `--help`.

**Version paths** (CLI auto-detects): DSS 14.5+ blocks live in
`versions[0].structuredAgentSettings`; DSS 13.x in `toolsUsingAgentSettings`.
Aliases: `CORE_LOOP`=`STANDARD_REACT`, `GENERATE_OUTPUT`=`EMIT_OUTPUT`. Always
`dku --format json agent get ID` a working agent to confirm the path on your instance.

---

## Structured-agent graph shape

Blocks are a **flat list** wired by ID fields (no nested graph). Two storage scopes:
`state["k"]` persists across the turn / all blocks; `scratchpad["k"]` is temporary,
scoped to the current branch.

```json
{
  "structuredAgentSettings": {
    "startingBlockId": "parse",
    "nextTurnBehaviour": "STARTING_BLOCK",   // | "SMART" | "LAST_BLOCK"
    "blocks": [ /* flat list of block defs below */ ]
  }
}
```

**Wiring fields (the trap):**

| Block type | Next-block field |
|---|---|
| Most blocks | `nextBlock: "id"` |
| STANDARD_REACT / CORE_LOOP | `defaultNextBlock: "id"` (NOT `nextBlock`) |
| ROUTING | per-clause `nextBlock` + `defaultNextBlockIfNoClauseMatch` |
| PYTHON_CODE | neither persists — `yield NextBlock("id")` + `validNextBlocksFromCode: ["id"]` |
| PARALLEL | `blockIds: [...]` branches, then `nextBlock` after merge |
| FOR_EACH | `blockIdToRepeat` + `nextBlock` after loop |

**CORE_LOOP/STANDARD_REACT silent null response:** A `CORE_LOOP` with no
`defaultNextBlock` (or a `defaultNextBlock` targetting a non-existent/terminal
block) returns `response:null` with `success:true` — no error. Always set
`defaultNextBlock` to an `EMIT_OUTPUT` block, and verify the graph with
`dku --format json agent-block get-graph AGENT_ID | jq '.blocks[]|{id,nextBlock,defaultNextBlock}'`
after every `set-graph`.

> **Don't chain a tool-calling CORE_LOOP *after* a PARALLEL gather** (verified
> live DSS 14.6): the agent returns `response:null` with `success:true` (silent
> failure). Put each tool-loop **inside** a PARALLEL branch; the block after
> PARALLEL should only merge/format the gathered state.

---

## Block types (19 in DSS 14.5+)

| Block | Purpose | Key fields |
|---|---|---|
| `LLM_REQUEST` | single-shot LLM (classify/extract/summarize, no tools) | `llmId`, `outputMode`, `responseFormat`, `passConversationHistory` |
| `STANDARD_REACT`/`CORE_LOOP` | agentic loop, LLM picks tools | `llmId`, `tools[]`, `maxLoopIterations`(25), `stateAware`, `exitConditions`, `defaultNextBlock` |
| `MANUAL_TOOL_CALL` | call a tool with preset args, no LLM | `tool.toolRef`, `tool.setArgs[]`, `outputMode`, `outputScratchpadKey` |
| `MANDATORY_TOOL_CALL` | LLM generates args, call guaranteed | `tool.toolRef`, `llmId`, `systemPrompt` |
| `ROUTING` | conditional branch | `clausesBasedDecisions[]`, `routingMode`, `defaultNextBlockIfNoClauseMatch` |
| `PARALLEL` | run branches concurrently | `blockIds[]`, `nextBlock` |
| `FOR_EACH` | iterate a list, guaranteed coverage | `sourceExpression`, `blockIdToRepeat`, `forEachInputKey` |
| `PYTHON_CODE` | custom logic / dynamic routing | `code`, `validNextBlocksFromCode[]` |
| `SET_STATE_ENTRIES` | init/update state | `entriesToSet[{key,value}]`, `nextBlock` |
| `SET_SCRATCHPAD_ENTRIES` | init/update scratchpad | same, targets scratchpad |
| `EMIT_OUTPUT`/`GENERATE_OUTPUT` | message to user (terminal or intermediate) | template `{{state.k}}`/`{{scratchpad.k}}` |
| `GENERATE_ARTIFACT` | DOCX/PDF from Jinja template | Jinja over `state`/`scratchpad` |
| `REFLECTION` | multi-perspective | mode `SYNTHESIZE` \| `CRITIQUE` |
| `DELEGATE_TO_OTHER_AGENT` | hand off sub-task | `agentRef` (same project) |
| `CONTEXT_COMPRESSION` | shrink long context | place before a loop |
| `EDIT_LAST_USER_MESSAGE` | rewrite user msg pre-LLM | — |
| `CUSTOM` | plugin block (`BlockHandler`) | `pyClazzName` via plugin |

**Output modes** (LLM/REACT blocks): `SAVE_TO_STATE` (+`outputKey`/`outputStateKey`),
`SAVE_TO_SCRATCHPAD` (+`outputScratchpadKey`), `ADD_TO_MESSAGES`. `streamOutput: true`
only with `ADD_TO_MESSAGES`. `responseFormat: {"type":"json","strict":true}` forces schema.

> **Canonical — Anthropic rejects `responseFormat: json` through the Mesh**
> (verified live): the block silently SKIPs or errors. Use an OpenAI (or other
> JSON-mode-capable) model for any JSON-output or judge/eval block; keep
> Anthropic for free-text blocks.

### STANDARD_REACT block + tool entry

```json
{
  "type": "STANDARD_REACT", "id": "kb_search", "llmId": "openai:conn:gpt-4.1",
  "tools": [{
    "toolRef": "<tool-id-from-agent-tool-create>", "type": "EXPLICIT_TOOL",
    "forwardContext": true, "returnSources": true,
    "enableSetArgs": false, "setArgs": [],
    "outputHandling": "ADD_TO_MESSAGES", "treatAsJSON": false
  }],
  "systemPromptAfterHistory": "Search the KB for {{state.topic}}...",
  "outputMode": "SAVE_TO_STATE", "outputStateKey": "search_results",
  "streamOutput": false, "passConversationHistory": true,
  "defaultNextBlock": "analyze"
}
```

### ROUTING clauses

```json
{
  "type": "ROUTING", "id": "route",
  "routingMode": "CLAUSES",
  "clausesBasedDecisions": [
    {
      "clause": {
        "type": "EXPRESSION",
        "expression": {"language": "CEL", "expression": "state[\"intent\"] == \"billing\""}
      },
      "nextBlock": "billing"
    },
    {
      "clause": {
        "type": "LLM_BASED",
        "llmId": "openai:conn:gpt-4.1",
        "passConversationHistory": true,
        "systemPromptAfterHistory": "Is this a billing question?"
      },
      "nextBlock": "ask_more"
    }
  ],
  "defaultNextBlockIfNoClauseMatch": "reject"
}
```
CEL: `state["x"]["y"] == "Z"`, `state["score"] > 0.7`, `state["items"].size() > 0`.
Prefer `EXPRESSION` (deterministic, free) over `LLM_BASED`.

**Micro-CEL operators are Python-style:** `and`/`or`/`not` and `True`/`False` —
NOT `&&`/`||`/`!`/`true`/`false` (those crash at runtime). An empty ROUTING
clause expression also crashes at runtime — every clause needs a real expression.

### MANUAL_TOOL_CALL with state-derived args

```json
{
  "type": "MANUAL_TOOL_CALL", "id": "lookup",
  "tool": {"toolRef": "dataset_lookup", "setArgs": [
    {"key": "filter", "value": "{\"column\":\"id\",\"operator\":\"EQUALS\",\"value\":scratchpad[\"amend\"][\"parent_id\"]}"}
  ]},
  "outputMode": "SAVE_TO_SCRATCHPAD", "outputScratchpadKey": "records"
}
```

### PYTHON_CODE entry point

```python
from dataiku.llm.python.blocks_graph import NextBlock
import json

def process(trace):
    raw = scratchpad.get("current", "{}")
    item = json.loads(raw) if isinstance(raw, str) else raw   # always guard
    existing = state.get("all_results", "[]")
    if isinstance(existing, str): existing = json.loads(existing)   # "[]" is a string
    existing.append(item)
    state["all_results"] = existing
    yield "Processed"                 # optional stream to user
    yield NextBlock("next_block")     # required for routing
```

### FOR_EACH item access

- LLM prompt template: `{{forEachInputKey}}` directly, e.g. `{{article.field}}` — NO
  `scratchpad.` prefix. String items: `{{current_event_type}}` (no field access).
- PYTHON_CODE: `scratchpad["article"]` or `scratchpad["forEachInput"]`.

### SET_STATE_ENTRIES (accumulator init)

```json
{"type": "SET_STATE_ENTRIES", "id": "init",
 "entriesToSet": [{"key": "all_results", "value": "[]"}], "nextBlock": "loop"}
```
CEL literals only: `"''"`, `"0"`, `"[]"`. Empty `""` crashes ("unexpected EOF").

---

## Visual agent (TOOLS_USING_AGENT)

Read config:

```python
raw = agent.get_settings().get_raw()
active = next(v for v in raw["versions"] if v["versionId"] == raw["activeVersion"])
s = active["toolsUsingAgentSettings"]   # .systemPromptAppend, .llmId, .tools
# RAG_LLM type instead: active["ragllmSettings"]["contextMessage"]
```

New version (always; never edit active in place): deep-copy active, fresh `versionId`,
refresh `versionTag`/`creationTag`, append to `raw["versions"]`, `save()`, then
`project.get_saved_model(agent_id).set_active_version(new_vid)` — setting
`activeVersion` alone does NOT persist. CLI does all this via `--new-version --activate`.

---

## Agent-tool built-in types

`dku agent-tool types` lists the catalog (no `-P`). No server endpoint
enumerates these — the CLI catalog is the source of truth. Live-verified DSS 14.6:

| Type | Key params | Dedicated flag |
|---|---|---|
| `DatasetRowLookup` | `datasetRef`, `retrievalMode`, `maxRecords` | `--dataset` |
| `DatasetRowAppend` | `datasetRef` | `--dataset` |
| `VectorStoreSearch` | `knowledgeBankRef` | `--knowledge-bank` |
| `LLMMeshLLMQuery` | `llmId` | `--llm` |
| `ClassicalPredictionModelPredict` | `smRef` (saved-model ID) | `--saved-model` |
| `ApiEndpoint` | endpoint config via `--params` | — |
| `ImageGeneration` | `nbImagesToGenerate`, `imageHandlingMode` | — |
| `GenerateArtifact` | `templateType`, `outputFormat`, `variables` | — |

Doc-listed tools NOT above (SQL Q&A, Google Search, Jira, Salesforce,
ServiceNow, MCP, Snowflake Cortex, Databricks Genie, …) are **plugin tools** —
install the plugin, then use `Custom_agent_tool_<plugin>_<tool>`.

`set-definition --params` is a **shallow merge**, and DSS does **not** validate
params keys against the tool type — typos / unknown keys are silently accepted
("it saved" ≠ "it works"). Confirm keys against the table above, then verify
with `dku agent-tool run`.

### Model Predict tool (ML → agent)

Saved-model field is `smRef` — NOT `savedModelId`/`modelId` (wrong keys persist
silently, fail at run time with "Model to use is not specified"). Run input is
`{"record": {…}}` at the **root** (SDK adds the envelope); output carries
`prediction` + `probas`. `dku ml redeploy` keeps the saved-model ID stable, so
`smRef` survives retrains — prefer `redeploy` over `deploy` once wired.

---

## LLM tool definitions

### get_descriptor — schema the LLM sees

```python
def get_descriptor(self, tool):
    return {
        "description": "Specific — the LLM uses this to decide when to call.",
        "inputSchema": {
            "$id": "https://dataiku.com/agents/tools/my-tool/input",
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "priority": {"type": "string", "enum": ["low", "high"]},
                "to": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["query"]
        }
    }
```
JSON Schema; `enum`, nested objects, arrays all supported.

### BaseAgentTool lifecycle (plugin: `python-agent-tools/<tool>/` = `tool.json`+`tool.py`)

```python
from dataiku.llm.agent_tools import BaseAgentTool

class MyTool(BaseAgentTool):
    def set_config(self, config, plugin_config):   # once at init; validate, fail early
        self.api_key = plugin_config.get("api_key")   # PASSWORD-type plugin param
        self.timeout = int(config.get("timeout", 120)) # tool param
    def get_descriptor(self, tool): ...
    def invoke(self, input, trace):
        args = input.get("input", {})              # args nested under "input"
        trace.attributes["query"] = args["query"]  # dict assign, NOT set_attribute()
        return {"output": "result string"}         # must be {"output": str}
    def load_sample_query(self, tool):             # optional Quick Test prefill
        return {"input": {"query": "example"}}
```

Multimodal (DSS 14+): image inputs arrive base64 under args; return
`{"output": str, "images": [{"data": b64, "mimeType": "image/png"}]}`.

**SQL-tool identity delegation (row-level security):** `tool.json` SELECT param
`enduser_sql_execution` ∈ `{tool_user`(default)`, enduser, enduser_available}`.
The end-user ticket arrives as `input["dkuCallerTicket"]` — **top-level** in the
invoke `input` dict, NOT under nested `input["input"]` args. `tool_user` → ticket
`None` (service acct, bypasses RLS); `enduser` → raise if absent;
`enduser_available` → ticket if present else fall back. Pass it to `SQLExecutor2`
so the query runs as the end user. (Checklist: `references/plugins.md`.)

### tool.json params

```json
{
  "meta": {"label": "DB Query", "description": "...", "icon": "icon-database"},
  "params": [
    {"name": "connection_id", "type": "STRING", "mandatory": true},
    {"name": "max_rows", "type": "INT", "defaultValue": 100},
    {"name": "allow_writes", "type": "BOOLEAN", "defaultValue": false}
  ]
}
```
Plugin params (`plugin.json`) shared across tools — use for API keys (`PASSWORD`).
Tool params (`tool.json`) per-instance. `SELECT` choices via `getChoicesFromPython` +
`dynamic_choices.py do(payload, config, plugin_config, inputs)` returning
`{"choices":[{"value","label"}]}` (must never raise — return fallback on error).

### Subprocess tools (non-negotiable flags)

```python
subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
    timeout=t, env={**os.environ, "CI":"true", "TERM":"dumb", "NO_COLOR":"1", "API_KEY":secret})
```
Without `stdin=DEVNULL` the tool server hangs (runs as `dssuser_dataiku`).

---

## Component-type chooser

| Component | Folder | Execution | Base class |
|---|---|---|---|
| Agent Tool | `python-agent-tools/` | LLM decides when | `BaseAgentTool` |
| Visual block | `python-structured-agent-blocks/` | always at graph position | `BlockHandler` |
| Agent connector (external runtime as LLM) | `python-agents/` | wraps as LLM connection | `BaseLLM` |
| Guardrail | `python-guardrails/` | intercept completion | `BaseGuardrail` (see `mlops.md`) |

### Custom BlockHandler

```python
from dataiku.llm.python.blocks_graph import BlockHandler, NextBlock

class MyBlock(BlockHandler):
    def __init__(self, turn, sequence_context, block_config):
        super().__init__(turn, sequence_context, block_config)
        self.config = self.block_config.get("config") or {}   # UI params
        if not self.config.get("resource_id"):
            raise ValueError("configure resource_id")          # validate early
    def process_stream(self, trace):                           # generator
        self.sequence_context.generated_messages.append(
            {"role": "system", "content": "[Injected]\n..."})  # LLM sees next step
        # read history: self.turn.initial_messages (read-only)
        yield NextBlock(id=self.block_config.get("defaultNextBlock"))
```
Blocks run in the **agent's** code env, not the plugin's — agent env must have block deps.
`block.json`: `pyClazzName` fully-qualified; `visibilityCondition` CEL; `triggerParameters`
re-evaluate dependent dropdowns.
