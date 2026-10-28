---
name: webapps
description: Understand and inspect Dataiku WebApps and their backend state, then use grounded context for Cobuild WebApp work. Use when reviewing an interactive application or planning a WebApp change.
---

# WebApps

Use this guide to understand existing WebApps and plan grounded application work through Cobuild.

## WebApp Concepts

A WebApp is an interactive application inside a Dataiku project. It can contain a user interface, framework-specific code, an optional backend runtime, and integrations with project objects.

The WebApp type determines its application framework and code structure. Persisted settings define the application; backend state is separate operational state used to diagnose availability, startup, and backend failures.

Creation, edits, backend restarts, and backend stops route through Cobuild. In Dataiku 15.1 and earlier, Cobuild creates and edits only `STANDARD`, `DASH`, and `STREAMLIT` WebApps. Headless writes `SHINY` WebApps directly; `BOKEH` WebApps can be inspected but not built.

| Type | Concept |
| --- | --- |
| `STANDARD` | General HTML, CSS, and JavaScript interface, optionally with a Python backend. |
| `DASH` | Python-driven interactive application using Dash. |
| `BOKEH` | Python interactive visualization application using Bokeh. Inspect only. |
| `SHINY` | R application with separate user-interface and server components. Written directly; see [Shiny WebApps](#shiny-webapps). |
| `STREAMLIT` | Python interactive application using Streamlit. |

Choose the framework that matches the requested application and existing project context. Choose `SHINY` only when the user explicitly asks for an R Shiny application. Backend availability is operational state; diagnose it separately from the persisted WebApp design.

## Shiny WebApps

A request for an interactive application, chart, or dashboard does not justify Shiny on its own. Use it only when the user explicitly asks for R Shiny.

Cobuild cannot create, edit, or start Shiny WebApps, so Headless writes them directly:

- Create with `create_shiny_webapp`, giving the `ui` and `server` R code.
- Inspect with `get_webapp_settings`, then replace `ui`, `server`, or both with `update_shiny_webapp`. Omitted code is kept.
- Both tools save the code and restart the backend. Check it with `get_webapp_state`, which reports a crashed backend's log tail.
- The backend needs `shiny`, and every package the code loads, in the project's R code environment. If the log reports one missing, find an R environment that has it with `list_code_envs` (`language` R, `packages`) and make it the project's default R environment with `update_project_settings`. If none has it, creating one changes the instance: confirm with the user first, then see `./administration/code-environments.md`.
- Delete through `./cobuild.md`.

## Workflow

1. Use `list_webapps` to discover WebApps and project-wide application context.
2. Use `get_webapp_settings` to inspect a selected WebApp's type and configuration.
3. Use `get_webapp_state` only when diagnosing availability, startup, or backend runtime issues.
4. Inspect referenced datasets, folders, models, APIs, code environments, and project-library files when they affect the requested change.
5. If the request only changes where the backend runs, use `./container-execution.md`. This is a narrow direct-write exception and does not require Cobuild.
6. Route all other WebApp creation, updates, backend restarts, and backend stops through `./cobuild.md`, except `SHINY`: use [Shiny WebApps](#shiny-webapps).
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
- `create_shiny_webapp` and `update_shiny_webapp`, for `SHINY` only

## Safety Rules

- Inspect a WebApp before requesting an update.
- Do not infer a WebApp's framework or backend requirements from its name.
- Treat backend restarts and stops as user-facing interruptions; request them only when explicitly needed.
- Do not expose secrets or unredacted runtime logs.
- Preserve existing framework-specific behavior unless the user requests a redesign.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Document direct WebApp mutation only for the `SHINY` exception.
