---
name: dataiku-headless
description: Use for Dataiku tasks including projects, flows, datasets, recipes, jobs, machine learning, agents, and Cobuild conversations. Choose the right reference guide, inspect state first, route project changes through Cobuild by default, and validate results after execution.
---

# Dataiku Headless

Use this for any Dataiku task. Choose the right reference guide first, inspect the current state before acting, route project changes through Cobuild by default, and validate by re-reading the resulting state.

## Shared Operating Rules

1. Just after installation, the plugin may still be getting ready. If its Dataiku tools are unavailable, run `uv --version` when local commands are available. If `uv` is missing or older than 0.12.0, explain that the plugin cannot start until uv is installed and on `PATH`; detect the platform, offer the official installer, and obtain explicit approval before running it. Otherwise, wait a minute, then restart the Codex or Claude app (or their agent) once before treating it as a Dataiku connection problem. Ask the user to run `uv --version` only when local commands are unavailable.
2. Ensure an instance is configured before any Dataiku work. If `get_current_instance` errors or `list_instances` is empty, run `configure_instance` first.
3. Discover project keys and object identifiers through tools; do not invent them.
4. Read before write. Inspect the current object, flow context, jobs, or run history before changing anything.
5. Treat the matching reference guide as the source of truth for object-specific concepts, inspection steps, and required references.
6. Route in-project asset creation and modification through `./references/cobuild.md` unless the matching guide documents a narrow direct exception.
7. Direct-write exceptions are allowed for operations that Cobuild cannot perform, especially bootstrap, cross-project, instance-level, or administrative actions. Treat them as narrow documented exceptions, not as the default mutation path.
8. Use visual recipes by default. A code recipe is appropriate only when the user explicitly requests a code-based transformation.
9. Preserve surrounding flow, storage, and operational context unless the user requests a change.
10. If MCP coverage is insufficient, stop and report the gap rather than falling back to raw Python, `dataikuapi`, or ad hoc REST calls.

## Default Workflow

1. Identify the target project and the user's main object of work.
2. Read the matching reference guide from the routing table below.
3. Follow that guide's inspection flow and read any references it explicitly requires.
4. If the task is read-only, answer from the inspected state.
5. If the task changes in-project assets, switch to `./references/cobuild.md` with grounded names, constraints, and context from the guide.
6. If the task is a documented direct-write exception, follow the matching guide's direct-write path instead of forcing it through Cobuild.
7. Keep the user's main object of work as the primary guide. Read supporting guides only when the primary guide tells you they are relevant.
8. For tasks that span multiple object types, keep one primary guide and read supporting guides for dependent objects or job/run follow-up.
9. Completion status is not enough. Validate by re-reading the changed object and using `./references/jobs.md` when execution may still be in progress.

## Guide Routing

| User intent | Guide to read next |
| --- | --- |
| Discover projects, inspect project metadata or variables, orient in a flow, or create a new project | `./references/projects.md` |
| Inspect or update project settings, including Flow display, pipelines, default code envs, or container execution | `./references/projects/settings.md` |
| Inspect the instance project-folder hierarchy or organize projects into project folders | `./references/project-folders.md` |
| Build, modify, or continue project-level work through Cobuild | `./references/cobuild.md` |
| Inspect datasets, schema, samples, or metrics; export a local CSV; or create an Uploaded Files dataset | `./references/datasets.md` |
| Inspect recipes, choose a recipe family, or ground a flow transformation | `./references/recipes.md` |
| Run an existing dataset or recipe, or track jobs, waits, and logs | `./references/jobs.md` |
| Inspect managed folders, create one on a chosen connection, or upload a user-supplied local file into one | `./references/managed_folders.md` |
| Inspect the project library or write one user-supplied local source file | `./references/project-libraries.md` |
| Inspect connections or choose a valid connection | `./references/connections.md` |
| Dataiku administrative tasks: (e.g. users, groups, code environments, general settings, etc.) | `./references/administration.md` |
| Inspect ML analyses, trained models, or saved models | `./references/machine-learning.md` |
| Inspect LLMs, Knowledge Banks, or RAG LLMs | `./references/llms-and-knowledge-banks.md` |
| Inspect agents or agent tools | `./references/agents.md` |
| Inspect Agent Reviews | `./references/agent-reviews.md` |
| Inspect dashboards | `./references/dashboards.md` |
| Inspect insights | `./references/insights.md` |
| Inspect scenarios and automation history, or run an existing scenario | `./references/scenarios.md` |
| Inspect semantic models | `./references/semantic-models.md` |
| Inspect WebApps and backend state | `./references/webapps.md` |
| Inspect wiki hierarchy or article content | `./references/wikis.md` |
| Inspect Data Quality rules and outcomes | `./references/data-quality.md` |
| Share a dataset from another project into the current project, or inspect cross-project sharing | `./references/cross-project-sharing.md` |
| Discover datasets through Data Collections | `./references/data-collections.md` |
| Port logic from Alteryx, SAS, Excel, or similar tools into Dataiku | `./references/migrations.md` |

## Routing Notes

- `./references/cobuild.md` is the default write path for in-project assets, but it should be grounded by the relevant guide first.
- Direct writes may grow over time for documented non-project, cross-project, instance-level, or administrative operations that Cobuild does not handle.
- `./references/jobs.md` is the follow-up guide after builds, runs, training, deployment, or other uncertain execution.
