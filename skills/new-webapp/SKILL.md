---
name: new-webapp
description: Scaffold a Dataiku plugin webapp with Flask backend and frontend. Handles webapp.json, backend.py, and static resources.
disable-model-invocation: true
context: fork
---

Scaffold a new Dataiku plugin webapp.

## Gather Info

Ask the user for:
1. **Plugin** — which plugin to add the webapp to (look for directories containing `plugin.json`), or standalone project-level webapp
2. **Webapp name** — kebab-case directory name (e.g., `my-dashboard`)
3. **Label** — display name
4. **Description** — what the webapp does
5. **Type** — standard HTML/JS/CSS or Bokeh/Dash/Streamlit
6. **Needs backend?** — whether to include a Flask backend.py

## Generate Structure

### For plugin webapps

Create at `{plugin}/webapps/{webapp-name}/`:

```
{plugin}/webapps/{webapp-name}/
├── webapp.json
├── backend.py          # if backend needed
└── resource/
    ├── index.html
    ├── app.js
    └── style.css
```

### For project-level webapps

Create at `webapps/{webapp-name}/`:

```
webapps/{webapp-name}/
├── webapp.json
├── body.html
├── app.js
├── style.css
└── backend.py          # if backend needed
```

### `webapp.json`
```json
{
  "type": "STANDARD",
  "name": "{label}",
  "description": "{description}",
  "hasBackend": true,
  "noJSSecurity": true
}
```

Set `hasBackend` to `true` only if backend is needed. Set `noJSSecurity: true` when the frontend needs to call the backend API.

### `backend.py` (if needed)

**CRITICAL**: DSS injects `app` (Flask) into `backend.py` globally. NEVER create your own Flask app instance — it breaks the `/__ping` health check and the webapp will never start.

```python
"""Flask backend for {label} webapp."""

from dataiku.customwebapp import get_webapp_config
from flask import request, jsonify

# IMPORTANT: Do NOT create app = Flask(__name__)
# DSS provides the `app` variable automatically

@app.route("/api/data")
def get_data():
    """Fetch data for the webapp."""
    config = get_webapp_config()
    # TODO: implement
    return jsonify({"status": "ok"})
```

Key backend rules:
- Import from `dataiku.customwebapp` (NOT `dataiku.webapp`)
- Never instantiate `Flask(__name__)` — use the DSS-provided `app` directly
- The `app` variable is available in global scope without importing it

### Frontend

Reference `skills/dataiku/references/webapps.md` for styling patterns and Dataiku CSS variables.

For calling the backend from frontend JavaScript:
```javascript
// Get the backend URL prefix
const backendUrl = window.getWebAppBackendUrl("/api/data");
fetch(backendUrl)
  .then(res => res.json())
  .then(data => { /* handle response */ });
```

### `style.css`
Apply Dataiku-compatible styling. Reference `skills/dataiku/references/webapps.md` for colors, typography, and design tokens.

## Common Pitfalls

Reference `skills/dataiku/references/webapp-pitfalls.md` for a full list. The most critical ones:

1. **Never create `app = Flask(__name__)`** — breaks health check
2. **Import from `dataiku.customwebapp`** not `dataiku.webapp`
3. **Plugin webapp folder is `webapps/`** not `custom-webapps/`
4. **Frontend calls backend via `window.getWebAppBackendUrl("/api/path")`**
5. **No public API for webapp creation** — webapps must be created via the DSS UI, then managed via `dku webapp start/stop/status`

## After Generation

1. Format the Python code (e.g., `ruff format {plugin}/webapps/{webapp-name}/`)
2. Show the user the files and explain how to deploy via `dku plugin push {plugin}`
3. Remind them that webapps are created in DSS UI after the plugin is installed
