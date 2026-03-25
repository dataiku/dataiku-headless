# Advanced Agent Tool & Plugin Patterns

> Dataiku-specific patterns for building agent tools, subprocess integrations, and multi-agent plugins. Assumes you already know Python, subprocess, Flask, etc.

**Source codebases:** opencode-agent-tool, dataiku-mcp-gateway, dss-plugin-agent-hub

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

```json
{
    "acceptedPythonInterpreters": ["PYTHON311", "PYTHON312", "PYTHON313"],
    "installCorePackages": false,
    "installJupyterSupport": false
}
```

**NEVER `installCorePackages: true` on Python 3.11+** — installs `pandas==0.23.4` which fails. Always explicit deps:

```
pandas>=2.0,<3
numpy>=1.22,<3
python-dateutil>=2.8,<3
requests>=2.28,<3
```

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

## Checklist

### Agent Tool
- [ ] `invoke()` reads args from `input.get("input", {})` (not root)
- [ ] `trace.attributes[key] = value` for key events (not `set_attribute`)
- [ ] Returns `{"output": str}` (string, not dict)
- [ ] Config validated in `set_config()` (fail early)

### Subprocess Tool
- [ ] `stdin=subprocess.DEVNULL`
- [ ] `CI=true`, `TERM=dumb`, `NO_COLOR=1` in env
- [ ] `timeout` parameter set
- [ ] Secrets via env vars (not CLI args, not logged)

### Code Environment
- [ ] `installCorePackages: false`
- [ ] Explicit pandas/numpy/dateutil/requests
- [ ] Python version matches target DSS instance
