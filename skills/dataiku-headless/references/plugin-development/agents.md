# Custom Agent Plugin Components

Start with [Plugin development](../plugin-development.md). For a tool that an agent
calls, see [Agent tools](./agent-tools.md).

Use `python-agents/<component-id>/agent.json` and `agent.py`, following the
[custom-agent tutorial](https://developer.dataiku.com/latest/tutorials/plugins/agent/generality/index.html).
Agents use the completion interface rather than a tool's `invoke` method. If the agent
uses an LLM, dataset, or Knowledge Bank, let users select it in the agent's settings.
Preserve the conversation history the agent needs and pass traces through its calls.
Test supported response modes and tool failures.
