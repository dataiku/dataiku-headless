---
name: code-agent-reference
description: "Configuration guide for PYTHON_AGENT — BaseLLM subclass interface, all four method options, query structure, image inputs, code env, trace, and flow dependencies."
---

# Code Agent (PYTHON_AGENT)

A fully custom agent implemented in Python. The class must subclass `BaseLLM` from `dataiku.llm.python` and implement one of four methods depending on the desired execution pattern. DSS invokes the class directly — there is no built-in LLM loop, tool dispatch, or memory management; all of that is the developer's responsibility.

**Prefer TOOLS_USING_AGENT or STRUCTURED_AGENT** unless you need capabilities unavailable through visual agents (custom streaming, multimodal processing, external SDK integration, etc.).

## Class Interface — Four Method Options

Implement exactly one method. Do not implement more than one.

```python
from dataiku.llm.python import BaseLLM

class MyLLM(BaseLLM):
    def __init__(self):
        pass

    # Option 1 — synchronous, returns a dict
    def process(self, query, settings, trace):
        return {"text": "response"}

    # Option 2 — async, returns a dict
    async def aprocess(self, query, settings, trace):
        return {"text": "response"}

    # Option 3 — synchronous generator, yields chunk dicts
    def process_stream(self, query, settings, trace):
        yield {"chunk": {"text": "partial response"}}

    # Option 4 — async generator, yields chunk dicts
    async def aprocess_stream(self, query, settings, trace):
        yield {"chunk": {"text": "partial response"}}
```

All four methods receive the same three parameters: `query` (the conversation), `settings` (completion settings), and `trace` (a span builder for observability).

## Query Structure

For simple text input, access the latest message content directly:

```python
prompt = query["messages"][-1]["content"]
```

For multipart messages (e.g. text + image), the message has a `parts` list instead of a plain `content` string. Each part has a `type` field:

| Part type | Field | Notes |
|-----------|-------|-------|
| `TEXT` | `part["text"]` | Plain text content |
| `IMAGE_INLINE` | `part["inlineImage"]` | Base64-encoded image data |

```python
parts = query["messages"][-1]["parts"]
for part in parts:
    if part["type"] == "TEXT":
        text = part["text"]
    elif part["type"] == "IMAGE_INLINE":
        img_b64 = part["inlineImage"]
```

The full conversation history is available as `query["messages"]` — iterate it for context-aware responses.

## Response Format

**Non-streamed** (`process` / `aprocess`) — return a dict:

```python
return {
    "text": "the response text",
}
```

**Streamed** (`process_stream` / `aprocess_stream`) — yield chunk dicts:

```python
yield {"chunk": {"text": "partial text"}}
# ... more chunks ...
```

## Trace

The `trace` parameter is a span builder for observability. Use it to track subprocesses and attach metadata:

```python
with trace.subspan("call-llm") as span:
    span.inputs["prompt"] = prompt
    result = call_my_llm(prompt)
    span.outputs["result"] = result
```

## Configuration via `update_agent_settings`

| Param | Notes |
|-------|-------|
| `code` | Full Python source — must define a class subclassing `BaseLLM` |
| `code_env_name` | Name of a DSS code environment to run the agent in; sets `envMode` to `EXPLICIT_ENV` automatically |
| `supports_image_inputs` | Set to `true` to enable image input in the DSS chat UI; required for multimodal agents |

`get_agent_settings` returns `code_env_mode`, `code_env_name`, and `supports_image_inputs` alongside `code`.

## Flow Dependencies

Code agents can declare dependencies on DSS objects (datasets, saved models, knowledge banks), which makes connections visible in the Dataiku Flow:

```python
class MyLLM(BaseLLM):
    dependencies = [
        {"type": "DATASET", "ref": "my_dataset"},
        {"type": "SAVED_MODEL", "ref": "my_model_id"},
        {"type": "KNOWLEDGE_BANK", "ref": "my_kb_id"},
    ]
```

## Calling a DSS-Managed LLM from Code

```python
import dataiku

llm = dataiku.api_client().get_default_project().get_llm("openai:MY_CONNECTION:gpt-5-mini")
completion = llm.new_completion()
completion.with_message("system instructions", "system")
completion.with_message(user_text, "user")
resp = completion.execute()
return {"text": resp.text}
```

For LangChain compatibility, use `DKUChatModel` to wrap a DSS LLM connection:

```python
from dataiku.langchain.dku_chat_model import DKUChatModel
llm = DKUChatModel(llm_id="openai:MY_CONNECTION:gpt-5-mini")
```

## Guardrails

1. **Implement exactly one method** — `process`, `aprocess`, `process_stream`, or `aprocess_stream`. Implementing multiple is undefined behavior.
2. **`supports_image_inputs` must be `true`** for multimodal agents; otherwise the DSS UI will not send image parts.
3. **Code env must have the required packages** — if your code imports third-party libraries, set `code_env_name` to an environment that includes them.
4. **Do not hardcode connection names** — use a project variable or pass the connection name as a parameter.
5. **Test with `run_agent` after code changes** — syntax errors in the agent class surface at runtime, not at save time.
