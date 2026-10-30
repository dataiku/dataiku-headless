# Guardrail Plugin Components

Start with [Plugin development](../plugin-development.md).

Use `python-guardrails/<component-id>/guardrail.json` and `guardrail.py`, following
[the guardrail tutorial](https://developer.dataiku.com/latest/tutorials/plugins/guardrail/generality/index.html).
Preserve the surrounding request or response structure. Specify whether the guardrail
checks inputs, outputs, or both; whether it blocks, audits, or rewrites; and what
happens when its checking service is unavailable.
Test each phase and outcome through an actual LLM call.
[TypeSafe AI](https://github.com/dataiku/dss-plugin-typesafe-ai) illustrates audit versus block modes.
