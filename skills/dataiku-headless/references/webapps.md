---
name: webapps
description: Understand and inspect Dataiku WebApps and their backend state, then use grounded context for Cobuild WebApp work. Use when reviewing an interactive application or planning a WebApp change.
---

# WebApps

Use this guide to understand existing WebApps and plan grounded application work through Cobuild.

## WebApp Concepts

A WebApp is an interactive application inside a Dataiku project. It can contain a user interface, framework-specific code, an optional backend runtime, and integrations with project objects.

The WebApp type determines its application framework and code structure. Persisted settings define the application; backend state is separate operational state used to diagnose availability, startup, and backend failures.

Creation, edits, backend restarts, and backend stops route through Cobuild. As of Dataiku 15.1, Cobuild creates and edits only `STANDARD`, `DASH`, and `STREAMLIT` WebApps; `BOKEH` and `SHINY` WebApps can be inspected but not built through Cobuild.

| Type | Concept |
| --- | --- |
| `STANDARD` | General HTML, CSS, and JavaScript interface, optionally with a Python backend. |
| `DASH` | Python-driven interactive application using Dash. |
| `BOKEH` | Python interactive visualization application using Bokeh. Inspect only. |
| `SHINY` | R application with separate user-interface and server components. Inspect only; see [Shiny WebApps](#shiny-webapps). |
| `STREAMLIT` | Python interactive application using Streamlit. |

Choose the framework that matches the requested application and existing project context. Choose `SHINY` only when the user explicitly asks for an R Shiny application. Backend availability is operational state; diagnose it separately from the persisted WebApp design.

## Shiny WebApps

A request for an interactive application, chart, or dashboard does not justify Shiny on its own. Use it only when the user explicitly asks for R Shiny.

If the user still wants Shiny:

- Inspect an existing Shiny WebApp with `get_webapp_settings`, which returns its `ui` and `server` code, and with `get_webapp_state` for its backend.
- Do not send Shiny creation or edits to Cobuild, and do not fall back to raw APIs. Report the gap.
- Offer a `DASH` or `STREAMLIT` WebApp through Cobuild as the alternative, and build it only if the user agrees.

## Workflow

1. Use `list_webapps` to discover WebApps and project-wide application context.
2. Use `get_webapp_settings` to inspect a selected WebApp's type and configuration.
3. Use `get_webapp_state` only when diagnosing availability, startup, or backend runtime issues.
4. Inspect referenced datasets, folders, models, APIs, code environments, and project-library files when they affect the requested change.
5. If the request only changes where the backend runs, use `./container-execution.md`. This is a narrow direct-write exception and does not require Cobuild.
6. Route all other WebApp creation, updates, backend restarts, and backend stops through `./cobuild.md`. For a type Cobuild cannot build, report the gap instead.
7. Re-check backend state after a Cobuild backend action when application availability or backend behavior is relevant.

## Supporting Context

- Data and model integrations: `./datasets.md` and `./machine-learning.md`
- File integrations: `./managed_folders.md`
- Code environments: `./administration/code-environments.md`
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
