# Simple Agent (`TOOLS_USING_AGENT`)

A simple agent is a single ReAct loop. Its LLM receives the conversation, chooses tools from their `additionalDescriptionForLLM`, reads tool results, and repeats until it produces a response.

## Model

- Conversation history is its only memory. There is no state or scratchpad.
- The LLM decides when to stop; there are no explicit exit conditions.
- Tool results and their sources are available to the LLM in the loop.

## Interpreting Configuration

- `llm_id` selects the tool-calling LLM.
- `system_prompt` defines behavior, tone, and fallback handling.
- `tool_ids` identifies the project-level tools available to the agent.

## Design Guidance

Use a simple agent for straightforward tool-using conversations where the LLM can choose the next step. Use a structured agent when the workflow requires deterministic branching, parallelism, explicit memory, or guaranteed processing after a tool call.

Tool descriptions are the main signal for correct tool selection. Read [agent-tools.md](agent-tools.md) when the task involves tool behavior or design.
