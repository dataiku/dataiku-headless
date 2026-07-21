---
name: code-environments
description: Understand and inspect Dataiku code environments. Use when selecting an environment or diagnosing an environment-related issue before asking Cobuild to change a recipe, ML analysis, or code agent.
---

# Code Environments

Use this guide to inspect available Dataiku code environments and gather grounded context for Cobuild.

Apply the shared operating rules in `../SKILL.md` for routing, grounding, and validation.

## Code Environment Concepts

A code environment provides the language runtime and installed dependencies for code-based work, including Python, R, and PySpark recipes, ML analyses, and code agents.

An asset can use an explicitly selected environment, inherit a configured default, or use its language's built-in environment. Choose an explicit environment only when the user requests it or the task/error context establishes that it is needed.

Matching a workload's language does not establish package or runtime compatibility. Diagnose failures using error details and known requirements, and involve Cobuild or an administrator when the available context is insufficient.

## Workflow

1. Use `list_code_envs` to discover exact environment names and available languages.
2. Identify the affected workload's language and requirements from the relevant recipe, ML analysis, code agent, or error message.
3. Use the returned environment metadata to identify compatible candidates. Do not assume that a compatible language means a compatible dependency set.
4. For a requested change, include the exact environment name or intended selection behavior in a grounded Cobuild prompt.
5. Route recipe, ML analysis, and code-agent environment changes through `./cobuild.md`.

## Preferred Tools

- `list_code_envs`

## Safety Rules

- Do not select an explicit environment solely from a package or import error unless its compatibility is otherwise established.
