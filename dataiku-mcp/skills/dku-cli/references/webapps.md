# Reference: Webapps

Durable webapp detail: backend patterns, frontend setup, deploy, pitfalls.
CLI lifecycle (`dku webapp start/stop/logs/...`) lives in `playbooks/extensions-admin.md`.

## Types & frameworks

| Kind | Where | When |
|---|---|---|
| Project webapp | DSS project, 4-tab editor (HTML/CSS/JS/Python) | project-specific UI |
| Plugin webapp | `webapps/<id>/` in a plugin | reusable shipped UI |

Framework: **DASH** (Python, data/chart-driven, components+callbacks) vs **STANDARD**
(handcrafted HTML/CSS/JS, optional Flask backend). Prefer DASH for charts/exploration;
STANDARD for fine HTML control. Also BOKEH, STREAMLIT, SHINY. DASH needs a code env with
`dash`; STANDARD+backend needs `Flask`; STANDARD without backend needs none. Set the code
env explicitly. Create with `dku webapp create` (types above; `--from-plugin PLUGIN
--component ID` for a plugin-webapp instance); no API delete (405) — delete in the UI.

## Backend

**The rule:** in a **plugin** STANDARD/FastAPI webapp, DSS injects `app` globally and
registers `/__ping`. Never write `app = Flask(__name__)` / `app = FastAPI()` — it shadows
the DSS app and the backend never starts. Just decorate `@app.route(...)`. (Project-level
4-tab webapps DO define their own app.) Import config from `dataiku.customwebapp`
(NOT `dataiku.webapp`).

**DASH webapps:** DSS injects the app (Dash) object too. Attach `app.layout`/`@callback` to
the injected `app` — never `app = Dash(__name__)` and never `app.run()` (the stock Dash idiom
breaks the webapp). Single `backend.py`.

```python
from flask import request, jsonify
import dataiku
from dataiku.customwebapp import get_webapp_config
config = get_webapp_config()

@app.route("/api/data")          # plugin webapp: any path; project 4-tab: NO /api/ prefix
def get_data():
    ds = dataiku.Dataset(config["input_dataset"])   # name from config, never hardcoded
    return jsonify(ds.get_dataframe().to_dict(orient="records"))
```

**Production shape (Tier 3+):** one-liner `backend.py` → `setup_app(app)` in `python-lib/`
(with `# noqa: F821` on `app`). `setup_app` branches on `LOCAL_DEV`, registers Flask
Blueprints via `register_all_routes(app)`, installs a global error handler + request
logging hooks. Deferred imports inside the function prevent import-time crashes.

**Lazy data loading:** load datasets on first request (`@app.before_request` with a module
global), never at import time — datasets may not be built yet. Add a `/reload` endpoint if
data changes.

**Socket.IO:** `SocketIO(app, path="/stream")` for streaming. But DSS WSGI does **not**
support websockets in production → force `transports: ["polling"]` (websocket transport
yields `write() before start_response` 500s that kill the backend).

**Per-user impersonation:** by default the backend runs as the service account, bypassing
row-level security. Resolve the caller with
`api_client().get_auth_info_from_browser_headers(dict(request.headers))["authIdentifier"]`,
then wrap API calls in `with WebappImpersonationContext(user_login):`.

## Frontend

Call backends through `window.getWebAppBackendUrl('endpoint')` — DSS doesn't serve static
files or route `/api/` paths. Route names must match `@app.route`. In **plugin** webapps the
function is on the parent window:
`const getUrl = window.getWebAppBackendUrl || window.parent.getWebAppBackendUrl;`

**Project 4-tab editor:** structure in HTML tab (CDN `<link>`/`<script>` only — no local
file refs), raw CSS in CSS tab, raw JS in JS tab (DSS wraps them; don't add `<style>`/
`<script>`). Access config with `dataiku.getWebAppConfig()` / `dataiku.datasets.get(name)`.

**SPA (Vue/React + Vite):** source in `resource/frontend/`, build to `resource/dist/`.
`body.html` loads `/plugins/<id>/resource/dist/assets/index.{js,css}`. Validate DSS context
before fetching. Required Vite config:
```ts
build.rollupOptions.output = {
  entryFileNames: "assets/index.js",
  chunkFileNames: "assets/[name].js",
  assetFileNames: "assets/index.[ext]",   // single bundle — code-splitting breaks loading
};
base = mode === "production" ? "/plugins/my-plugin/resource/dist/" : "/";
```
Chart.js: `chart.destroy()` before recreating on the same canvas.

## webapp.json (plugin)

```json
{ "baseType": "STANDARD", "hasBackend": true, "noJSSecurity": true,
  "standardWebAppLibraries": ["dataiku"], "enableJavascriptModules": "true",
  "codeEnv": { "envMode": "PLUGIN_MANAGED" },
  "params": [ { "name": "main_dataset", "type": "DATASET" },
              { "name": "llm_id", "type": "LLM" } ] }
```
| Setting | Why |
|---|---|
| `hasBackend: true` | DSS provides Flask `app` |
| `noJSSecurity: true` | enables `getWebAppBackendUrl()` + cross-origin |
| `standardWebAppLibraries: ["dataiku"]` | injects `getWebAppBackendUrl` into frontend |
| `enableJavascriptModules` | ES module imports for SPA builds |
| `codeEnv: PLUGIN_MANAGED` | else backend runs on bare DSS Python (no deps) |

Dynamic params: `getChoicesFromPython: true` + `resource/params_helper.py do(payload,...)`
returning `{"choices":[...]}`, with `triggerParameters` for cascading. Note
`params_helper.py` runs on DSS **base** Python — don't import plugin deps there.

## Local dev

Plugin HTML/JS: a `dev_server.py` Flask app replicates what DSS injects — monkey-patch
`dataiku.customwebapp.get_webapp_config` **before** `exec`-ing `backend.py`, inject `app`
into exec globals, serve `app.js`/`style.css` as static routes, and inject a
`getWebAppBackendUrl` shim + `<link>`/`<script>` into `body.html`. Set
`dataiku.set_remote_dss(url, key)` so `dataiku.Dataset`/`api_client()` hit real DSS (no
mocking). Needs `dataiku-internal-client` (fetch from your DSS, not PyPI).

SPA: `wsgi.py` factory sets `LOCAL_DEV=true`, calls `setup_app`; Vite dev server runs
separately. `.env`: `DKU_API_URL`, `DKU_API_KEY`, `DKU_CURRENT_PROJECT_KEY`, `VITE_API_PORT`.

## Storage & persistence (plugin webapps)

Plugin install dir is **read-only** (`DKU_CUSTOM_RESOURCE_FOLDER` points there too). For
writable per-instance storage use
`from dataiku.core import workload_local_folder; workload_local_folder.get_workload_local_folder_path()`.
SQLAlchemy DB URL: resolve from a DSS connection
(`api_client().get_connection(name).get_definition()["params"]`); use `TABLES_PREFIX` env
var for multi-tenant isolation. In DSS use `db.create_all()` — **no Alembic subprocess**
(migration paths aren't present); Alembic-on-startup is for non-plugin deployments only.

## Pitfalls (fix)

| Symptom | Cause → fix |
|---|---|
| `/__ping` 404, backend never ready | `app = Flask(__name__)` defined → remove it, use injected `app` |
| `module 'dataiku' has no attribute 'customwebapp'` | running outside DSS / shadowed app → same fix |
| `Unexpected token '<'` in console | JS got HTML (404) — local file ref or `/api/` path → use `getWebAppBackendUrl`, move CSS/JS to tabs |
| API calls 404 in DSS only | `getWebAppBackendUrl` on `window.parent`, not `window` → check both |
| `IllegalStateException: no JavaScript file` | missing `app.js` (DSS requires it, even empty) + `meta.json` |
| Flask backend never served | `meta.json` must CONTAIN `{"backendEnabled": true}`, not just exist |
| backend missing deps | `codeEnv: PLUGIN_MANAGED` absent from webapp.json |
| random 404 on chunk files | Vite code-splitting / wrong `base` → single-bundle + plugin `base` path |
| Socket.IO 500 kills backend | websocket transport in DSS → polling only |
| `body.html`/`webapp.json` edits not taking effect | DSS caches aggressively → delete & recreate the webapp instance |
| `TypeError: unsupported operand type(s) for |` | DSS Python 3.9–3.11 → `from __future__ import annotations` |
| CDN fonts fail | air-gapped DSS → bundle fonts in `resource/dist/` |

The plugin id propagates into Vite `base`, `body.html` asset tags, socket config, zip name,
and code-env name (`plugin_<id>_managed`) — renaming it breaks several at once.
