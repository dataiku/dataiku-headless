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

## Plugin Webapp Component Structure

```text
webapps/<webapp-id>/
├── webapp.json
├── backend.py
├── resource/
└── assets/
```

For `webapp.json` fields and parameter syntax, read `parameters.md` and the component examples in the focused references above.
