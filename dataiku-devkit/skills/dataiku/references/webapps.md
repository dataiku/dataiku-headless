# Dataiku Web Applications

Use this entrypoint to choose the right webapp reference. Detailed backend, frontend, and local development content lives in focused files.

## Type Selection

| Need | Read |
|---|---|
| Backend routes, DSS-injected Flask app, Socket.IO | `webapp-backends.md` |
| HTML/JS, Vue/Vite, Bokeh, Dash, Shiny frontend patterns | `webapp-frontends.md` |
| Local dev server, build/deploy, config access, troubleshooting | `webapp-local-dev-deploy.md` |
| Known traps and failure modes | `webapp-pitfalls.md` |
| Reusable frontend architecture patterns | `webapp-patterns.md` |

## Two Types of Webapps

| Type | Location | Use when |
|---|---|---|
| Standard project webapp | DSS project | Building a project-specific UI or dashboard |
| Plugin webapp | `webapps/<id>/` in a plugin | Shipping reusable UI as part of a plugin |

## Webapp Framework: DASH vs STANDARD

When building a webapp, choose the framework that fits the task:

| | `DASH` | `STANDARD` |
|---|---|---|
| **Best for** | Data-driven apps, charts, controls, filters, KPIs | Handcrafted HTML/CSS/JS, custom frontend logic |
| **Language** | Python (Dash components + callbacks) | HTML + CSS + JS, optional Python backend |
| **Output** | One `backend.py` file | `body.html`, `style.css`, `app.js`, optional `backend.py` |
| **Key constraint** | Uses the DSS-provided `app` object (do NOT call `app.run()` or create a second `Dash()` instance) | No framework constraints |

**Prefer `DASH` when:**
- The UI can be expressed with Dash components and callbacks
- The app is primarily Python/data-driven
- Charts, interactive exploration, or controls are central

**Prefer `STANDARD` when:**
- The user wants handcrafted HTML/CSS/JS with fine control
- The app doesn't need charts and is orthogonal to dashboard-building
- An existing STANDARD webapp needs extending

If both are viable, pick `DASH`. If in doubt, ask the user.

### Code Environment for Webapps

- `DASH` requires a code env with the `dash` package.
- `STANDARD` with a backend requires a code env with `Flask`.
- `STANDARD` without a backend has no code-env requirement.

Always set the code env explicitly instead of relying on defaults. See `code-environments.md` for code-env selection rules.

## Plugin Webapp Component Structure

```text
webapps/<webapp-id>/
├── webapp.json
├── backend.py
├── resource/
└── assets/
```

For `webapp.json` fields and parameter syntax, read `parameters.md` and the component examples in the focused references above.
