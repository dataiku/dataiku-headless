---
name: datasets
description: Inspect Dataiku datasets and use the results as grounding for Cobuild prompts. Use when an agent must discover dataset names, inspect schema, sample rows, profile distributions, or review metrics before asking Cobuild to create or modify project assets.
---

# Dataset Inspection

Use this skill to inspect datasets and gather context for Cobuild.

## Workflow

1. Use `list_datasets` to discover exact dataset names.
2. Use `get_dataset_info` for schema and storage details.
3. Use `get_dataset_profile` for distributions, null rates, and value frequencies.
4. Use `get_dataset_sample` when raw rows or formatting details matter.
5. Use `get_dataset_metrics` and `get_dataset_column_descriptions` when the user needs attached metadata or descriptions.
6. If the task requires creating, deleting, or modifying datasets, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`
- `get_dataset_metrics`
- `get_dataset_column_descriptions`

## Safety Rules

- Never invent dataset names.
- Inspect datasets directly before asking Cobuild to build from or modify them.
- Do not document direct dataset creation, update, or deletion workflows here.
