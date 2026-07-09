---
name: simple-agent-reference
description: "Configuration guide for TOOLS_USING_AGENT (simple ReAct agent) — LLM, system prompt, and tool setup."
---

# Simple Agent (TOOLS_USING_AGENT)

A single ReAct loop: the LLM sees the conversation, picks which tools to call based on their `additionalDescriptionForLLM`, calls them, reads the results, and repeats until it has enough to respond. The full conversation context is passed to every tool call. Sources from tool results are aggregated and returned with the response.

There is **no state or scratchpad** — memory is conversation history only. The loop has no explicit exit conditions; the LLM decides when it's done. For anything requiring deterministic branching, parallel work, or guaranteed post-processing, use a STRUCTURED_AGENT instead.

## Configuration via `update_agent_settings`

| Param | Notes |
|-------|-------|
| `llm_id` | Must support **tool calling** — Anthropic, OpenAI, Azure OpenAI, Mistral, Vertex Gemini, Bedrock Claude; discover with `list_llms` |
| `system_prompt` | Instructions for the LLM: tone, behavior, what to do when it doesn't know |
| `tool_ids` | Full list of active tool IDs — **replaces** the existing list; include every tool you want active |

## Tool Management

- Use `list_agent_tools` to discover available tool IDs before calling `update_agent_settings`
- `tool_ids` replaces the full list on every call — to add a tool, send the existing list plus the new one
- To disable a tool temporarily, send the full list with the unwanted tool omitted (the agent stores `{toolRef, disabled}` internally)
- Read the [agent tools reference](agent-tools.md) for tool creation, config shapes, and guardrails

## Guardrails

1. **LLM must support tool calling.** Not all LLMs do — use `list_llms` and verify before setting `llm_id`.
2. **Tool descriptions drive selection.** A vague `additionalDescriptionForLLM` leads to the LLM skipping or misusing a tool. Be specific.
3. **No state between turns.** Each turn starts fresh from conversation history. If the user asks a follow-up that depends on a prior tool result, the LLM must re-call the tool or the result must be in the conversation history.
4. **Test with `run_agent` after each tool change.** Tool list replacement can silently remove tools if the full list is not sent.
