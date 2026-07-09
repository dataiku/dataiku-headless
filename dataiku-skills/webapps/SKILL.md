---
name: webapps
description: Create, inspect, update, and operate Dataiku WebApps through MCP tools. Use when an agent must create WebApps, list them, inspect settings, replace settings safely, or start/stop backends.
---

# WebApp Operations

Use Dataiku MCP tools to inspect and operate WebApps safely.

This skill covers native code WebApp creation, discovery, full-settings round-trip edits, and backend lifecycle actions. WebApp deletion is not supported via MCP tools.

## What Are WebApps?

WebApps are interactive application surfaces inside DSS. Depending on the WebApp type, the main code and configuration live in different keys under `params`.

Common WebApp types include:
- `STANDARD`
- `DASH`
- `BOKEH`
- `SHINY`
- `STREAMLIT`

## Follow This Execution Pattern

1. Orient in the project when needed with `get_flow_items_in_traversal_order`. If the relevant datasets, models, or APIs are already clearly identified, you may skip broad flow discovery and go straight to the specific objects the WebApp will reference.
2. If creating a new WebApp, call `create_webapp` with the requested name and one supported native type: `STANDARD`, `BOKEH`, `DASH`, `STREAMLIT`, or `SHINY`.
3. Call `list_webapps` to discover exact WebApp ids, types, and backend status when you still need the id, or when you want project-wide WebApp context.
4. Before any edit, inspect the current full settings dict. For existing WebApps, call `get_webapp_settings`. Always review [WebApp settings structure reference](references/webapp_settings_structure_reference.md) before editing a WebApp.
5. Announce the intended action in one sentence.
6. For edits, modify only the necessary fields, then call `set_webapp_settings` with the full settings dict. Treat this as a full replace.
7. For runtime operations, call `get_webapp_state` before and after `restart_webapp_backend` or `stop_webapp_backend`.

## Settings Rules

- `create_webapp` creates only native code WebApps and seeds a DSS-generated default settings object for the selected type.
- After creating a WebApp, inspect it with `get_webapp_settings` before making any non-trivial changes to `params`.
- `get_webapp_settings` returns the full settings dict for round-trip editing.
- Sensitive top-level fields such as `apiKey` may be redacted as `__DATAIKU_REDACTED__`.
- When calling `set_webapp_settings`, omitted redacted sensitive fields are preserved automatically from the current live settings.
- `params` is strongly type-specific. Do not guess nested `params` structure from memory.
- `get_webapp_state` may include recent backend log tails such as `currentLogTail` or `lastCrashLogTail`. These are tails, not guaranteed full logs.
- `restart_webapp_backend` returns the restart action future id. This may differ from `state.futureId` returned later by `get_webapp_state`.
- Always round-trip through `get_webapp_settings` first, then edit the returned dict.
- Preserve unknown fields unless the user explicitly wants them changed.
- Review [WebApp settings structure reference](references/webapp_settings_structure_reference.md) when editing a WebApp.

## Type-Specific Guidance

Common `params` differences by type:

- `STANDARD`: typically uses `html`, `css`, `js`, `python`, plus backend/runtime fields
- `DASH`: typically uses `python`, `serveLocally`, and backend/runtime fields
- `BOKEH`: typically uses `python` and runtime fields
- `SHINY`: typically uses `ui` and `server`
- `STREAMLIT`: typically uses `python` and `config`

The exact `params` shape may also vary with:
- `envSelection`
- `containerSelection`
- `infra.exposition`
- `backendEnabled`
- `backendAPIAccessEnabled`
- `forceAuthentication`

Inspect the live object before editing. Do not synthesize a new `params` block from scratch.

## Preferred Tools

- Create: `create_webapp`
- Discover: `list_webapps`
- Inspect settings: `get_webapp_settings`
- Replace settings: `set_webapp_settings`
- Inspect runtime: `get_webapp_state`
- Restart backend: `restart_webapp_backend`
- Stop backend: `stop_webapp_backend`

## Safety Rules

- Use `create_webapp` to create a new native WebApp. Do not try to synthesize a brand-new WebApp object via `set_webapp_settings`.
- Supported creation types are `STANDARD`, `BOKEH`, `DASH`, `STREAMLIT`, and `SHINY`.
- Never invent WebApp ids; discover them with `list_webapps`.
- `set_webapp_settings` is a full replace. Always round-trip through `get_webapp_settings` first.
- Do not remove or rewrite type-specific fields unless the user explicitly wants them changed.
- Treat backend restarts and stops as real runtime mutations. Confirm with the user before interrupting a running app unless they explicitly asked for it.
- WebApp settings may include sensitive fields. Do not expose secrets in output, logs, or examples.
