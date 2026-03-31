# Visual Agent Block Plugin Development

> Reference for building **custom** visual agent (SVA) blocks as plugin components. Blocks execute deterministically in the agent's graph flow — always at specified points, regardless of LLM choice.

> **Using built-in blocks?** See `references/structured-agents.md` for the design guide (when/why for all 13 block types) and `docs/block-graph-api.md` for JSON schemas. This doc is for building NEW block types as plugin components.

**Example plugin:** `dss-plugin-aws-bedrock-agentcore-resources` (memory + code interpreter + browser)

**Requires:** DSS 14.4+

---

## When to Use Blocks vs Tools vs Agent Connectors

A single plugin can offer the same capability through multiple component types:

| Component | Execution | Use When | Folder |
|-----------|-----------|----------|--------|
| **Agent Tool** | Non-deterministic — LLM decides when to call | Open-ended reasoning, ad-hoc use | `python-agent-tools/` |
| **Visual Agent Block** | Deterministic — always runs at graph position | Pre/post-turn orchestration, guaranteed execution, routing | `python-structured-agent-blocks/` |
| **Python Agent Connector** | Runtime delegation — wraps external agent as LLM | Calling external agent runtimes as if they were an LLM | `python-agents/` |

**Dual-mode pattern:** Offer both a tool AND a block for the same capability when it makes sense both ways:
- **Block**: Always inject context before generation (guaranteed, pre-turn)
- **Tool**: Let the LLM decide to fetch context (on-demand, in-loop)

---

## Block Component Structure

```
my-plugin/
├── python-structured-agent-blocks/
│   └── my-block/
│       ├── block.json              # Block metadata, params, UI config
│       └── dynamic_choices.py      # Dynamic SELECT population (optional)
├── python-lib/my_plugin/
│   └── blocks.py                   # BlockHandler subclasses
└── resource/
    └── dynamic_choices.py          # Shared dynamic choices helper (optional)
```

### block.json Reference

```json
{
    "meta": {
        "label": "My Custom Block",
        "description": "Injects external context into the agent graph flow",
        "icon": "icon-puzzle-piece"
    },
    "pyClazzName": "my_plugin.blocks.MyCustomBlock",
    "params": [
        {
            "name": "resource_id",
            "type": "SELECT",
            "label": "Resource",
            "mandatory": true,
            "getChoicesFromPython": true,
            "triggerParameters": ["connection", "region"]
        },
        {
            "name": "connection",
            "type": "CONNECTION",
            "label": "Connection",
            "mandatory": true,
            "connectionTypes": ["S3"]
        },
        {
            "name": "mode",
            "type": "SELECT",
            "label": "Mode",
            "selectChoices": [
                {"value": "inject", "label": "Inject into conversation"},
                {"value": "store", "label": "Store from conversation"}
            ],
            "defaultValue": "inject"
        },
        {
            "name": "show_advanced",
            "type": "BOOLEAN",
            "label": "Show Advanced Settings",
            "defaultValue": false
        },
        {
            "name": "max_chars",
            "type": "INT",
            "label": "Max Context Characters",
            "defaultValue": 4000,
            "visibilityCondition": "model.show_advanced == true"
        }
    ]
}
```

**Key fields:**

| Field | Description |
|-------|-------------|
| `pyClazzName` | Fully-qualified class name in python-lib (e.g. `"my_plugin.blocks.MyCustomBlock"`) |
| `params` | Same parameter types as tools/recipes (STRING, SELECT, BOOLEAN, etc.) |
| `visibilityCondition` | CEL expression for conditional param display |
| `triggerParameters` | Re-evaluate dynamic choices when these params change |
| `getChoicesFromPython` | Populate SELECT from `dynamic_choices.py` |

---

## BlockHandler Implementation

```python
# python-lib/my_plugin/blocks.py
from dataiku.llm.python.blocks_graph import BlockHandler, NextBlock

class MyContextBlock(BlockHandler):
    """Inject external context into the agent's conversation."""

    def __init__(self, turn, sequence_context, block_config):
        super().__init__(turn, sequence_context, block_config)
        self.config = self.block_config.get("config") or {}
        self.max_chars = int(self.config.get("max_chars", 4000))
        if not self.config.get("resource_id"):
            raise ValueError("Please configure resource_id on block %s" % self.block_config["id"])

    def process_stream(self, trace):
        """
        Execute block logic. Generator — yield NextBlock at the end to advance the graph.

        Key attributes:
            self.block_config          — full block definition dict
            self.block_config["id"]    — this block's ID
            self.block_config.get("defaultNextBlock") — the next block ID configured in the graph
            self.config                — dict of parameter values from the UI (set in __init__)
            self.turn.initial_messages — list of [{role, content}] at start of turn (read-only)
            self.turn.context_get("conversationId") — current conversation ID
            self.sequence_context.generated_messages — list to append injected messages into
        """
        result_text = self._fetch_context(self.config["resource_id"], self.config)

        if len(result_text) > self.max_chars:
            result_text = result_text[:self.max_chars] + "\n[truncated]"

        # Inject as system message — LLM sees this in the next generation step
        self.sequence_context.generated_messages.append({
            "role": "system",
            "content": f"[Injected Context]\n{result_text}"
        })

        yield NextBlock(id=self.block_config.get("defaultNextBlock"))

    def _fetch_context(self, resource_id, config):
        # Your logic here — API calls, DB queries, etc.
        ...
```

**Critical points:**

1. **Blocks run in the agent's code environment**, not the plugin's. If your block imports `boto3` or any library, the agent's code env must have it installed.

2. **`process_stream()` is a generator** — you must `yield NextBlock(id=self.block_config.get("defaultNextBlock"))` at the end to advance the graph. Not returning it — yielding it.

3. **`self.sequence_context.generated_messages`** is where you inject content. Appended messages (role `"system"` or `"user"`) are visible to the LLM in the next generation step.

4. **`self.turn.initial_messages`** is the conversation history at the start of the turn (read-only). Use it to read what the user said.

5. **Use `__init__` for config validation** — raising `ValueError` there gives a clear error before the block runs rather than mid-graph.

---

## Routing Between Blocks

Blocks can route to different downstream blocks based on logic:

```python
class RoutingBlock(BlockHandler):
    def __init__(self, turn, sequence_context, block_config):
        super().__init__(turn, sequence_context, block_config)
        self.config = self.block_config.get("config") or {}

    def process_stream(self, trace):
        last_msg = self.turn.initial_messages[-1]["content"] if self.turn.initial_messages else ""

        # Route based on content — yield NextBlock with explicit target ID
        if "code" in last_msg.lower():
            yield NextBlock(id="code-interpreter-block")
        elif "search" in last_msg.lower():
            yield NextBlock(id="search-block")
        else:
            yield NextBlock(id=self.block_config.get("defaultNextBlock"))
```

For simple routing, prefer DSS's built-in **Expression Block** (CEL-based) over custom Python blocks. Use Python routing blocks only when you need complex logic that CEL can't express.

---

## Dynamic Choices for Block Parameters

### Block-Level dynamic_choices.py

```python
# python-structured-agent-blocks/my-block/dynamic_choices.py

def do(payload, config, plugin_config, inputs):
    """
    Called by DSS to populate SELECT dropdowns.

    Args:
        payload: {"parameterName": "resource_id", "formData": {...}}
        config: Current block parameter values
        plugin_config: Plugin-level parameters
        inputs: Flow inputs

    Returns:
        {"choices": [{"value": "id", "label": "Display Name"}, ...]}
    """
    parameter_name = payload.get("parameterName")

    if parameter_name == "resource_id":
        return _list_resources(config, plugin_config)

    return {"choices": []}
```

### Error Handling in Dynamic Choices

**Dynamic choices must NEVER raise exceptions.** An unhandled error breaks the entire parameter UI.

```python
def _list_resources(config, plugin_config):
    try:
        client = build_client(config, plugin_config)
        items = client.list_resources(maxResults=500)
        return {
            "choices": [
                {"value": item["id"], "label": f"{item['id']} [{item['status']}]"}
                for item in items
            ]
        }
    except Exception as e:
        # Graceful fallback — show current value + error
        current = config.get("resource_id", "")
        choices = []
        if current:
            choices.append({"value": current, "label": f"{current} (current value)"})
        choices.append({"value": "", "label": f"Error: {str(e)[:100]}"})
        return {"choices": choices}
```

### Shared Choices Between Tools and Blocks

If both tools and blocks need the same dropdown data, put the helper in `resource/dynamic_choices.py` and import it from both `python-structured-agent-blocks/*/dynamic_choices.py` and `python-agent-tools/*/` code.

---

## Python Agent Connector

For wrapping external agent runtimes (Bedrock, LangGraph, custom) as DSS LLM connections.

### Structure

```
python-agents/
└── my-runtime/
    ├── agent.json              # Connector metadata + params
    └── agent.py                # BaseLLM subclass
```

### agent.json

```json
{
    "meta": {
        "label": "External Runtime Agent",
        "description": "Wraps an external agent runtime as a DSS LLM connection",
        "icon": "icon-cloud"
    },
    "params": [
        {
            "name": "endpoint",
            "type": "STRING",
            "label": "Runtime Endpoint",
            "mandatory": true
        },
        {
            "name": "connection",
            "type": "CONNECTION",
            "label": "Connection for Auth",
            "mandatory": true
        }
    ]
}
```

### BaseLLM Implementation

```python
from dataiku.llm import BaseLLM

class ExternalRuntimeAgent(BaseLLM):

    def set_config(self, config, plugin_config):
        """Initialize from params."""
        self.endpoint = config["endpoint"]
        self.client = self._build_client(config, plugin_config)

    def process(self, messages, settings=None):
        """
        Synchronous processing — called when this agent is invoked.

        Args:
            messages: List of {role, content} messages
            settings: Optional LLM settings

        Returns:
            str: Response text
        """
        user_msg = self._extract_last_user_message(messages)

        response = self.client.invoke(payload={"prompt": user_msg})

        # Multi-strategy response extraction (APIs vary)
        return self._extract_text(response)

    def _extract_last_user_message(self, messages):
        """Find last user message from DSS message list."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    def _extract_text(self, response):
        """Try multiple response formats — external APIs are inconsistent."""
        # Strategy 1: Streaming event format
        if "events" in response:
            return "".join(e.get("text", "") for e in response["events"])
        # Strategy 2: Direct text
        if "text" in response:
            return response["text"]
        # Strategy 3: Message array
        if "content" in response:
            return " ".join(c.get("text", "") for c in response["content"] if "text" in c)
        # Fallback
        return str(response)
```

**Key difference from agent tools:** Agent connectors implement `BaseLLM`, not `BaseAgentTool`. They appear as LLM connections in DSS, not as tools an agent can call.

---

## Recommended Graph Architecture

When combining blocks and tools in a visual agent:

```
┌─────────────────────────────────────────┐
│  Before Turn                             │
│  ┌────────────────────────┐             │
│  │ Context Inject Block   │ ← Always    │
│  └───────────┬────────────┘   runs      │
│              ▼                           │
│  ┌────────────────────────┐             │
│  │ Routing Block / CEL    │ ← Branch    │
│  └──┬─────────┬──────────┬┘             │
│     ▼         ▼          ▼              │
│  ┌──────┐ ┌───────┐ ┌───────┐          │
│  │ Core │ │ Core  │ │ Code  │ ← Loops  │
│  │ Loop │ │ Loop  │ │ Block │   + tools │
│  │ +tool│ │ +tool │ │       │           │
│  └──┬───┘ └──┬────┘ └──┬────┘          │
│     └────────┴──────────┘               │
│              ▼                           │
│  After Turn                              │
│  ┌────────────────────────┐             │
│  │ Context Store Block    │ ← Persist   │
│  └────────────────────────┘             │
└─────────────────────────────────────────┘
```

**Principle:** Blocks for guaranteed orchestration (inject context, store results, route). Tools for LLM-driven reasoning within core loops (search, browse, execute).

---

## Error Handling Patterns

### Retryable External API Errors

```python
def call_with_retry(func, *args, max_retries=3, base_delay=0.5):
    """Exponential backoff for external API calls."""
    for attempt in range(max_retries + 1):
        try:
            return func(*args)
        except Exception as e:
            error_name = type(e).__name__
            if error_name not in RETRYABLE_ERRORS or attempt == max_retries:
                raise
            time.sleep(base_delay * (2 ** attempt))
```

### Stream Collection with Budget

For blocks that consume event streams from external services:

```python
def collect_stream(response_stream, max_chars=4000):
    """Safely collect streaming response with character budget."""
    text_parts = []
    errors = []
    total_chars = 0

    for event in response_stream:
        try:
            content = event.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    remaining = max_chars - total_chars
                    if remaining <= 0:
                        break
                    if len(text) > remaining:
                        text_parts.append(text[:remaining] + "\n[truncated]")
                        total_chars = max_chars
                    else:
                        text_parts.append(text)
                        total_chars += len(text)
        except Exception as e:
            errors.append(str(e))

    return {"text": "\n".join(text_parts), "errors": errors}
```

---

## Example: AWS Bedrock AgentCore Plugin

The `dss-plugin-aws-bedrock-agentcore-resources` plugin is the reference implementation. It demonstrates platform-specific patterns on top of the generic block framework:

| Pattern | What It Does | Generic or AWS-Specific |
|---------|-------------|------------------------|
| BlockHandler subclass | Implements `process()` | **Generic** — all block plugins use this |
| Dynamic choices from API | Populates SELECTs from live AWS resources | **AWS-specific** — adapt for your service |
| Identity from `context.dkuOnBehalfOf` | Resolves who's running the agent | **Generic** — DSS provides this in Agent Hub |
| Namespace scoping (app vs user_global) | Isolates memory per-agent or per-user | **AWS AgentCore-specific** — memory store concept |
| S3 connection credential reuse | Gets AWS creds from DSS connection | **AWS-specific** — other clouds use different patterns |
| Dual-mode (block + tool) | Same capability both deterministic and LLM-driven | **Generic** — good pattern for any external service |
| Retryable error handling | Exponential backoff on throttling | **Generic** — adapt error types for your API |

---

## Checklist: Visual Agent Block Plugin

### block.json
- [ ] `pyClazzName` is fully-qualified class name (e.g. `"my_plugin.blocks.MyBlock"`)
- [ ] Dynamic SELECTs have `getChoicesFromPython: true`
- [ ] `triggerParameters` set for dependent dropdowns
- [ ] `visibilityCondition` for advanced settings

### BlockHandler
- [ ] Imports from `dataiku.llm.python.blocks_graph` (`BlockHandler`, `NextBlock`)
- [ ] `__init__(self, turn, sequence_context, block_config)` validates required config (raises `ValueError` early)
- [ ] `process_stream(self, trace)` is a generator that yields `NextBlock(id=...)`
- [ ] Reads params from `self.block_config.get("config") or {}` (set in `__init__`)
- [ ] Injects messages via `self.sequence_context.generated_messages.append({"role": "system", ...})`
- [ ] Reads turn messages via `self.turn.initial_messages`

### Dynamic Choices
- [ ] NEVER raises exceptions (returns fallback choices with error in label)
- [ ] Shows current value as fallback on error
- [ ] Shared helper in `resource/dynamic_choices.py` if used by both tools and blocks

### Dual-Mode (if applicable)
- [ ] Deterministic operations → block (guaranteed execution)
- [ ] LLM-driven operations → tool (agent decides)
- [ ] Shared logic in `python-lib/` (DRY)

### Code Environment
- [ ] Blocks run in AGENT's code env, not plugin's — document required packages
- [ ] `installCorePackages: false` in plugin's desc.json
