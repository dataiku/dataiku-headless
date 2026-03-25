---
name: new-guardrail
description: Add an LLM guardrail to an existing Dataiku DSS plugin. Generates guardrail.json and guardrail.py with proper trace handling.
disable-model-invocation: true
context: fork
---

Create a new Dataiku LLM guardrail in an existing plugin.

## Gather Info

Ask the user for:
1. **Plugin** — which plugin to add the guardrail to (look for directories containing `plugin.json`)
2. **Guardrail name** — kebab-case name (e.g., `pii-detector`)
3. **Description** — what the guardrail checks for
4. **Configuration params** — what the guardrail needs (e.g., LLM ID, thresholds, prompts)
5. **Check scope** — queries only, responses only, or both

## Generate Files

Create the guardrail directory at `{plugin}/python-guardrails/{guardrail-name}/` with:

### `guardrail.json`
```json
{
  "meta": {
    "label": "{Guardrail Label}",
    "description": "{description}"
  },
  "params": []
}
```

### `guardrail.py`

Follow the standard Dataiku guardrail pattern — extend `BaseGuardrail` with `set_config` and `process`.

```python
"""Guardrail: {Guardrail Label}

{description}
"""

import logging
from dataiku.llm.guardrails import BaseGuardrail

logger = logging.getLogger(__name__)


class {GuardrailClassName}(BaseGuardrail):
    def set_config(self, config, plugin_config):
        """Initialize guardrail with configuration.

        Args:
            config: Guardrail-specific configuration from guardrail.json params
            plugin_config: Plugin-level configuration
        """
        self.config = config
        self.plugin_config = plugin_config

    def process(self, input, trace):
        """Process a completion request/response through the guardrail.

        Args:
            input: Dict containing:
                - completionQuery.messages: list of conversation messages
                - completionResponse.text: the LLM response (if checking responses)
            trace: Trace object for observability

        Returns:
            Modified input dict. Raise an exception to block the request entirely.
        """
        # Check queries (before LLM call)
        messages = input.get("completionQuery", {}).get("messages", [])
        if messages:
            with trace.subspan("check-query") as span:
                last_message = messages[-1].get("content", "")
                logger.info(f"[{GuardrailClassName}] Checking query: {last_message[:100]}...")

                # TODO: implement query checking logic
                # Raise an exception to block the query:
                #   raise Exception("Query blocked: reason")
                # Or modify the input to filter/rewrite:
                #   input["completionQuery"]["messages"][-1]["content"] = filtered

                span.attributes["query_checked"] = True

        # Check responses (after LLM call)
        response_text = input.get("completionResponse", {}).get("text", "")
        if response_text:
            with trace.subspan("check-response") as span:
                logger.info(f"[{GuardrailClassName}] Checking response: {response_text[:100]}...")

                # TODO: implement response checking logic
                # Modify response if needed:
                #   input["completionResponse"]["text"] = filtered_response

                span.attributes["response_checked"] = True

        return input
```

Key guardrail patterns:
- Use `trace.subspan()` for observability (NOT `trace.set_attribute()` — that's OpenTelemetry, not DSS)
- Use `trace.attributes[key] = value` or `span.attributes[key] = value` to record check results
- Raise exceptions to **block** queries (for security guardrails)
- Modify `input` dict to **filter** or **rewrite** content
- Always fail safely — for security guardrails, block on error rather than allow through
- Use logging with a `[GuardrailName]` prefix throughout

## After Generation

1. Format the code (e.g., `ruff format {plugin}/python-guardrails/{guardrail-name}/`)
2. Show generated files and ask if the user wants to adjust the implementation
3. Remind them to deploy with `dku plugin push {plugin}` when ready
