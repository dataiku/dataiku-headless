# Dataiku Webapps — Critical Pitfalls & Correct Patterns

## The Three Critical Mistakes (Prevent First)

### 0. Defining `app` in a Plugin Webapp Backend

```python
# WRONG — Dataiku injects the Flask app instance; defining it yourself breaks routing
app = Flask(__name__)

@app.route('/filters')
def get_filters(): ...
```

In **plugin HTML/JS webapps**, the `app` Flask instance is injected by Dataiku's runtime. Never define it — just decorate with `@app.route()` directly:

```python
# CORRECT — app is already in scope, provided by Dataiku
from flask import jsonify, request
from dataiku.customwebapp import get_webapp_config

@app.route('/filters', methods=['GET'])
def get_filters():
    config = get_webapp_config()
    return jsonify({...})
```

This is **only** for plugin webapps (HTML/JS tab mode). Dash/Streamlit backends do define their own app object.

**FastAPI (DSS 14+):** The same rule applies — DSS injects the `app` object for FastAPI-based plugin webapps. Do NOT create `app = FastAPI()`.

---

### 1. Local File References in HTML Tab

```javascript
// WRONG — Will 404 and cause "Unexpected token '<'" error
<script src="dashboard.js"></script>
<link href="style.css" rel="stylesheet">
```

Dataiku doesn't serve static files. All four tabs (HTML, CSS, JS, Python) are **combined at runtime into a single page**. There is no file serving.

**What works:**
```html
<!-- CDN libraries work -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

<!-- Local files don't work -->
<link href="style.css" rel="stylesheet">         <!-- NO -->
<script src="dashboard.js"></script>              <!-- NO -->
```

### 2. Hardcoded API Paths

```javascript
// WRONG — Dataiku doesn't route /api/ paths
fetch('/api/filters')
fetch('/api/tab1/data')
```

Paired with wrong backend:
```python
# WRONG — /api/ prefix fails
@app.route('/api/filters')
@app.route('/api/tab1/data')
```

**What works:**
```javascript
// Use getWebAppBackendUrl() — Dataiku utility for routing
fetch(getWebAppBackendUrl('filters'))
fetch(getWebAppBackendUrl('tab1/data'))
```

Paired with correct backend:
```python
# No /api/ prefix
@app.route('/filters', methods=['GET'])
def get_filters():
    return jsonify({...})

@app.route('/tab1/data', methods=['GET'])
def tab1_data():
    return jsonify({...})
```

## Tab Architecture at a Glance

| Tab | Content | Don't Include |
|-----|---------|---------------|
| **HTML** | Page structure, CDN `<link>` & `<script>` only | Local file refs, `<style>` tags, inline scripts |
| **CSS** | Raw CSS rules, variables, @media | `<style>` wrapper, imports from local files |
| **JS** | Functions, listeners, initialization | `<script>` wrapper, imports from local files |
| **Python** | Flask app, @app.route(), data logic | External imports (use inline) |

Dataiku injects CSS as `<style>` and JS as `<script>` automatically. Don't wrap them yourself.

## Quick Start: Correct Structure

```html
<!-- HTML tab: Structure only -->
<!DOCTYPE html>
<html>
<head>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>
  <select id="filter"></select>
  <canvas id="chart"></canvas>
</body>
</html>
```

```css
/* CSS tab: Raw CSS only */
:root { --primary: #2ab1ac; }
body { font-family: sans-serif; margin: 20px; }
#chart { height: 300px; }
```

```javascript
// JS tab: Raw JavaScript only
async function loadFilters() {
  const data = await fetch(getWebAppBackendUrl('filters')).then(r => r.json());
  document.getElementById('filter').innerHTML =
    data.options.map(o => `<option>${o}</option>`).join('');
}

window.addEventListener('DOMContentLoaded', loadFilters);
```

```python
# Python tab: Flask backend
# NOTE: Project-level webapps (4-tab editor) define their own Flask app.
# Plugin webapps must NOT — DSS injects `app` automatically.
from flask import Flask, jsonify
import logging

app = Flask(__name__)  # Only in project-level webapps, NEVER in plugins
logger = logging.getLogger(__name__)

data_cache = None

@app.before_request
def before_request():
    """Load data on first request (Flask 2.3+ compatible)"""
    global data_cache
    if data_cache is None:
        logger.info("Loading data...")
        data_cache = load_data()

@app.route('/filters', methods=['GET'])
def get_filters():
    return jsonify({'options': ['Option1', 'Option2']})

@app.route('/tab1/data', methods=['GET'])
def tab1_data():
    return jsonify({'data': [...]})

def load_data():
    return {'processed': 'data'}
```

## Avoiding Common Errors

### "Unexpected token '<'" in Console?

JavaScript tried to parse HTML (404 response). Likely causes:

1. **Local file reference** -> `<script src="dashboard.js">` or `<link href="style.css">`
   - **Fix:** Remove local refs, move CSS to CSS tab, JS to JS tab

2. **Wrong routing path** -> `fetch('/api/filters')`
   - **Fix:** Use `fetch(getWebAppBackendUrl('filters'))`

3. **Empty tab** -> HTML, CSS, or JS tab is blank
   - **Fix:** Verify all four tabs have content

### 404 on `/filters` Endpoint?

Backend not responding. Check:

1. **Syntax error in Python** -> Check Dataiku logs for errors
2. **Route name mismatch** -> `fetch(getWebAppBackendUrl('filters'))` must match `@app.route('/filters')`
3. **Data loading** -> Verify `@app.before_request` exists and `data_cache` loads successfully

## Pre-Deployment Checklist

- [ ] No `<script src="...">` or `<link href="...">` for local files
- [ ] All four tabs have content (no empty HTML/CSS/JS/Python)
- [ ] JavaScript uses `getWebAppBackendUrl('endpoint')`
- [ ] Python routes have NO `/api/` prefix
- [ ] Route names match: `fetch(getWebAppBackendUrl('filters'))` <-> `@app.route('/filters')`
- [ ] CDN libraries in HTML tab (Bootstrap, Chart.js, etc.)
- [ ] `@app.before_request` exists to load data on startup
- [ ] Tested: Filters load, no console errors, tabs load data

## Summary

**Do:**
- Use `getWebAppBackendUrl('endpoint')` for all backend calls
- Put structure in HTML tab, styles in CSS tab, logic in JS tab
- Use CDN libraries (Bootstrap, Chart.js) via `<link>` in HTML
- Name routes simply: `/filters`, `/tab1/data` (no `/api/` prefix)
- Test all four tabs in browser before deploying

**Don't:**
- Reference local files (`dashboard.js`, `style.css`)
- Use hardcoded paths like `/api/filters` or `/filters` directly
- Wrap CSS in `<style>` or JS in `<script>` (Dataiku does it)
- Leave tabs empty
