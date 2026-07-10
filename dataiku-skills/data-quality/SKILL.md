---
name: data-quality
description: Inspect Dataiku Data Quality rules and results. Use when an agent must discover existing rules, read rule outcomes, or understand quality status before asking Cobuild to modify project assets.
---

# Data Quality Inspection

Use this skill to inspect Data Quality rules and outcomes.

## Workflow

1. Use `list_data_quality_rules` to discover rules on a dataset.
2. Use `get_data_quality_status` for the current overall quality status.
3. Use `get_data_quality_rule`, `get_data_quality_rule_results`, and `get_data_quality_rule_history` for rule-specific details.
4. If the task requires creating, updating, computing, or deleting quality rules, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_data_quality_rules`
- `get_data_quality_status`
- `get_data_quality_rule`
- `get_data_quality_rule_results`
- `get_data_quality_rule_history`

## Safety Rules

- Inspect the dataset first with the dataset skill when rule context matters.
- Do not document direct Data Quality write workflows here.
