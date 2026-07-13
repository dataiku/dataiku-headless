---
name: connections
description: Understand and inspect Dataiku connections. Use to list configured connection names and types, select a suitable connection for a project asset, or diagnose connection access and test failures before a Cobuild change.
---

# Connections

Use this skill to inspect available Dataiku connections and gather grounded context for Cobuild.

## Connection Concepts

Connections are shared Dataiku configuration objects that provide access to storage systems, databases, LLM providers, remote services, and other external systems. A connection can be available on the instance but still be unsuitable or unavailable for a particular project or user.

When selecting a connection, consider its type, whether it supports the intended operation, and its project-specific usability. For example, a connection used for a managed dataset or managed folder must support that storage mode and any required write access.

## Workflow

1. Use `list_connections` to discover exact connection names. Do not infer names from defaults or memory.
2. When restricted discovery requires filtering, read [Connection Type Filters](references/connection-types.md) and use either `connection_type` or `connection_category`, never both.
3. Use `get_connection_info` on candidate connections before recommending or using one. Pass `contextual_project_key` when project variables or permissions may affect usability.
4. Use `test_connection` only when the user is diagnosing connectivity, permissions, or setup issues, or explicitly requests validation.
5. Recommend a connection based on its type, writeability, managed-dataset or folder support, project-specific usability, and any remaining uncertainty.
6. When a project asset must use the selected connection, route that asset change through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- Discover: `list_connections`
- Inspect: `get_connection_info`
- Validate: `test_connection`

## Safety Rules

- Discover connection names via tools; do not invent identifiers.
- Keep this skill read-only. Route project-asset changes that use a connection through `./dataiku-skills/cobuild/SKILL.md`.
- Do not expose or rely on secret-bearing fields; use the already-redacted inspection summaries.
- Do not repeat `test_connection` calls unless the user is actively debugging a connection issue.
- Do not choose a connection solely because it is configured as a default; inspect real candidates first.
