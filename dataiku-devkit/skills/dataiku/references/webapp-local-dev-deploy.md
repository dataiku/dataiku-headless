# Webapp Local Development and Deployment

Local development, build/deploy, frontend config access, and operational guidance for webapps.

## Local Development

### Plugin HTML/JS Webapp Dev Server

Running a plugin webapp locally requires replicating what DSS injects at runtime:

| DSS injects automatically | Must replicate for local dev |
|---|---|
| `getWebAppBackendUrl()` JS global | Inject via `<script>` into `body.html` |
| `style.css` and `app.js` | Serve as Flask static routes |
| Flask `app` instance for `@app.route` | Pass via `exec()` globals |
| `dataiku.customwebapp.get_webapp_config()` | Monkey-patch before exec |

### dev_server.py

```python
import builtins, os, sys, types
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, Response, send_file, jsonify, request

load_dotenv()

import dataiku
dataiku.set_remote_dss(os.environ["DKU_DSS_URL"], os.environ["DKU_API_KEY"])

def get_webapp_config():
    return {
        "my_param": os.environ["WEBAPP_MY_PARAM"],
        # mirror all webapp.json params
    }

# Monkey-patch BEFORE exec so backend.py's import gets the mock
try:
    import dataiku.customwebapp as _dku_webapp
    _dku_webapp.get_webapp_config = get_webapp_config
except (ImportError, AttributeError):
    _mod = types.ModuleType("dataiku.customwebapp")
    _mod.get_webapp_config = get_webapp_config
    sys.modules["dataiku.customwebapp"] = _mod
    dataiku.customwebapp = _mod  # type: ignore[attr-defined]

app = Flask(__name__)
WEBAPP_DIR = Path(__file__).parent / "webapps" / "my-webapp"

@app.route("/")
def index():
    html = (WEBAPP_DIR / "body.html").read_text()
    head_inject = (
        '<link rel="stylesheet" href="/style.css">\n'
        "<script>\n"
        "function getWebAppBackendUrl(path) { return 'http://localhost:5000/' + path; }\n"
        "</script>\n"
    )
    body_inject = '<script src="/app.js"></script>\n'
    html = html.replace("</head>", head_inject + "</head>")
    html = html.replace("</body>", body_inject + "</body>")
    return Response(html, mimetype="text/html")

@app.route("/app.js")
def serve_app_js():
    return send_file(WEBAPP_DIR / "app.js", mimetype="application/javascript")

@app.route("/style.css")
def serve_style_css():
    return send_file(WEBAPP_DIR / "style.css", mimetype="text/css")

# Inject `app` so @app.route decorators in backend.py register on our Flask instance.
_backend_globals = {"__builtins__": builtins, "app": app}
exec(compile((WEBAPP_DIR / "backend.py").read_text(), "backend.py", "exec"), _backend_globals)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

### Environment Variables for Local Dev

```env
DKU_DSS_URL="https://your-dss-instance.example.com/"
DKU_API_KEY="dkuaps-xxxx"
WEBAPP_MY_PARAM="value"
VITE_API_PORT=5000
VITE_CLIENT_PORT=3000
```

### Run

```bash
python dev_server.py
# open http://localhost:5000
```

**Notes:**
- No CORS needed — frontend and backend are served from the same Flask server.
- `dataiku.Dataset`, `dataiku.Folder`, `dataiku.api_client()` all hit real remote DSS — no mocking needed.
- `dataiku-internal-client` must be installed (fetch from your DSS instance, not PyPI).

---

## Build & Deploy (Vue/React Frontends)

### Makefile

```makefile
FRONTEND_DIR := resource/frontend
DIST_DIR := resource/dist

.PHONY: install build clean

install:
	cd $(FRONTEND_DIR) && npm ci

build: install
	cd $(FRONTEND_DIR) && npm run build
	rm -rf $(DIST_DIR)
	cp -r $(FRONTEND_DIR)/dist $(DIST_DIR)

clean:
	rm -rf $(DIST_DIR)
	rm -rf $(FRONTEND_DIR)/node_modules
	rm -rf $(FRONTEND_DIR)/dist
```

### Deployment Steps

1. Build frontend: `make build`
2. Verify `resource/dist/` contains built assets
3. Reload plugin in Dataiku UI
4. Create webapp instance from plugin

---

## Accessing Config in Frontend

### JavaScript (Standard Webapp)

```javascript
// Using Dataiku's built-in method
const config = dataiku.getWebAppConfig();
const dataset = config.input_dataset;
```

### Via API Endpoint

```typescript
// Fetch from backend
const config = await apiClient.getConfig();
```

### Python

```python
from dataiku.customwebapp import get_webapp_config
config = get_webapp_config()
dataset_name = config['input_dataset']
```

### R

```r
config <- dkuPluginConfig()
dataset_name <- config$input_dataset
```

---

## Advanced Features

### State Management (Client-Side)

```javascript
function saveState() {
    let state = {
        selectedColumn: currentColumn,
        colorScheme: currentScheme
    };
    localStorage.setItem('webapp_state', JSON.stringify(state));
}

function loadState() {
    let state = localStorage.getItem('webapp_state');
    if (state) {
        state = JSON.parse(state);
        currentColumn = state.selectedColumn;
        currentScheme = state.colorScheme;
    }
}
```

### Real-World Example: Interactive Map

**webapp.json:**
```json
{
  "meta": {
    "label": "Mapbox Visualization",
    "description": "Interactive map with dataset markers",
    "icon": "icon-map-marker"
  },
  "baseType": "STANDARD",
  "params": [
    {"name": "mapbox_token", "label": "Mapbox Access Token", "type": "STRING", "mandatory": true},
    {"name": "input_dataset", "label": "Dataset", "type": "DATASET", "mandatory": true},
    {"name": "lat_column", "label": "Latitude Column", "type": "COLUMN", "columnRole": "input_dataset", "mandatory": true},
    {"name": "lng_column", "label": "Longitude Column", "type": "COLUMN", "columnRole": "input_dataset", "mandatory": true},
    {"name": "center_lat", "label": "Map Center Latitude", "type": "DOUBLE", "defaultValue": 0},
    {"name": "center_lng", "label": "Map Center Longitude", "type": "DOUBLE", "defaultValue": 0},
    {"name": "zoom_level", "label": "Initial Zoom", "type": "INT", "defaultValue": 2}
  ]
}
```

---

## Best Practices

### Performance
- **Limit data loading** - Sample large datasets
- **Lazy loading** - Load data on demand
- **Caching** - Cache expensive computations in backend
- **Debouncing** - Delay updates on rapid input
- **Streaming** - Use Socket.IO for real-time updates instead of polling
- **Efficient rendering** - Update only changed elements

### User Experience
- **Loading indicators** - Show progress for async operations
- **Error messages** - Clear, actionable errors
- **Responsive design** - Work on different screen sizes
- **Intuitive controls** - Clear labeling
- **Help documentation** - Tooltips and guides
- **Refresh/reload** - Add refresh capabilities

### Security
- **Input validation** - Validate user inputs in backend
- **SQL injection prevention** - Parameterized queries
- **XSS prevention** - Sanitize outputs
- **Access control** - Check permissions
- **Credentials** - Use Dataiku connections, don't store in webapp

#### Per-User Impersonation

By default, webapp backends run as the DSS service account. To make API calls on behalf of the connected user (respecting their project/dataset permissions):

```python
from dataiku.customwebapp import get_webapp_config
from dataiku import WebappImpersonationContext
from flask import request, jsonify

@app.route("/api/data")
def get_user_data():
    # Resolve the calling user from DSS browser headers
    headers = dict(request.headers)
    auth = dataiku.api_client().get_auth_info_from_browser_headers(headers)
    user_login = auth["authIdentifier"]

    # All API calls inside this context run as `user_login`
    with WebappImpersonationContext(user_login):
        client = dataiku.api_client()
        project = client.get_default_project()
        ds = dataiku.Dataset("my_dataset")
        df = ds.get_dataframe(limit=100)

    return jsonify(df.to_dict(orient="records"))
```

**Why**: Without impersonation, the webapp can read datasets the user cannot — bypassing DSS row-level security and project permissions. Use impersonation whenever the webapp exposes user-specific or access-controlled data.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `/__ping` returns 404 (backend never ready) | **Do NOT create `app = Flask(__name__)`**. DSS provides `app` globally and registers `/__ping` on it. Creating your own app shadows the DSS one. |
| `module 'dataiku' has no attribute 'customwebapp'` | Same root cause — running outside DSS context. Remove `app = Flask(__name__)` and let DSS inject `app`. The `dataiku.customwebapp` module is only available inside DSS webapp runtime. |
| 404 on static assets | Verify `resource/dist/` path at plugin root level and asset references in `body.html` use `/plugins/{plugin-id}/resource/dist/assets/...` |
| CORS errors in development | Configure CORS in Flask: `CORS(app)` |
| Webapp not loading | Check browser console for JS errors, verify backend is running |
| Data not refreshing | Check API endpoints, verify Socket.IO connection |
| Config not available | Ensure `from dataiku.customwebapp import get_webapp_config` is used (not `dataiku.webapp`) |

### Common Mistakes

1. **Creating `app = Flask(__name__)`** — This is the #1 mistake. DSS provides `app`. Your code just decorates routes on it.
2. **Importing `Flask`** — You don't need it. Only import from `flask` what you use in routes: `jsonify`, `request`, etc.
3. **Wrong webapp folder name** — Plugin structure uses `webapps/` (not `custom-webapps/`). The `custom-webapps/` name is for project-level webapps only.
4. **Wrong config import** — Use `from dataiku.customwebapp import get_webapp_config`, NOT `dataiku.webapp.get_webapp_config()`.

## Quick Reference

**Get webapp config (JS):**
```javascript
let config = dataiku.getWebAppConfig();
let dataset = config['input_dataset'];
```

**Get webapp config (Python):**
```python
config = dataiku.customwebapp.get_webapp_config()
dataset_name = config['input_dataset']
```

**Get webapp config (R):**
```r
config <- dkuPluginConfig()
dataset_name <- config$input_dataset
```

**Load dataset (JS):**
```javascript
let dataset = dataiku.datasets.get(datasetName);
let data = await dataset.fetchSamples({limit: 10000});
```

**Load dataset (Python):**
```python
dataset = dataiku.Dataset(dataset_name)
df = dataset.get_dataframe(limit=10000)
```

**Convert webapp to plugin:**
```
Webapp Actions > Plugin > Convert to plugin webapp
```
