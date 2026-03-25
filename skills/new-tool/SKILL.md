---
name: new-tool
description: Add a new agent tool to an existing Dataiku DSS plugin. Generates tool.json schema and tool.py implementation.
disable-model-invocation: true
context: fork
---

Create a new Dataiku agent tool in an existing plugin.

## Gather Info

Ask the user for:
1. **Plugin** — which plugin to add the tool to (look for directories containing `plugin.json`)
2. **Tool name** — kebab-case name (e.g., `search-documents`)
3. **Description** — what the tool does (1-2 sentences)
4. **Input parameters** — what the tool accepts (name, type, description, required?)

## Generate Files

Create the tool directory at `{plugin}/python-agent-tools/{tool-name}/` with:

### `tool.json`
```json
{
  "meta": {
    "label": "{Tool Label}",
    "description": "{description}"
  },
  "params": [],
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

### `tool.py`
Follow the standard Dataiku agent tool pattern — extend `BaseAgentTool` with `get_descriptor`, `set_config`, `invoke`. Reference `skills/dataiku/references/llm-tools.md` for detailed patterns and examples.

Key requirements:
- Put the tool description in a `TOOL_DESCRIPTION` constant
- Include clear docstrings
- Validate inputs in `invoke()`
- Return `{"output": "..."}` from invoke
- Use logging with a `[ToolName]` prefix throughout
- Handle errors gracefully with user-friendly messages

```python
"""Agent Tool: {Tool Label}

{description}
"""

import logging
from dataiku.llm.agent_tools import BaseAgentTool

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = """{description}

When to use: ...
When NOT to use: ...
"""


class {ToolClassName}(BaseAgentTool):
    def get_descriptor(self, tool_config, trace):
        return {
            "description": TOOL_DESCRIPTION,
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    def set_config(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config

    def invoke(self, input, trace):
        args = input.get("input", {})
        # Validate inputs
        # Process request
        # Return result
        return {"output": "..."}
```

## After Generation

1. Format the code (e.g., `ruff format {plugin}/python-agent-tools/{tool-name}/`)
2. Show the user the generated files and ask if they want to adjust the schema or implementation
3. Remind them to deploy with `dku plugin push {plugin}` when ready
