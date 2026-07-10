---
name: code-environments
description: Discover Dataiku DSS code environments and use that information as supporting context for Cobuild prompts. Use when an agent must find exact environment names or diagnose environment-related issues before asking Cobuild to modify a recipe or ML analysis.
---

# Code Environments

Use this skill to inspect available code environments only.

## Workflow

1. Call `list_code_envs` to discover exact environment names.
2. Use the returned language and deployment details to recommend an environment when needed.
3. If the task requires changing a recipe or ML analysis to use a different environment, route that change through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_code_envs`

## Safety Rules

- Never invent a code environment name.
- Do not document direct recipe or ML code-environment mutation workflows here.
