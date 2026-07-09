---
name: data-quality
description: Inspect, create, update, compute, and delete Dataiku DSS Data Quality rules on datasets through MCP tools. Use when an agent must list dataset DQ rules, inspect DQ status/results/history, create raw rule payloads, update existing rules, compute rules, or delete rules with explicit user intent.
---

# Data Quality Rule Operations

Use Dataiku MCP tools to manage DSS Data Quality rules on datasets. These are the newer dataset Data Quality rules, not legacy metrics/checks and not local dataset profiling.

## Follow This Execution Pattern

1. For inspection, call `list_data_quality_rules` first. It returns compact summaries for discovery, not full configs. Use `get_data_quality_rule` when you need one exact raw rule by ID. Then use `get_data_quality_status`, `get_data_quality_rule_results`, or `get_data_quality_rule_history` depending on whether the user needs current dataset state, latest rule outcomes, or trends.
2. For creation, pass a raw JSON object to `create_data_quality_rule`. Require at least `type`. For column-based rules, call `get_dataset_info` and verify referenced columns exist. Use the observed payload reference before constructing type-specific fields.
3. For updates, list the rules and read the target rule with `get_data_quality_rule` first. Modify the returned raw rule config and call `update_data_quality_rule` with the complete object.
4. For compute, announce the run before calling `compute_data_quality_rules`. Use async only when the dataset is expensive or partition-heavy and the user accepts getting a DSSFuture ID; follow async runs with `get_future_status`.
5. For delete, require explicit user confirmation before calling `delete_data_quality_rule`.
6. When reporting results, distinguish the dataset-level status from individual rule outcomes. If a configured rule has no latest result, say that no computed result is available.

## Tool Reference

| Goal | Tool |
| --- | --- |
| List configured rules, compact summaries, and dataset monitor flag | `list_data_quality_rules` |
| Read one full raw rule config | `get_data_quality_rule` |
| Read dataset-level DQ status | `get_data_quality_status` |
| Read latest computed rule result(s) | `get_data_quality_rule_results` |
| Read rule result history | `get_data_quality_rule_history` |
| Create a rule from raw config | `create_data_quality_rule` |
| Replace a rule config | `update_data_quality_rule` |
| Compute all enabled rules, or one rule when `rule_id` is provided | `compute_data_quality_rules` |
| Inspect an async compute future | `get_future_status` |
| Delete one rule | `delete_data_quality_rule` |

## Key Behaviors

- **Rule IDs vs names**: Tools that mutate rules require the `rule_id`, not the display name. Use `list_data_quality_rules` first to resolve names to IDs.
- **Updates are full-replace**: `update_data_quality_rule` replaces the rule config. Read the current rule with `get_data_quality_rule`, modify only the intended fields, and pass the complete modified rule back.
- **Nested config**: Rules can contain nested objects such as `driftParams`, `expectedSchema`, `envSelection`, and `meta`. Preserve sibling fields unless the user explicitly wants to remove them.
- **Type changes**: Changing a rule's type is allowed by the MCP tool, but should be treated as repurposing the rule. Prefer creating a new rule unless the user explicitly wants to replace the existing rule's meaning.
- **Python rules**: Prefer built-in rule types. Use Python-code rules only as a fallback when no built-in rule type can express the desired check.

## Raw Rule Payloads

Data Quality rule payloads are type-specific. Prefer raw payloads and observed reference shapes over invented field names.

Read [Rule settings and payload reference](references/data_quality_settings_and_payload.md) before constructing or editing type-specific payloads beyond simple metadata toggles.

For column-based rules, validate referenced columns with `get_dataset_info` before creation.

## Status And Results

The dataset-level status is not the same as individual rule results.

- `get_data_quality_status` returns the dataset's current/worst DQ status when DSS has one.
- `get_data_quality_rule_results` returns only the latest computed results available for the requested partition; uncomputed rules may simply be absent.
- `get_data_quality_rule_history` returns historical computed rule results, not rule configuration.
- If DSS has no computed status yet, the tool may return `status: null` with a warning rather than inventing a status string.

Known outcomes include `OK`, `WARNING`, `ERROR`, and `EMPTY`. Treat unknown strings as DSS-provided statuses and report them literally.

## Dataset Monitor

`list_data_quality_rules` includes the dataset-level `monitor` flag when DSS returns it. This flag controls whether the dataset contributes to broader Data Quality monitoring views. Rule configuration and rule computation are separate from this flag.

Monitor is read-only in this v1 skill. Do not attempt to write it unless a future MCP tool explicitly supports that operation.

## Safety Rules

- Never delete a rule without explicit user confirmation.
- Never invent project keys, dataset names, rule IDs, or connection names.
- Prefer built-in rule types over Python rules; create or edit Python-code rules only when no built-in rule type can express the desired check, and review the code before saving it.
- Be explicit about partition handling: `partition="NP"` for non-partitioned datasets, a concrete partition ID for partitioned datasets, or `"ALL"` when the user asks for whole-dataset computation.
- Treat `autoRun=true` as build behavior: DSS computes the rule after dataset builds, and `ERROR` results can fail build jobs.

## Analytical Lens

When inspecting rules, explain what they imply:

- A rule with no latest result has not been computed for that partition, or DSS has no retained result.
- A disabled rule remains configured but is ignored by compute/status.
- `WARNING` may be an acceptable soft-threshold signal; `ERROR` usually means a hard-threshold failure and can break builds when `autoRun=true`.
- Drift rules need enough historical runs to be meaningful; a freshly created drift rule may not have a useful baseline.
