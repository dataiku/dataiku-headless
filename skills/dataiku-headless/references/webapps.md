---
name: webapps
description: Understand and inspect Dataiku WebApps and their backend state, then use grounded context for Cobuild WebApp work. Use when reviewing an interactive application or planning a WebApp change.
---

# WebApps

Use this guide to understand existing WebApps and plan grounded application work through Cobuild.

## WebApp Concepts

A WebApp is an interactive application inside a Dataiku project. It can contain a user interface, framework-specific code, an optional backend runtime, and integrations with project objects.

The WebApp type determines its application framework and code structure. Persisted settings define the application; backend state is separate operational state used to diagnose availability, startup, and backend failures.

Creation, edits, backend restarts, and backend stops route through Cobuild.

| Type | Concept |
| --- | --- |
| `STANDARD` | General HTML, CSS, and JavaScript interface, optionally with a Python backend. |
| `DASH` | Python-driven interactive application using Dash. |
| `BOKEH` | Python interactive visualization application using Bokeh. |
| `SHINY` | R application with separate user-interface and server components. |
| `STREAMLIT` | Python interactive application using Streamlit. |

Choose the framework that matches the requested application and existing project context. Backend availability is operational state; diagnose it separately from the persisted WebApp design.

## Workflow

1. Use `list_webapps` to discover WebApps and project-wide application context.
2. Use `get_webapp_settings` to inspect a selected WebApp's type and configuration.
3. Use `get_webapp_state` only when diagnosing availability, startup, or backend runtime issues.
4. Inspect referenced datasets, folders, models, APIs, code environments, and project-library files when they affect the requested change.
5. Route WebApp creation, updates, backend restarts, and backend stops through `./cobuild.md`.
6. Re-check backend state after a Cobuild backend action when application availability or backend behavior is relevant.

## Supporting Context

- Data and model integrations: `./datasets.md` and `./machine-learning.md`
- File integrations: `./managed_folders.md`
- Code environments: `./code-environments.md`
- Shared application source: `./project-libraries.md`
- External service connections: `./connections.md`

## Preferred Tools

- `list_webapps`
- `get_webapp_settings`
- `get_webapp_state`

## Safety Rules

- Inspect a WebApp before requesting an update.
- Do not infer a WebApp's framework or backend requirements from its name.
- Treat backend restarts and stops as user-facing interruptions; request them only when explicitly needed.
- Do not expose secrets or unredacted runtime logs.
- Preserve existing framework-specific behavior unless the user requests a redesign.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct WebApp mutation workflows here.
