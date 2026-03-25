# Advanced Webapp Patterns

> Dataiku-specific patterns for building production webapps beyond the basics in `webapps.md`. Focuses on DSS integration points — assumes you already know Flask, React, Chart.js, etc.

**Source codebases:** genai_insights_dashboard, honeywell-regression, dataiku-mcp-gateway, agent-hub, [`dss-plugin-semantic-models-lab`](https://github.com/dataiku/dss-plugin-semantic-models-lab)

---

## Architecture Tiers

| Tier | Defining DSS Feature | Example |
|------|---------------------|---------|
| **Simple** | 1-2 Flask routes, single `dataiku.Dataset()` | Config viewer |
| **Dashboard** | Multi-dataset lazy cache, `get_webapp_config()` params | genai_insights_dashboard |
| **SPA** | React/Vue built to `resource/dist/`, Vite single-bundle | honeywell-regression |
| **Platform** | SQLAlchemy + Alembic, DSS connection for DB URL, Socket.IO | agent-hub |
| **Agentic** | Blueprints, setup_app(), LangGraph, local dev mode | [semantic-models-lab](https://github.com/dataiku/dss-plugin-semantic-models-lab) |

---

## Backend Patterns

### One-Liner backend.py with setup_app() (Recommended)

The ideal pattern for production webapps. `backend.py` is a pure entry point — all logic lives in `python-lib/`:

```python
# webapps/my-webapp/backend.py
from my_plugin.setup import setup_app
setup_app(app)  # noqa: F821 - 'app' is injected by DSS
```

The `# noqa: F821` comment tells linters that `app` is a DSS-injected global — not an undefined variable.

**setup_app() in python-lib/**:

```python
# python-lib/my_plugin/setup.py
import logging
import os
from flask import Flask

def setup_app(app: Flask) -> None:
    is_local_dev = os.getenv("LOCAL_DEV", "").lower() == "true"

    if is_local_dev:
        from flask_cors import CORS
        from my_plugin.config import load_local_config
        CORS(app, resources={r"/api/*": {"origins": "*"}})
        load_local_config()
    else:
        from my_plugin.config import load_webapp_config
        load_webapp_config()

    # Register routes
    from my_plugin.routes import register_all_routes
    register_all_routes(app)

    # Configure logging
    from my_plugin.logging_utils import configure_logging, install_request_logging_hooks
    configure_logging()
    install_request_logging_hooks(app)
```

**Benefits:**
- All initialization logic testable (it's in `python-lib/`)
- Same `setup_app()` reused for local dev (`wsgi.py`) and DSS
- Imports are deferred inside the function — prevents import-time crashes
- Clear separation: DSS vs local dev path

### Flask Blueprints for Route Organization

For webapps with more than 3-4 routes, use Flask Blueprints instead of defining routes directly on `app`:

```python
# python-lib/my_plugin/routes/__init__.py
from flask import Flask
from my_plugin.routes import config, data, playground, resources
from my_plugin.routes.common import handle_error

def register_all_routes(app: Flask) -> None:
    app.register_error_handler(Exception, handle_error)
    app.register_blueprint(config.bp)
    app.register_blueprint(data.bp)
    app.register_blueprint(playground.bp)
    app.register_blueprint(resources.bp)
```

```python
# python-lib/my_plugin/routes/data.py
from flask import Blueprint, jsonify, request

bp = Blueprint("data", __name__, url_prefix="/api/data")

@bp.route("/query", methods=["POST"])
def query_data():
    payload = request.get_json()
    result = run_query(payload["question"])
    return jsonify(result)
```

```python
# python-lib/my_plugin/routes/common.py
import logging
import traceback
from flask import jsonify

logger = logging.getLogger(__name__)

def handle_error(error):
    """Global error handler for all blueprints."""
    logger.exception("Unhandled error: %s", error)
    return jsonify({"error": str(error)}), getattr(error, "code", 500)
```

---

### Local Development Mode

Run your webapp backend outside DSS for fast iteration. Requires a `wsgi.py` entry point:

```python
# wsgi.py (project root)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python-lib"))

from dotenv import load_dotenv
load_dotenv()

if not os.getenv("LOCAL_DEV"):
    os.environ["LOCAL_DEV"] = "true"

from flask import Flask
from my_plugin.setup import setup_app

def create_app() -> Flask:
    app = Flask(__name__)
    setup_app(app)
    return app

if __name__ == "__main__":
    port = int(os.getenv("VITE_API_PORT", "5000"))
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=True)
```

**.env file** for local development:
```
LOCAL_DEV=true
DKU_CURRENT_PROJECT_KEY=MY_PROJECT
DKU_API_URL=https://dss.example.com
DKU_API_KEY=your-api-key
DSS_DEV_USER=admin
VITE_API_PORT=5000
```

**Makefile** for development commands:
```makefile
setup:
	cd python-lib && pip install -e .
	cd resource/frontend && yarn install

backend-dev:
	python wsgi.py

frontend-dev:
	cd resource/frontend && yarn dev

backend-unit-tests:
	cd python-lib && pytest tests/ -v

check-all: backend-unit-tests
	cd python-lib && ruff check .
	cd resource/frontend && yarn test
```

**Key points:**
- `wsgi.py` sets `LOCAL_DEV=true` before importing plugin code
- `setup_app()` branches on `LOCAL_DEV` to enable CORS and load from `.env`
- Frontend dev server (Vite) runs separately and proxies API calls to Flask
- The `create_app()` factory pattern is standard Flask — works with `flask run` too

---

### Dataset Loading with Lazy Cache

Load datasets once on first request — not at import time (crashes if dataset isn't built yet).

```python
from dataiku.customwebapp import get_webapp_config
import dataiku

_df_main = None

@app.before_request
def ensure_data_loaded():
    global _df_main
    if _df_main is not None:
        return
    config = get_webapp_config()
    _df_main = dataiku.Dataset(config.get("main_dataset", "default_name")).get_dataframe()
```

**Gotcha:** Cache persists for webapp lifetime. Add a `/reload` endpoint if underlying data changes frequently.

### Config-Driven Dataset Names

Never hardcode. Use `webapp.json` DATASET params so admins can swap datasets without code.

```json
{
    "params": [
        { "name": "accounts_dataset", "type": "DATASET", "label": "Accounts Dataset" },
        { "name": "opportunities_dataset", "type": "DATASET", "label": "Opportunities" }
    ]
}
```

```python
config = get_webapp_config()
df = dataiku.Dataset(config["accounts_dataset"]).get_dataframe()
```

### Project Variable Storage (Mutable Config)

Plugin params are read-only at runtime. For config that changes (admin UIs, settings pages), use project variables:

```python
def get_config():
    project = dataiku.api_client().get_default_project()
    variables = project.get_variables()
    return variables.get("standard", {}).get("my_app_config", {})

def save_config(config):
    project = dataiku.api_client().get_default_project()
    variables = project.get_variables()
    variables.setdefault("standard", {})["my_app_config"] = config
    project.set_variables(variables)
```

### Multi-Dataset Aggregation Endpoints

Each tab/view gets its own endpoint returning a self-contained payload (`{ kpis, charts, tables }`). Frontend renders without additional computation. Separate `/filters` endpoint for populating dropdowns (called once on load from unfiltered data).

### Boolean & Numeric Normalization

DSS datasets have inconsistent boolean representations (`"true"`, `"1"`, `"yes"`, `True`, `1`). Normalize early:

```python
def to_bool_series(series):
    return series.astype(str).str.lower().isin(["true", "1", "yes"])
```

---

## Frontend Patterns

### DSS Context Check (Critical)

Every webapp frontend must validate it's running inside DSS before making API calls:

```typescript
// TypeScript (React/Vue SPA)
const getUrl = window.getWebAppBackendUrl;
if (!getUrl) throw new Error("Not running inside Dataiku DSS webapp context");
const data = await fetch(getUrl("/api/data")).then(r => r.json());
```

```javascript
// Vanilla JS
const backendUrl = window.getWebAppBackendUrl("");
fetch(`${backendUrl}/api/data`).then(r => r.json()).then(renderDashboard);
```

### Vite Single-Bundle Config (Required for DSS)

DSS serves webapp resources from a specific path. Code splitting creates unpredictable filenames that break resource loading. **Always use single-bundle output:**

```typescript
export default defineConfig({
    plugins: [react()],
    build: {
        rollupOptions: {
            output: {
                entryFileNames: "assets/index.js",
                chunkFileNames: "assets/[name].js",
                assetFileNames: "assets/index.[ext]",
            },
        },
    },
});
```

### Chart Lifecycle (Chart.js)

Destroy existing chart before re-creating on the same canvas — otherwise Chart.js throws "Canvas is already in use":

```javascript
if (chartCache[key]) chartCache[key].destroy();
chartCache[key] = new Chart(ctx, config);
```

### Tab Lazy Loading Pattern

For multi-tab dashboards, cache per tab and only fetch on first view:

```javascript
let tabDataCache = {};
function switchTab(tabNum) {
    // Show/hide DOM, then:
    if (!tabDataCache[tabNum]) loadTab(tabNum);
}
```

---

## webapp.json — Required Settings

```json
{
    "baseType": "STANDARD",
    "hasBackend": true,
    "noJSSecurity": true,
    "standardWebAppLibraries": ["dataiku"],
    "enableJavascriptModules": "true",
    "params": [
        { "name": "main_dataset", "type": "DATASET", "label": "Main Dataset" },
        { "name": "llm_id", "type": "LLM", "label": "LLM for Analysis" }
    ]
}
```

| Setting | Why Required |
|---------|-------------|
| `hasBackend: true` | DSS provides Flask `app` globally |
| `noJSSecurity: true` | Enables `getWebAppBackendUrl()` and cross-origin |
| `standardWebAppLibraries: ["dataiku"]` | Injects `getWebAppBackendUrl` into frontend JS |
| `enableJavascriptModules: "true"` | Required for ES module imports in SPA builds |

### Dynamic Webapp Parameters

For SELECTs populated from live DSS state (connections, folders, projects):

```json
{
    "name": "db_connection",
    "type": "SELECT",
    "getChoicesFromPython": true,
    "triggerParameters": ["storage_type"]
}
```

```python
# resource/params_helper.py
def do(payload, config, plugin_config, inputs):
    if payload.get("parameterName") == "db_connection":
        connections = dataiku.api_client().list_connections()
        return {"choices": [{"value": c, "label": c} for c in connections]}
```

`triggerParameters` re-fetches when `storage_type` changes.

---

## Platform Webapp Patterns (Tier 4-5)

### Database URL from DSS Connection

For webapps needing persistent storage, resolve DB URL from DSS connection config:

```python
def get_database_url(config):
    if config.get("storage_type") == "LOCAL":
        return f"sqlite:///{os.path.join(get_workload_folder(), 'data_store.db')}"

    conn = dataiku.api_client().get_connection(config["db_connection"])
    params = conn.get_definition()["params"]
    # Build URL per DB type (PostgreSQL, Snowflake, MySQL)
```

### Table Prefix for Multi-Tenant

Multiple deployments sharing one schema:

```python
TABLES_PREFIX = os.environ.get("TABLES_PREFIX", "")
class Conversation(db.Model):
    __tablename__ = f"{TABLES_PREFIX}conversations"
```

### Alembic Migrations on Startup

Run as subprocess to avoid circular imports with Flask app setup:

```python
# backend.py (DSS entry point)
run_alembic_upgrade()  # subprocess: alembic upgrade head
setup_app(app, db_url, workload_folder)
```

---

## Checklist

### Backend
- [ ] Uses DSS-injected `app` (NEVER `Flask(__name__)`)
- [ ] Imports from `dataiku.customwebapp` (NOT `dataiku.webapp`)
- [ ] Dataset names from `get_webapp_config()` (not hardcoded)
- [ ] Lazy dataset loading (not at import time)
- [ ] Error handling: try/except + `traceback.print_exc()` + JSON response

### Backend (Production — Tier 4-5)
- [ ] One-liner `backend.py` delegating to `setup_app(app)` in `python-lib/`
- [ ] Flask Blueprints for route organization (not all routes on `app`)
- [ ] `register_all_routes(app)` with global error handler
- [ ] Request logging hooks with timing and user resolution
- [ ] `# noqa: F821` comment on `app` reference for linters

### Local Development
- [ ] `wsgi.py` entry point with `create_app()` factory
- [ ] `LOCAL_DEV=true` env var branching in `setup_app()`
- [ ] CORS enabled for local dev only
- [ ] `.env` file with `DKU_CURRENT_PROJECT_KEY`, `DKU_API_URL`, `DKU_API_KEY`
- [ ] Makefile with `backend-dev`, `frontend-dev`, `check-all` targets

### Frontend
- [ ] Uses `window.getWebAppBackendUrl("/path")` for all API calls
- [ ] Checks DSS context before first fetch
- [ ] Charts destroyed before re-creation

### webapp.json
- [ ] `hasBackend: true`, `noJSSecurity: true`, `standardWebAppLibraries: ["dataiku"]`
- [ ] Dataset params typed as `"type": "DATASET"`

### React/Vite SPA
- [ ] Single-bundle output in vite.config.ts
- [ ] Build output to `resource/dist/`
