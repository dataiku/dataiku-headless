# Guardrails

> Complete reference for building plugin guardrails in Dataiku DSS. Guardrails run before (query check) and/or after (response check) every LLM call in the Mesh, providing safety, compliance, and quality controls.

---

## Overview

A guardrail is a plugin component that intercepts LLM completions. It receives the full completion payload and can:

- **Block** a query or response by raising an exception
- **Rewrite** content by mutating the `input` dict
- **Observe** calls via the trace/span API

Guardrails chain: DSS applies them in order, stopping at the first exception.

---

## File Structure

```
my-plugin/
└── python-guardrails/
    └── my-guardrail/
        ├── guardrail.json
        └── guardrail.py
```

---

## guardrail.json

```json
{
  "meta": {
    "label": "My Guardrail",
    "description": "Describe what this guardrail checks."
  },
  "params": [
    {
      "name": "blocked_terms",
      "type": "TEXTAREA",
      "label": "Blocked Terms (one per line)",
      "defaultValue": ""
    },
    {
      "name": "check_queries",
      "type": "BOOLEAN",
      "label": "Check Queries",
      "defaultValue": true
    },
    {
      "name": "check_responses",
      "type": "BOOLEAN",
      "label": "Check Responses",
      "defaultValue": true
    }
  ]
}
```

---

## BaseGuardrail Implementation

```python
"""Guardrail: My Guardrail

Describe what this guardrail checks.
"""

import logging
from dataiku.llm.guardrails import BaseGuardrail

logger = logging.getLogger(__name__)


class MyGuardrail(BaseGuardrail):

    def set_config(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config

    def process(self, input, trace):
        # Check queries (before LLM call)
        messages = input.get("completionQuery", {}).get("messages", [])
        if messages:
            with trace.subspan("check-query") as span:
                last_message = messages[-1].get("content", "")
                logger.info("[MyGuardrail] Checking query: %s...", last_message[:100])

                # Raise to block:    raise Exception("Query blocked: reason")
                # Rewrite to filter: input["completionQuery"]["messages"][-1]["content"] = filtered

                span.attributes["query_checked"] = True

        # Check responses (after LLM call)
        response_text = input.get("completionResponse", {}).get("text", "")
        if response_text:
            with trace.subspan("check-response") as span:
                logger.info("[MyGuardrail] Checking response: %s...", response_text[:100])

                # Modify response: input["completionResponse"]["text"] = filtered_response

                span.attributes["response_checked"] = True

        return input
```

**Key rules:**
- Always return `input` (modified or not)
- `trace.subspan(name)` for observability — do NOT call `trace.set_attribute()`
- `span.attributes[key] = value` records metadata visible in the audit UI
- Raise to block; mutate `input` to rewrite/filter
- Fail safe: block on unexpected error rather than pass through

---

## Input Structure

```python
# input dict — both keys may be present in the same call
input = {
    # Present before LLM call (query check)
    "completionQuery": {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user",   "content": "User's message here"}
        ]
    },
    # Present after LLM call (response check)
    "completionResponse": {
        "text": "LLM response text"
    }
}
```

The last message in `completionQuery.messages` is the user's current input.

---

## Common Patterns

### Content Filter (blocklist)

```python
def set_config(self, config, plugin_config):
    raw = config.get("blocked_terms", "")
    self.blocked_terms = [t.strip().lower() for t in raw.splitlines() if t.strip()]
    self.check_queries = config.get("check_queries", True)
    self.check_responses = config.get("check_responses", True)

def process(self, input, trace):
    with trace.subspan("Content Filter") as span:
        if self.check_queries and "completionQuery" in input:
            messages = input["completionQuery"].get("messages", [])
            if messages:
                text = messages[-1].get("content", "").lower()
                for term in self.blocked_terms:
                    if term in text:
                        logger.warning("[Content Filter] Blocked term in query: %s", term)
                        raise Exception("Query blocked: prohibited content detected.")

        if self.check_responses and "completionResponse" in input:
            text = input["completionResponse"].get("text", "").lower()
            for term in self.blocked_terms:
                if term in text:
                    logger.warning("[Content Filter] Blocked term in response: %s", term)
                    input["completionResponse"]["text"] = "Response blocked: prohibited content."

        span.attributes["terms_checked"] = len(self.blocked_terms)
    return input
```

### PII Detection

```python
import re

EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
PHONE_RE = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')

def process(self, input, trace):
    with trace.subspan("PII Detection") as span:
        if "completionQuery" in input:
            messages = input["completionQuery"].get("messages", [])
            if messages:
                text = messages[-1].get("content", "")
                if EMAIL_RE.search(text):
                    raise Exception("Query contains PII (email address). Please remove it.")
                if PHONE_RE.search(text):
                    raise Exception("Query contains PII (phone number). Please remove it.")
        span.attributes["pii_checked"] = True
    return input
```

### LLM Judge (delegate safety check to another LLM)

```python
def set_config(self, config, plugin_config):
    import dataiku
    project = dataiku.api_client().get_default_project()
    self.llm_judge = project.get_llm(config["judge_llm_id"])
    self.system_prompt = config.get("system_prompt", "You are a content safety judge.")
    self.block_message = config.get("block_message", "Content blocked by safety policy.")

def process(self, input, trace):
    with trace.subspan("LLM Judge") as span:
        if "completionQuery" in input:
            messages = input["completionQuery"].get("messages", [])
            if messages:
                text = messages[-1].get("content", "")
                completion = self.llm_judge.new_completion()
                completion.with_message(self.system_prompt, role="system")
                completion.with_message(
                    f"Is this content a policy violation? Answer yes or no only.\n\n{text}",
                    role="user"
                )
                resp = completion.execute()
                if span and hasattr(resp, "trace"):
                    span.append_trace(resp.trace)
                if "yes" in resp.text.strip().lower():
                    raise Exception(self.block_message)
    return input
```

### Token Budget Enforcement

```python
def set_config(self, config, plugin_config):
    self.max_input_tokens = int(config.get("max_input_tokens", 4000))

def process(self, input, trace):
    with trace.subspan("Token Budget") as span:
        if "completionQuery" in input:
            messages = input["completionQuery"].get("messages", [])
            total_chars = sum(len(m.get("content", "")) for m in messages)
            # Rough estimate: 1 token ≈ 4 chars
            estimated_tokens = total_chars // 4
            span.attributes["estimated_input_tokens"] = estimated_tokens
            if estimated_tokens > self.max_input_tokens:
                raise Exception(
                    f"Input too long ({estimated_tokens} estimated tokens > {self.max_input_tokens} limit)."
                )
    return input
```

---

## Trace & Observability

```python
def process(self, input, trace):
    # Top-level span for this guardrail
    with trace.subspan("My Guardrail") as span:
        # Nested spans for sub-steps
        with span.subspan("step-1") as step:
            step.attributes["key"] = "value"   # Visible in audit UI
            # ... logic ...

        with span.subspan("step-2") as step:
            # Append a child LLM trace (for LLM judge pattern)
            if hasattr(llm_resp, "trace"):
                step.append_trace(llm_resp.trace)

    return input
```

**Do NOT use** `trace.set_attribute()` — use `span.attributes[key] = value` instead.

---

## Design Checklist

- [ ] `guardrail.json` has `meta.label` and `meta.description`
- [ ] Class extends `BaseGuardrail` (from `dataiku.llm.guardrails`)
- [ ] `set_config(config, plugin_config)` stores settings as instance vars
- [ ] `process(input, trace)` always returns `input`
- [ ] Uses `trace.subspan()` — not `trace.set_attribute()`
- [ ] Raises exception to block (with a user-readable message)
- [ ] Mutates `input` dict to rewrite/filter (does not replace the dict)
- [ ] Logs with `logger.warning()` when blocking
- [ ] Fails safe on unexpected errors (block rather than allow through)
- [ ] Does not hardcode LLM IDs — reads from `config`
