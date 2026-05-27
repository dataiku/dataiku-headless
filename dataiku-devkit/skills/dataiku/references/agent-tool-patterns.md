# Advanced Agent Tool & Plugin Patterns

> Dataiku-specific patterns for building agent tools, subprocess integrations, and multi-agent plugins. Assumes you already know Python, subprocess, Flask, etc.

**Source codebases:** opencode-agent-tool, dataiku-mcp-gateway, dss-plugin-agent-hub, `dss-plugin-semantic-models-lab` (internal Dataiku — not public on GitHub)

---

## Agent Tool Lifecycle

Every tool follows three methods. The DSS-specific gotchas are in the comments:

```python
from dataiku.llm.agent_tools import BaseAgentTool

class MyTool(BaseAgentTool):

    def set_config(self, config, plugin_config):
        """Called once at init. Plugin params (PASSWORD for API keys) in plugin_config."""
        self.api_key = plugin_config.get("api_key")  # Plugin-level param
        self.timeout = int(config.get("timeout", 120))  # Tool-level param

    def get_descriptor(self, tool):
        """MCP-style tool definition for the LLM."""
        return {
            "description": "Be specific — LLM uses this to decide when to call",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        }

    def invoke(self, input, trace):
        # CRITICAL: DSS wraps args under "input" key
        args = input.get("input", {})
        query = args.get("query", "")

        # CRITICAL: Use dict assignment, NOT set_attribute (that's OpenTelemetry)
        trace.attributes["query"] = query

        result = self._do_work(query)

        # CRITICAL: Return {"output": str} — must be a string
        return {"output": result}
```

### tool.json — Plugin-Level vs Tool-Level Params

- **Plugin params** (in `plugin.json`): Shared across all tools. Use for API keys (`PASSWORD` type), base URLs.
- **Tool params** (in `tool.json`): Per-tool instance. Use for model selection, timeouts, behavior toggles.

---

## Subprocess Tool Pattern

For tools that delegate to external CLIs. The DSS-specific safety flags are non-negotiable:

```python
result = subprocess.run(
    cmd,
    stdin=subprocess.DEVNULL,           # MUST: DSS tool server blocks on stdin
    capture_output=True,
    text=True,
    timeout=self.timeout_seconds,       # MUST: prevents infinite hangs
    env={
        **os.environ,
        "CI": "true",                   # Skip interactive prompts
        "TERM": "dumb",                 # Disable ANSI escape codes
        "NO_COLOR": "1",               # Additional color suppression
        "API_KEY": self.api_key,       # Secrets via env, not CLI args
    },
    cwd=self.working_dir,
)
```

**DSS runtime context:**
- Tools run as `dssuser_dataiku` (not `dataiku`). HOME is `/data/home/dssuser_dataiku`
- Tool server processes persist between Quick Test invocations — stale processes can block new ones
- Without `stdin=subprocess.DEVNULL`, the tool server hangs and DSS must be restarted

---

## MCP Gateway Pattern

For exposing Dataiku agent tools to external MCP clients (Claude Desktop, ChatGPT):

```python
def handle_tools_call(params, msg_id, server_name):
    """Bridge MCP tools/call to Dataiku agent tool execution."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    project = dataiku.api_client().get_project(project_key)
    tool = project.get_agent_tool(tool_name)
    output = tool.run({"question": arguments.get("query", "")})

    response_text = output.get("output", {}).get("response", json.dumps(output))
    return {
        "jsonrpc": "2.0", "id": msg_id,
        "result": {"content": [{"type": "text", "text": response_text}]},
    }
```

---

## Multi-Agent Streaming (Agent-Hub Pattern)

The core agentic loop in agent-hub uses explicit imperative flow (no LangGraph) for full control over HITL:

**Key DSS integration points:**
- LLM invocation via `llm.new_completion().with_message().execute_streamed()`
- Tool calls parsed from streamed chunks, executed via `tool.run(arguments)`
- HITL: `TOOL_VALIDATION_REQUESTS` event pauses execution, stores `memory_fragment` for resume
- 24 event types (`EventKind` enum) normalized via `normalise_stream_event()` before emitting to frontend
- Artifact size checking before emit (preview if oversized) to prevent UI hangs
- Sources extracted from `DSSLLMStreamedCompletionFooter.additionalInformation.sources`

---

## Plugin Code Organization

Core logic in `python-lib/` must have **zero Dataiku imports** — this is the key DSS pattern for testability:

```
python-lib/my_plugin/
├── core/               # Zero Dataiku imports — trivially testable
│   ├── runner.py
│   └── validation.py
└── adapters/           # Dataiku integration wrappers
    └── datasets.py
```

Component files (`tool.py`, `backend.py`) are thin wrappers: config → core → output.

Tests in `tests/python/unit/` import from `python-lib/` directly — no DSS mocking needed for core logic.

---

## Code Environment

Use the canonical plugin code-environment policy in `code-environments.md`.

The `dataiku` runtime imports numpy/pandas/dateutil at module load — include them even if your plugin doesn't use them directly.

---

## Trace API

```python
def invoke(self, input, trace):
    trace.attributes["tool_version"] = "1.2.0"
    trace.attributes["query"] = args.get("query", "")[:200]
    start = time.time()
    try:
        result = self._execute(args)
        trace.attributes["success"] = True
        trace.attributes["duration_ms"] = int((time.time() - start) * 1000)
        return {"output": result}
    except Exception as e:
        trace.attributes["success"] = False
        trace.attributes["error_type"] = type(e).__name__
        raise
```

**Gotcha:** `trace.attributes[key] = value` (dict assignment) — NOT `trace.set_attribute()`. That's OpenTelemetry, not DSS.

---

## Agentic Tool Pattern (Internal Agent Loop)

For tools that run multi-step reasoning internally — not just a single request→response. The tool receives a question and orchestrates multiple LLM calls + internal tool executions before returning.

**Source:** `dss-plugin-semantic-models-lab` (Dataiku internal state-of-the-art — plugin not public; patterns below distilled from its code). For semantic model JSON schema, see `references/semantic-models.md`.

### Architecture

```
invoke(question)
  └─ run_agent(ctx)
       ├─ LangGraph StateGraph with internal tools
       │   ├─ list_entities → discover schema
       │   ├─ generate_sql → LLM → SQL
       │   ├─ execute_sql → run query
       │   ├─ resolve_values → fuzzy/semantic matching
       │   └─ get_glossary_terms → business context
       ├─ Agent loop (up to recursion_limit iterations)
       └─ Return aggregated result
```

### LangGraph Integration

DSS LLMs integrate with LangGraph via `DKUChatModel` (LangChain-compatible wrapper):

```python
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

# Internal tools use @tool decorator (NOT BaseAgentTool)
@tool
def generate_sql(question: str, entities: list[str], dialect: str) -> dict:
    """Generate SQL from natural language question."""
    # This runs INSIDE the agent loop, not as a DSS agent tool
    result = call_llm_for_sql(question, entities, dialect)
    return {"sql": result}

@tool
def execute_sql(sql: str, max_rows: int = 1000) -> dict:
    """Execute SQL and return results."""
    executor = dataiku.core.sql.SQLExecutor2(connection=connection_id)
    df = executor.query_to_df(sql)
    return {"columns": list(df.columns), "rows": df.head(max_rows).values.tolist()}

def build_agent_graph(ctx):
    """Build LangGraph state graph for the agent loop."""
    tools = [generate_sql, execute_sql, list_entities, resolve_values]

    # DKUChatModel wraps DSS LLM for LangChain compatibility
    from dataiku.langchain import DKUChatModel
    llm = DKUChatModel(ctx.llm_id).bind_tools(tools)

    graph = StateGraph(AgentState)
    graph.add_node("call_llm", make_call_model(llm))
    graph.add_node("tool_calls", ToolNode(tools))
    graph.add_conditional_edges("call_llm", should_continue, {"tools": "tool_calls", "end": END})
    graph.add_edge("tool_calls", "call_llm")
    graph.set_entry_point("call_llm")
    return graph.compile()
```

### RuntimeContext for State

Carry immutable state through the agent loop:

```python
@dataclass
class RuntimeContext:
    question: str
    spec: dict                          # Schema/model spec
    dialect: str                        # SQL dialect (postgres, snowflake, etc.)
    llm_id: str
    embedding_llm_id: Optional[str]
    semantic_model_id: str
    version_id: str
    trace: Any                          # DSS trace span
    dku_caller_ticket: Optional[str]    # End-user identity

    # Caches — prevent redundant API calls during agent loop
    entity_cache: dict = field(default_factory=dict)
    attribute_values_cache: dict = field(default_factory=dict)
    glossary_cache: Optional[list] = None
```

### The Outer Tool (DSS BaseAgentTool)

The DSS-facing tool is thin — it configures, then delegates to the agent loop:

```python
class SemanticModelQueryTool(BaseAgentTool):
    def set_config(self, config, plugin_config):
        # 1. Validate required params
        self.llm_id = config.get("llm_id")
        if not self.llm_id:
            raise ValueError("llm_id is required")

        # 2. Create service layer
        client = LocalSemanticModelClient(config.get("project_key"))
        self.service = get_semantic_models_service(client=client)

        # 3. Load global config
        load_tool_config(config)

        # 4. Pre-initialize search indices (non-blocking)
        self._initialize_search_indices()

    def invoke(self, input, trace):
        question = input.get("input", {}).get("question")

        # Wrap invocation with logging context
        with log_context(request_id=str(uuid.uuid4()), user=resolve_tool_user(),
                         method="TOOL", path="/agent-tools/semantic-model-query"):

            result = run_semantic_model_query(
                service=self.service,
                question=question,
                llm_id=self.llm_id,
                trace=trace,
                dku_caller_ticket=resolve_dku_caller_ticket(self.config, input),
            )
            return format_tool_response(question, result)

    def load_sample_query(self, tool):
        """Provide sample input for Quick Test UI."""
        return {"input": {"question": "What are the top 10 records?"}}
```

### DSS Trace Integration with LangGraph

Bridge LangChain callbacks to DSS tracing:

```python
from dataiku.langchain import LangchainToDKUTracer

def run_agent_core(ctx):
    graph = build_agent_graph(ctx)

    # Create DSS trace subspan for the agent loop
    agent_span = ctx.trace.create_child_span("agent_loop")

    # Bridge LangChain callbacks → DSS trace
    callbacks = [LangchainToDKUTracer(trace=agent_span)]

    state = AgentState(
        messages=[SystemMessage(content=system_prompt), HumanMessage(content=ctx.question)],
        spec=ctx.spec, dialect=ctx.dialect,
    )

    result = graph.invoke(state, config={"recursion_limit": 100, "callbacks": callbacks})
    return extract_results(result)
```

### Key Dependencies for Agentic Tools

In `requirements.txt`:
```
langgraph>=0.2.0
langchain-core>=0.3.0
dataiku-api-client>=14.0.0
```

---

## Dual-Mode Tool Pattern

Two tools sharing the same agent loop but with different setup paths — one for ease-of-use, one for power users:

| Mode | Tool | Setup | Use Case |
|------|------|-------|----------|
| **Lite** | `semantic-model-lite` | Auto-generates spec from dataset schema | Quick ad-hoc queries |
| **Full** | `semantic-model-query` | Uses explicit pre-built semantic model | Production queries with curated models |

Both tools call `run_agent()` with the same LangGraph graph — the difference is how `spec` is built:

```python
# Lite: auto-generate spec from dataset
spec = build_spec_from_dataset(dataset_id)

# Full: load spec from semantic model version
version = service.get_active_version(model_id)
spec = build_spec_from_version(version)
```

---

## End-User SQL Execution Security

For tools that execute SQL, delegate identity to respect row-level security:

```python
# tool.json param
{
    "name": "enduser_sql_execution",
    "type": "SELECT",
    "label": "SQL Execution Identity",
    "selectChoices": [
        {"value": "tool_user", "label": "Tool user (default)"},
        {"value": "enduser", "label": "End user (requires caller ticket)"},
        {"value": "enduser_available", "label": "End user if available, else tool user"}
    ],
    "defaultValue": "tool_user"
}
```

```python
# In tool.py
def resolve_dku_caller_ticket(config, input):
    """Resolve end-user identity from tool invocation context."""
    mode = config.get("enduser_sql_execution", "tool_user")
    if mode == "tool_user":
        return None

    ticket = input.get("dkuCallerTicket")
    if mode == "enduser" and not ticket:
        raise ValueError("enduser_sql_execution=enduser requires dkuCallerTicket")

    return ticket  # None for "enduser_available" when ticket absent

def resolve_tool_user():
    """Get the identity of the tool's service user."""
    try:
        return dataiku.api_client().get_auth_info()["authIdentifier"]
    except Exception:
        return "unknown"
```

---

## load_sample_query() Method

Undocumented `BaseAgentTool` method that provides default input for the Quick Test UI:

```python
class MyTool(BaseAgentTool):
    def load_sample_query(self, tool):
        """Return sample input pre-filled in Quick Test."""
        return {"input": {"question": "What are the top 10 customers by revenue?"}}
```

Without this, Quick Test shows an empty input field. With it, users can immediately test the tool.

---

## Checklist

### Agent Tool
- [ ] `invoke()` reads args from `input.get("input", {})` (not root)
- [ ] `trace.attributes[key] = value` for key events (not `set_attribute`)
- [ ] Returns `{"output": str}` (string, not dict)
- [ ] Config validated in `set_config()` (fail early)
- [ ] `load_sample_query()` provides Quick Test defaults

### Agentic Tool (Internal Agent Loop)
- [ ] Internal tools use `@tool` decorator (NOT `BaseAgentTool`)
- [ ] `DKUChatModel` for LangChain-compatible DSS LLM access
- [ ] `RuntimeContext` dataclass carries state through agent loop
- [ ] Caches prevent redundant API calls during iterations
- [ ] `recursion_limit` configured (default 100)
- [ ] `LangchainToDKUTracer` bridges callbacks → DSS trace
- [ ] `langgraph` + `langchain-core` in `requirements.txt`

### Subprocess Tool
- [ ] `stdin=subprocess.DEVNULL`
- [ ] `CI=true`, `TERM=dumb`, `NO_COLOR=1` in env
- [ ] `timeout` parameter set
- [ ] Secrets via env vars (not CLI args, not logged)

### End-User Security
- [ ] `enduser_sql_execution` param if tool runs SQL
- [ ] `resolve_dku_caller_ticket()` for identity delegation
- [ ] `resolve_tool_user()` for audit logging

### Code Environment
- [ ] Code environment follows `code-environments.md`
- [ ] Explicit pandas/numpy/dateutil/requests
- [ ] Python version matches target DSS instance
