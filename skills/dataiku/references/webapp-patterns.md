# Advanced Webapp Patterns

> Dataiku-specific patterns for building production webapps beyond the basics in `webapps.md`. Focuses on DSS integration points — assumes you already know Flask, React, Chart.js, etc.

**Source codebases:** genai_insights_dashboard, honeywell-regression, dataiku-mcp-gateway, agent-hub

---

## Architecture Tiers

| Tier | Defining DSS Feature | Example |
|------|---------------------|---------|
| **Simple** | 1-2 Flask routes, single `dataiku.Dataset()` | Config viewer |
| **Dashboard** | Multi-dataset lazy cache, `get_webapp_config()` params | genai_insights_dashboard |
| **SPA** | React/Vue built to `resource/dist/`, Vite single-bundle | honeywell-regression |
| **Platform** | SQLAlchemy + Alembic, DSS connection for DB URL, Socket.IO | agent-hub |

---

## Backend Patterns

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
