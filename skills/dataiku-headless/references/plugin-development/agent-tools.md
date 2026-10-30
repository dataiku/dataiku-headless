# Agent-Tool Plugin Components

Start with [Plugin development](../plugin-development.md). The plugin defines a tool
type that users can configure as an agent tool in their projects. Tools can perform
calculations, process inputs, work with Dataiku resources, or call external services.

## Implement The Tool

Use `python-agent-tools/<component-id>/tool.json` and `tool.py`.
`tool.json` defines any settings users configure, such as processing options or
result limits. Keep these separate from the arguments the model supplies on each call.

Implement `BaseAgentTool` from `dataiku.llm.agent_tools` following the
[custom-tool contract](https://developer.dataiku.com/latest/tutorials/plugins/custom-tools/generality/index.html):

| Method | Purpose |
| --- | --- |
| `set_config(config, plugin_config)` | Store and validate the settings. |
| `get_descriptor(self, tool)` | Describe when to use the tool and define its JSON `inputSchema`. |
| `invoke(self, input, trace)` | Read `input["input"]`; return `output` and optional `sources` and `artifacts`. |
| `load_sample_query(self, tool)` | Return sample arguments for the test panel. |

In the tool test panel, put the arguments inside `input`. For example, a calculation
tool might accept:

```json
{"input": {"values": [2, 4, 6]}, "context": {}}
```

## User Access And Results

- If the tool needs credentials, get them from a configured connection or preset.
  Do not ask the model to supply credentials or choose the user identity.
- If the tool needs to run as the Dataiku end user, use `context.dkuCallerTicket`
  with the documented impersonation mechanism. If the ticket is required but missing, return an error.
  Running as the tool runner instead must be an explicit setting.
- Put the answer in `output`, supporting evidence in `sources`, and displayable
  results such as tables in `artifacts`. Follow the [sources and artifacts reference](https://developer.dataiku.com/latest/concepts-and-examples/agents.html).
- If the tool queries a service, explain what each limit controls. Limiting returned
  rows or displayed tables may not reduce the work or cost of the underlying query.

Test input validation, outputs, and failures, plus any identity settings, limits,
or service responses the tool uses. In Dataiku, check that the agent selects the tool
appropriately and displays its results, including any citations and artifacts.
Use the tool test UI when Headless cannot run the tool.
