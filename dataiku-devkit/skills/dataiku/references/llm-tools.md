# LLM Tools & Custom Agents Guide

> Complete reference for extending Dataiku's GenAI capabilities with custom agent tools and full agent implementations.

---

## Overview

Dataiku's LLM Mesh supports extensibility through:
- **Agent Tools**: Individual capabilities that agents can invoke
- **Custom Agents**: Full agent implementations with custom logic

These integrate with Prompt Studio, Agent Connect, and programmatic APIs.

---

## Agent Tools

### Folder Structure

```
python-agent-tools/
└── my-tool/
    ├── tool.json     # Tool descriptor (REQUIRED)
    └── tool.py       # Python implementation (REQUIRED)
```

### tool.json Reference

```json
{
  "meta": {
    "label": "Database Query Tool",
    "description": "Execute SQL queries against configured databases",
    "icon": "icon-database"
  },
  "params": [
    {
      "name": "connection_id",
      "type": "STRING",
      "label": "Database Connection",
      "description": "Dataiku connection name",
      "mandatory": true
    },
    {
      "name": "max_rows",
      "type": "INT",
      "label": "Max Rows",
      "defaultValue": 100,
      "description": "Maximum rows to return"
    },
    {
      "name": "allow_writes",
      "type": "BOOLEAN",
      "label": "Allow Write Operations",
      "defaultValue": false,
      "description": "Enable INSERT/UPDATE/DELETE"
    }
  ]
}
```

### tool.py Implementation

```python
"""
Database Query Tool

Allows LLM agents to execute SQL queries against databases.
"""
import json
import logging
from typing import Any, Dict

import dataiku
from dataiku.llm.agent_tools import BaseAgentTool

logger = logging.getLogger(__name__)


class DatabaseQueryTool(BaseAgentTool):
    """
    Custom agent tool for database queries.

    Execution flow:
    1. set_config() - Called once at tool initialization
    2. get_descriptor() - Called to get tool schema for LLM
    3. invoke() - Called when LLM decides to use the tool
    """

    def set_config(self, config: Dict[str, Any], plugin_config: Dict[str, Any]) -> None:
        """
        Initialize tool with configuration.

        Args:
            config: Tool instance parameters from tool.json params
            plugin_config: Plugin-level configuration
        """
        self.config = config
        self.plugin_config = plugin_config

        # Extract parameters
        self.connection_id = config.get("connection_id")
        self.max_rows = config.get("max_rows", 100)
        self.allow_writes = config.get("allow_writes", False)

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initialized DatabaseQueryTool for connection: {self.connection_id}")

    def get_descriptor(self, tool: Any) -> Dict[str, Any]:
        """
        Return tool schema for LLM.

        This defines how the LLM should invoke the tool.

        Args:
            tool: Tool context object

        Returns:
            Dict with description and inputSchema
        """
        return {
            "description": (
                "Execute SQL queries against a database. "
                "Use this tool when you need to retrieve or analyze data from the database. "
                f"Maximum {self.max_rows} rows will be returned. "
                f"Write operations are {'enabled' if self.allow_writes else 'disabled'}."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute. Use standard SQL syntax."
                    },
                    "explain": {
                        "type": "boolean",
                        "description": "If true, return query execution plan instead of results"
                    }
                },
                "required": ["query"]
            }
        }

    def invoke(self, input: Dict[str, Any], trace: Any) -> Dict[str, Any]:
        """
        Execute the tool with provided input.

        Args:
            input: Contains "input" key with the arguments matching inputSchema
            trace: Trace object for observability

        Returns:
            Dict with "output" key containing result string
        """
        args = input.get("input", {})
        query = args.get("query", "")
        explain = args.get("explain", False)

        self.logger.info(f"Executing query: {query[:100]}...")

        try:
            # Validate query
            if not self.allow_writes:
                query_upper = query.upper().strip()
                if any(kw in query_upper for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"]):
                    return {
                        "output": "Error: Write operations are not allowed. Only SELECT queries permitted."
                    }

            # Get executor
            executor = dataiku.core.sql.SQLExecutor2(connection=self.connection_id)

            if explain:
                # Return execution plan
                result = executor.query_to_df(f"EXPLAIN {query}")
                return {
                    "output": f"Query Plan:\n{result.to_string()}"
                }
            else:
                # Execute query
                result_df = executor.query_to_df(query)

                # Limit rows
                if len(result_df) > self.max_rows:
                    result_df = result_df.head(self.max_rows)
                    truncated = True
                else:
                    truncated = False

                # Format output
                output = result_df.to_markdown(index=False)
                if truncated:
                    output += f"\n\n[Results truncated to {self.max_rows} rows]"

                return {"output": output}

        except Exception as e:
            self.logger.error(f"Query failed: {e}")
            return {
                "output": f"Error executing query: {str(e)}"
            }
```

---

## Tool Input Schema Design

The `inputSchema` follows JSON Schema format and determines how the LLM calls your tool.

### Simple Schema

```python
def get_descriptor(self, tool):
    return {
        "description": "Search for documents by keyword",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords"
                }
            },
            "required": ["query"]
        }
    }
```

### Complex Schema with Multiple Parameters

```python
def get_descriptor(self, tool):
    return {
        "description": "Create a support ticket in the ticketing system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Ticket title (max 100 characters)"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Ticket priority level"
                },
                "category": {
                    "type": "string",
                    "enum": ["bug", "feature", "question", "other"],
                    "description": "Ticket category"
                },
                "assignee": {
                    "type": "string",
                    "description": "Optional: Username to assign ticket to"
                }
            },
            "required": ["title", "description", "priority"]
        }
    }
```

### Schema with Nested Objects

```python
def get_descriptor(self, tool):
    return {
        "description": "Send an email with optional attachments",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of recipient email addresses"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content (supports markdown)"
                },
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content": {"type": "string", "description": "Base64 encoded content"}
                        }
                    },
                    "description": "Optional file attachments"
                }
            },
            "required": ["to", "subject", "body"]
        }
    }
```

---

## Advanced Tool Patterns

### Tool with Knowledge Bank Access

```python
class RAGSearchTool(BaseAgentTool):
    """Search tool with Knowledge Bank integration."""

    def set_config(self, config, plugin_config):
        self.config = config
        self.kb_name = config.get("knowledge_bank")

        # Get Knowledge Bank
        client = dataiku.api_client()
        project = client.get_default_project()
        kb = project.get_knowledge_bank(self.kb_name)
        self.kb = kb.as_core_knowledge_bank()

    def get_descriptor(self, tool):
        return {
            "description": f"Search the {self.kb_name} knowledge base for relevant information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)"
                    }
                },
                "required": ["query"]
            }
        }

    def invoke(self, input, trace):
        args = input.get("input", {})
        query = args.get("query", "")
        top_k = args.get("top_k", 5)

        # Search Knowledge Bank
        results = self.kb.search_vectors(query=query, k=top_k)

        # Format results
        formatted = []
        for i, doc in enumerate(results, 1):
            formatted.append(f"**Result {i}** (score: {doc.get('score', 'N/A'):.3f})")
            formatted.append(doc.get("content", ""))
            formatted.append("")

        return {"output": "\n".join(formatted)}
```

### Tool with LLM Sub-calls

```python
class SummarizerTool(BaseAgentTool):
    """Tool that uses another LLM for summarization."""

    def set_config(self, config, plugin_config):
        self.config = config
        self.summarizer_llm_id = config.get("summarizer_llm_id")

        client = dataiku.api_client()
        project = client.get_default_project()
        self.llm = project.get_llm(self.summarizer_llm_id)

    def get_descriptor(self, tool):
        return {
            "description": "Summarize a long text into key points",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to summarize"
                    },
                    "max_points": {
                        "type": "integer",
                        "description": "Maximum number of bullet points"
                    }
                },
                "required": ["text"]
            }
        }

    def invoke(self, input, trace):
        args = input.get("input", {})
        text = args.get("text", "")
        max_points = args.get("max_points", 5)

        prompt = f"""Summarize the following text into {max_points} or fewer bullet points:

{text}

Provide only the bullet points, no additional commentary."""

        completion = self.llm.new_completion()
        completion.with_message(prompt, role="user")
        response = completion.execute()

        return {"output": response.text}
```

### Tool with External API

```python
import requests

class WeatherTool(BaseAgentTool):
    """Tool to get weather information."""

    def set_config(self, config, plugin_config):
        self.api_key = plugin_config.get("weather_api_key")
        self.base_url = "https://api.weatherapi.com/v1"

    def get_descriptor(self, tool):
        return {
            "description": "Get current weather for a location",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or coordinates (e.g., 'London' or '51.5,-0.1')"
                    }
                },
                "required": ["location"]
            }
        }

    def invoke(self, input, trace):
        args = input.get("input", {})
        location = args.get("location", "")

        try:
            response = requests.get(
                f"{self.base_url}/current.json",
                params={"key": self.api_key, "q": location}
            )
            response.raise_for_status()
            data = response.json()

            weather = data["current"]
            loc = data["location"]

            return {
                "output": (
                    f"Weather in {loc['name']}, {loc['country']}:\n"
                    f"- Condition: {weather['condition']['text']}\n"
                    f"- Temperature: {weather['temp_c']}C ({weather['temp_f']}F)\n"
                    f"- Humidity: {weather['humidity']}%\n"
                    f"- Wind: {weather['wind_kph']} km/h {weather['wind_dir']}"
                )
            }
        except Exception as e:
            return {"output": f"Error fetching weather: {e}"}
```

---

## Custom Agents

### Folder Structure

```
python-agents/
└── my-agent/
    ├── agent.json    # Agent descriptor (REQUIRED)
    └── agent.py      # Python implementation (REQUIRED)
```

### agent.json Reference

```json
{
  "meta": {
    "label": "Research Assistant",
    "description": "Agent specialized in research and analysis tasks",
    "icon": "icon-search"
  },
  "params": [
    {
      "name": "llm_id",
      "type": "LLM",
      "label": "Base LLM",
      "mandatory": true,
      "llmUsagePurpose": "GENERIC_COMPLETION"
    },
    {
      "name": "knowledge_banks",
      "type": "STRINGS",
      "label": "Knowledge Banks",
      "description": "Knowledge banks to search"
    },
    {
      "name": "max_iterations",
      "type": "INT",
      "label": "Max Iterations",
      "defaultValue": 10
    },
    {
      "name": "system_prompt",
      "type": "TEXTAREA",
      "label": "System Prompt",
      "defaultValue": "You are a helpful research assistant."
    }
  ]
}
```

### agent.py Implementation

```python
"""
Research Assistant Agent

Custom agent with specialized research capabilities.
"""
import json
import logging
from typing import Any, Dict, List, Optional

import dataiku
from dataiku.llm.agents import BaseAgent

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Custom agent implementation.

    Implements a ReAct-style agent loop with custom tools and logic.
    """

    def set_config(self, config: Dict[str, Any], plugin_config: Dict[str, Any]) -> None:
        """Initialize agent configuration."""
        self.config = config
        self.plugin_config = plugin_config

        self.llm_id = config.get("llm_id")
        self.kb_names = config.get("knowledge_banks", [])
        self.max_iterations = config.get("max_iterations", 10)
        self.system_prompt = config.get("system_prompt", "You are a helpful assistant.")

        # Initialize components
        self.client = dataiku.api_client()
        self.project = self.client.get_default_project()
        self.llm = self.project.get_llm(self.llm_id)

        # Load knowledge banks
        self.knowledge_banks = []
        for kb_name in self.kb_names:
            try:
                kb = self.project.get_knowledge_bank(kb_name)
                self.knowledge_banks.append(kb.as_core_knowledge_bank())
            except Exception as e:
                logger.warning(f"Could not load KB {kb_name}: {e}")

        logger.info(f"Research Agent initialized with {len(self.knowledge_banks)} knowledge banks")

    def get_descriptor(self, agent: Any) -> Dict[str, Any]:
        """Return agent description for UI."""
        return {
            "description": (
                "A research assistant that can search knowledge bases, "
                "analyze information, and provide comprehensive answers."
            ),
            "capabilities": [
                "Search multiple knowledge bases",
                "Synthesize information from multiple sources",
                "Provide citations for claims"
            ]
        }

    def run(self, input: Dict[str, Any], trace: Any) -> Dict[str, Any]:
        """
        Execute the agent.

        Args:
            input: Contains user query and conversation history
            trace: Trace object for observability

        Returns:
            Dict with response and metadata
        """
        query = input.get("query", "")
        conversation_history = input.get("history", [])

        logger.info(f"Processing query: {query[:100]}...")

        try:
            # Search knowledge bases
            context = self._search_knowledge_bases(query)

            # Build prompt with context
            prompt = self._build_prompt(query, context, conversation_history)

            # Generate response
            completion = self.llm.new_completion()
            completion.with_message(self.system_prompt, role="system")
            completion.with_message(prompt, role="user")

            response = completion.execute()

            return {
                "response": response.text,
                "sources": context.get("sources", []),
                "tokens_used": response.usage.get("total_tokens", 0)
            }

        except Exception as e:
            logger.error(f"Agent error: {e}")
            return {
                "response": f"I encountered an error while processing your request: {e}",
                "error": str(e)
            }

    def _search_knowledge_bases(self, query: str) -> Dict[str, Any]:
        """Search all configured knowledge bases."""
        all_results = []
        sources = []

        for i, kb in enumerate(self.knowledge_banks):
            try:
                results = kb.search_vectors(query=query, k=3)
                for doc in results:
                    all_results.append({
                        "content": doc.get("content", ""),
                        "score": doc.get("score", 0),
                        "source": f"KB{i+1}"
                    })
                    if doc.get("metadata", {}).get("source"):
                        sources.append(doc["metadata"]["source"])
            except Exception as e:
                logger.warning(f"KB search failed: {e}")

        # Sort by score and take top results
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top_results = all_results[:5]

        context_text = "\n\n".join([
            f"[Source: {r['source']}]\n{r['content']}"
            for r in top_results
        ])

        return {
            "text": context_text,
            "sources": list(set(sources))
        }

    def _build_prompt(self, query: str, context: Dict, history: List) -> str:
        """Build the prompt with context and history."""
        prompt_parts = []

        # Add context
        if context.get("text"):
            prompt_parts.append("## Relevant Information\n")
            prompt_parts.append(context["text"])
            prompt_parts.append("\n")

        # Add conversation history
        if history:
            prompt_parts.append("## Previous Conversation\n")
            for msg in history[-5:]:  # Last 5 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"{role}: {content}\n")
            prompt_parts.append("\n")

        # Add current query
        prompt_parts.append("## Current Question\n")
        prompt_parts.append(query)
        prompt_parts.append("\n\n")

        # Add instructions
        prompt_parts.append("Please provide a comprehensive answer based on the information above. ")
        prompt_parts.append("If citing sources, indicate which source the information came from.")

        return "".join(prompt_parts)
```

---

## Testing Tools

### Unit Test Pattern

```python
import pytest
from unittest.mock import Mock, patch

from python_agent_tools.my_tool.tool import DatabaseQueryTool


class TestDatabaseQueryTool:

    @pytest.fixture
    def tool(self):
        tool = DatabaseQueryTool()
        tool.set_config(
            config={
                "connection_id": "test_connection",
                "max_rows": 100,
                "allow_writes": False
            },
            plugin_config={}
        )
        return tool

    def test_get_descriptor(self, tool):
        descriptor = tool.get_descriptor(None)
        assert "description" in descriptor
        assert "inputSchema" in descriptor
        assert descriptor["inputSchema"]["properties"]["query"]["type"] == "string"

    def test_blocks_write_queries(self, tool):
        result = tool.invoke(
            {"input": {"query": "DELETE FROM users"}},
            trace=None
        )
        assert "Error" in result["output"]
        assert "not allowed" in result["output"]

    @patch("dataiku.core.sql.SQLExecutor2")
    def test_executes_select(self, mock_executor, tool):
        import pandas as pd

        mock_df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
        mock_executor.return_value.query_to_df.return_value = mock_df

        result = tool.invoke(
            {"input": {"query": "SELECT * FROM users"}},
            trace=None
        )

        assert "Alice" in result["output"]
        assert "Bob" in result["output"]
```

---

## Tool Execution Flow

Understanding the execution order:

```
1. Agent receives user message
2. Agent calls tool.get_descriptor() to understand capabilities
3. Agent decides to use tool based on query
4. Agent calls tool.invoke(input, trace)
5. Tool executes and returns result
6. Agent incorporates result into response
```

### Quick Test UI

The Dataiku Quick Test UI issues these calls:
1. `set_config()` - One-time initialization
2. `get_descriptor()` - Get tool schema
3. `load_sample_query()` - Pre-fill test input (optional)
4. `invoke()` - Execute with test input

### load_sample_query() — Pre-fill Quick Test Input

Optional method that provides default input for the Quick Test UI. Without it, users see an empty input field:

```python
class MyTool(BaseAgentTool):
    def load_sample_query(self, tool):
        """Pre-fill Quick Test with a useful example."""
        return {"input": {"question": "What are the top 10 customers by revenue?"}}
```

### inputSchema Best Practices

Use `$id` for schema identification (follows JSON Schema spec):

```python
def get_descriptor(self, tool):
    return {
        "description": build_descriptor(self.model_name, self.model_desc),
        "inputSchema": {
            "$id": "https://dataiku.com/agents/tools/my-tool/input",
            "title": "My Tool Input",
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural language question"}
            },
            "required": ["question"],
        },
    }
```

Build descriptions dynamically from config for better LLM tool selection:

```python
def build_descriptor(model_name, model_desc):
    desc = f"Query the '{model_name}' semantic model using natural language."
    if model_desc:
        desc += f" This model contains: {model_desc}"
    return desc
```

---

## Multimodal Tool I/O (DSS 14+)

Agent tools can accept image inputs and return multimodal outputs (not just text):

```python
def invoke(self, input, trace):
    args = input.get("input", {})

    # Image inputs are provided as base64-encoded data
    image_data = args.get("image")  # base64 string if image was sent

    # Return multimodal output (image + text)
    return {
        "output": "Analysis complete",
        "images": [{"data": base64_result, "mimeType": "image/png"}]
    }
```

---

## Best Practices

### Tool Design
- Keep tools focused on single responsibilities
- Provide detailed descriptions for the LLM
- Include examples in schema descriptions
- Handle errors gracefully and return informative messages

### Input Validation
```python
def invoke(self, input, trace):
    args = input.get("input", {})

    # Validate required fields
    if not args.get("query"):
        return {"output": "Error: query parameter is required"}

    # Validate types
    try:
        limit = int(args.get("limit", 10))
    except ValueError:
        return {"output": "Error: limit must be an integer"}

    # Proceed with validated input
    ...
```

### Observability
```python
def invoke(self, input, trace):
    # Log invocation
    self.logger.info(f"Tool invoked with: {input}")

    # Add to trace for observability
    if trace:
        trace.attributes["tool_version"] = "1.0"
        trace.attributes["parameters"] = input

    result = self._execute(input)

    # Log result
    self.logger.info(f"Tool returned: {len(result.get('output', ''))} chars")

    return result
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Tool not appearing | Check tool.json syntax, reload plugin |
| LLM not using tool | Improve description clarity, check inputSchema |
| Invocation errors | Add logging in invoke(), check input structure |
| Timeout issues | Optimize tool execution, add progress indicators |
| Permission errors | Verify plugin/tool has required DSS permissions |
| `'SpanBuilder' has no attribute 'set_attribute'` | Use `trace.attributes[key] = value` (dict assignment), not `trace.set_attribute()` |
| `No module 'dateutil'` / `No module 'numpy'` | Code env needs explicit deps -- see `code-environments.md` |
| Subprocess tool hangs | Set `stdin=subprocess.DEVNULL` + `env["CI"]="true"` + `env["TERM"]="dumb"` |
| Tool works via SSH but not in DSS | DSS runs as `dssuser_dataiku` (not `dataiku`). Check file perms and HOME dir. |

### Code Environment for Agent Tools

Agent tools need an explicit plugin code environment. Use the canonical Python package policy in `code-environments.md`.

### Subprocess-Based Agent Tools

When your tool spawns external CLI processes:

```python
result = subprocess.run(
    cmd,
    stdin=subprocess.DEVNULL,   # CRITICAL: prevents blocking on stdin
    capture_output=True,
    text=True,
    timeout=timeout_seconds,
    env={
        **os.environ,
        "CI": "true",           # Skip interactive prompts
        "TERM": "dumb",         # Disable terminal formatting
        "NO_COLOR": "1",        # Disable color codes
        "MY_API_KEY": secret,   # Pass secrets via env, not args
    },
    cwd=working_directory,
)
```
