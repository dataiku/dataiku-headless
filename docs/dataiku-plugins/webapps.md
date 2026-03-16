# Webapp Development Guide

> Complete reference for building interactive dashboards and applications as Dataiku plugin components.

---

## Overview

Plugin webapps provide reusable, instantiable web applications within Dataiku. They combine:
- **Frontend**: HTML/JS, Vue, React, or other frameworks
- **Backend**: Python (Flask), Bokeh, Dash, Streamlit, or R Shiny
- **Integration**: Access to Dataiku datasets, APIs, and LLMs

---

## Folder Structure

```
custom-webapps/
└── my-webapp/
    ├── webapp.json           # Webapp descriptor (REQUIRED)
    ├── backend.py            # Python backend (Flask/standard)
    ├── app.py                # Alternative: Dash/Bokeh app
    └── resource/
        └── frontend/         # Frontend source (Vue, React, etc.)
            ├── package.json
            ├── src/
            └── dist/         # Built assets
```

For DSS to serve the frontend, copy built assets to `resource/dist/` at the plugin root level.

---

## webapp.json Reference

### Complete Template

```json
{
  "meta": {
    "label": "My Dashboard",
    "description": "Interactive dashboard for data visualization",
    "icon": "icon-dashboard",
    "iconColor": "blue"
  },
  "baseType": "STANDARD",
  "hasBackend": true,
  "noJSSecurity": true,
  "params": [
    {
      "name": "input_dataset",
      "type": "DATASET",
      "label": "Input Dataset",
      "description": "Dataset to visualize",
      "mandatory": true
    },
    {
      "name": "llm_id",
      "type": "LLM",
      "label": "LLM for Analysis",
      "llmUsagePurpose": "GENERIC_COMPLETION"
    },
    {
      "name": "refresh_interval",
      "type": "INT",
      "label": "Refresh Interval (seconds)",
      "defaultValue": 60,
      "minI": 10
    },
    {
      "name": "chart_type",
      "type": "SELECT",
      "label": "Default Chart Type",
      "selectChoices": [
        {"value": "line", "label": "Line Chart"},
        {"value": "bar", "label": "Bar Chart"},
        {"value": "scatter", "label": "Scatter Plot"}
      ],
      "defaultValue": "line"
    }
  ]
}
```

### Key webapp.json Fields

| Field | Type | Description |
|-------|------|-------------|
| `baseType` | string | App framework (see table below) |
| `hasBackend` | boolean | **Required for Flask backends.** Set `true` to enable `backend.py`. |
| `noJSSecurity` | boolean | Set `true` for React/Vue apps that load external JS from `resource/dist/`. Without this, DSS blocks script loading. |
| `params` | array | Webapp instance parameters (DATASET, STRING, INT, etc.) |

### baseType Options

| Type | Description | Files Required |
|------|-------------|----------------|
| `STANDARD` | HTML/JS with Python backend | `backend.py`, `body.html`, `app.js` (can be empty) |
| `BOKEH` | Bokeh server app | `backend.py` |
| `DASH` | Plotly Dash app | `app.py` |
| `STREAMLIT` | Streamlit app | `app.py` |
| `SHINY` | R Shiny app | `ui.R`, `server.R` |

---

## Standard Backend (Flask)

> **CRITICAL**: DSS injects a pre-configured `app` (Flask instance) into the global scope of `backend.py`.
> Do **NOT** create your own `app = Flask(__name__)` — this breaks DSS health checks (`/__ping`)
> and the `dataiku.customwebapp` module won't be available in your context.

### backend.py Template

```python
"""
My Dashboard Backend

Flask-based backend for the webapp.
DSS provides 'app' (Flask instance) in global scope — do NOT create your own.
"""
import json
import logging
from flask import request, jsonify
from concurrent.futures import ThreadPoolExecutor
import dataiku
from dataiku.customwebapp import get_webapp_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get webapp configuration (available because DSS injects the context)
webapp_config = get_webapp_config()
input_dataset = webapp_config.get("input_dataset")
llm_id = webapp_config.get("llm_id")

# 'app' is provided by DSS — just use @app.route() directly
# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=4)


@app.route("/api/data")
def get_data():
    """Fetch data from the configured dataset."""
    try:
        if not input_dataset:
            return jsonify({"error": "No dataset configured"}), 400

        ds = dataiku.Dataset(input_dataset)
        df = ds.get_dataframe()

        # Apply optional filters from query params
        limit = request.args.get("limit", type=int)
        if limit:
            df = df.head(limit)

        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": list(df.columns),
            "total": len(df)
        })
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyze data using LLM."""
    try:
        payload = request.get_json()
        query = payload.get("query", "")
        context = payload.get("context", "")

        if not llm_id:
            return jsonify({"error": "No LLM configured"}), 400

        client = dataiku.api_client()
        project = client.get_default_project()
        llm = project.get_llm(llm_id)

        completion = llm.new_completion()
        completion.with_message(f"Context: {context}\n\nQuery: {query}", role="user")
        response = completion.execute()

        return jsonify({
            "analysis": response.text,
            "model": llm_id
        })
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schema")
def get_schema():
    """Get dataset schema."""
    try:
        if not input_dataset:
            return jsonify({"error": "No dataset configured"}), 400

        ds = dataiku.Dataset(input_dataset)
        schema = ds.read_schema()

        return jsonify({"schema": schema})
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/config")
def get_config():
    """Return webapp configuration to frontend."""
    return jsonify({
        "dataset": input_dataset,
        "llm": llm_id,
        "refresh_interval": webapp_config.get("refresh_interval", 60),
        "chart_type": webapp_config.get("chart_type", "line")
    })
```

### Socket.IO for Real-Time Updates

```python
from flask_socketio import SocketIO, emit

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*", path="/stream")


@socketio.on("connect")
def handle_connect():
    logger.info("Client connected")
    emit("status", {"connected": True})


@socketio.on("subscribe")
def handle_subscribe(data):
    """Subscribe to data updates."""
    channel = data.get("channel", "default")
    # Add client to channel for updates
    emit("subscribed", {"channel": channel})


@socketio.on("query")
def handle_query(data):
    """Handle streaming LLM query."""
    query = data.get("query", "")

    try:
        client = dataiku.api_client()
        project = client.get_default_project()
        llm = project.get_llm(llm_id)

        completion = llm.new_completion()
        completion.with_message(query, role="user")

        # Stream response chunks
        for chunk in completion.execute_streamed():
            emit("response_chunk", {"text": chunk.text})

        emit("response_complete", {"status": "done"})
    except Exception as e:
        emit("error", {"message": str(e)})


@socketio.on("disconnect")
def handle_disconnect():
    logger.info("Client disconnected")
```

---

## Frontend Integration

### body.html Shell (Standard Webapp)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Dashboard</title>
    <link rel="stylesheet" href="/plugins/my-plugin/resource/dist/assets/index.css">
</head>
<body>
    <div id="app"></div>
    <script type="module" src="/plugins/my-plugin/resource/dist/assets/index.js"></script>
</body>
</html>
```

### Vue 3 + Vite Frontend Setup

```
resource/frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── api/
│   │   └── client.ts
│   ├── components/
│   └── views/
└── dist/                 # Build output
```

### package.json

```json
{
  "name": "my-webapp-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "pinia": "^2.1.0",
    "vue-router": "^4.2.0",
    "axios": "^1.6.0",
    "socket.io-client": "^4.7.0",
    "echarts": "^5.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vue-tsc": "^1.8.0",
    "tailwindcss": "^3.4.0"
  }
}
```

### API Client (TypeScript)

```typescript
// src/api/client.ts
import axios, { AxiosInstance } from 'axios';
import { io, Socket } from 'socket.io-client';

class ApiClient {
  private http: AxiosInstance;
  private socket: Socket | null = null;

  constructor() {
    // Determine base URL (works in both dev and DSS)
    const baseURL = import.meta.env.DEV
      ? `http://localhost:${import.meta.env.VITE_API_PORT}`
      : '';

    this.http = axios.create({
      baseURL,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // REST API methods
  async getData(limit?: number) {
    const params = limit ? { limit } : {};
    const response = await this.http.get('/api/data', { params });
    return response.data;
  }

  async getConfig() {
    const response = await this.http.get('/api/config');
    return response.data;
  }

  async analyze(query: string, context: string) {
    const response = await this.http.post('/api/analyze', { query, context });
    return response.data;
  }

  // WebSocket methods
  connectSocket() {
    const socketURL = import.meta.env.DEV
      ? `http://localhost:${import.meta.env.VITE_API_PORT}`
      : window.location.origin;

    this.socket = io(socketURL, { path: '/stream' });
    return this.socket;
  }

  getSocket() {
    return this.socket;
  }
}

export const apiClient = new ApiClient();
```

### Vue Component Example

```vue
<!-- src/components/DataChart.vue -->
<template>
  <div class="chart-container">
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else ref="chartRef" class="chart"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import * as echarts from 'echarts';
import { apiClient } from '@/api/client';

interface Props {
  chartType?: 'line' | 'bar' | 'scatter';
}

const props = withDefaults(defineProps<Props>(), {
  chartType: 'line'
});

const chartRef = ref<HTMLElement | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
let chart: echarts.ECharts | null = null;

async function loadData() {
  loading.value = true;
  error.value = null;

  try {
    const response = await apiClient.getData(1000);
    renderChart(response.data, response.columns);
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load data';
  } finally {
    loading.value = false;
  }
}

function renderChart(data: any[], columns: string[]) {
  if (!chartRef.value) return;

  if (!chart) {
    chart = echarts.init(chartRef.value);
  }

  const xColumn = columns[0];
  const yColumn = columns[1];

  const option = {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: data.map(row => row[xColumn])
    },
    yAxis: { type: 'value' },
    series: [{
      name: yColumn,
      type: props.chartType,
      data: data.map(row => row[yColumn])
    }]
  };

  chart.setOption(option);
}

onMounted(() => {
  loadData();
});

watch(() => props.chartType, () => {
  if (chart) {
    loadData();
  }
});
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 400px;
}
.chart {
  width: 100%;
  height: 100%;
}
</style>
```

---

## Dash Apps

### app.py for Dash

```python
"""
Dash-based webapp.
"""
import dash
from dash import dcc, html, Input, Output, callback
import plotly.express as px
import dataiku
from dataiku.customwebapp import get_webapp_config

# Get configuration
config = get_webapp_config()
input_dataset = config.get("input_dataset")

# Initialize Dash app
app = dash.Dash(__name__)

# Layout
app.layout = html.Div([
    html.H1("Data Dashboard"),

    dcc.Dropdown(
        id="column-selector",
        placeholder="Select column to visualize"
    ),

    dcc.Graph(id="main-chart"),

    dcc.Interval(
        id="refresh-interval",
        interval=config.get("refresh_interval", 60) * 1000,
        n_intervals=0
    )
])


@callback(
    Output("column-selector", "options"),
    Input("refresh-interval", "n_intervals")
)
def update_columns(_):
    """Update available columns from dataset."""
    if not input_dataset:
        return []

    ds = dataiku.Dataset(input_dataset)
    schema = ds.read_schema()

    return [{"label": col["name"], "value": col["name"]} for col in schema]


@callback(
    Output("main-chart", "figure"),
    Input("column-selector", "value"),
    Input("refresh-interval", "n_intervals")
)
def update_chart(column, _):
    """Update chart based on selected column."""
    if not input_dataset or not column:
        return {}

    ds = dataiku.Dataset(input_dataset)
    df = ds.get_dataframe()

    fig = px.histogram(df, x=column, title=f"Distribution of {column}")
    return fig
```

---

## Bokeh Apps

### backend.py for Bokeh

```python
"""
Bokeh-based webapp.
"""
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.layouts import column
from bokeh.io import curdoc
import dataiku
from dataiku.customwebapp import get_webapp_config

# Get configuration
config = get_webapp_config()
input_dataset = config.get("input_dataset")

# Load data
if input_dataset:
    ds = dataiku.Dataset(input_dataset)
    df = ds.get_dataframe()
    source = ColumnDataSource(df)
else:
    source = ColumnDataSource(data={"x": [], "y": []})

# Create figure
p = figure(title="Data Visualization", sizing_mode="stretch_width")
p.circle(x="x", y="y", source=source, size=10, alpha=0.6)

# Add to document
curdoc().add_root(column(p, sizing_mode="stretch_width"))
curdoc().title = "Bokeh Dashboard"
```

---

## Local Development Setup

### Environment Variables

Create `.env` in `resource/frontend/`:

```env
VITE_API_PORT=5000
VITE_CLIENT_PORT=3000
LOCAL_DEV=true
DKU_CURRENT_PROJECT_KEY=MY_PROJECT
```

### Backend Local Server

```python
# local_server.py (for development)
import os
import json
from flask import Flask

# Mock Dataiku imports for local development
os.environ["LOCAL_DEV"] = "true"

# Load local config
with open("local_config.json") as f:
    local_config = json.load(f)

# Monkey-patch get_webapp_config for local dev
import dataiku.customwebapp
dataiku.customwebapp.get_webapp_config = lambda: local_config

# Import and run backend
from backend import app, socketio

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
```

### local_config.json

```json
{
  "input_dataset": "MY_PROJECT.my_dataset",
  "llm_id": "openai:gpt-4",
  "refresh_interval": 30,
  "chart_type": "line"
}
```

---

## Build & Deploy

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

---

## Best Practices

### Performance
- **Lazy loading**: Only load data when needed
- **Pagination**: Limit initial data load, paginate large datasets
- **Caching**: Cache expensive computations in backend
- **Streaming**: Use Socket.IO for real-time updates instead of polling

### Security
- Validate all user input in backend
- Use Dataiku connections for credentials (don't store in webapp)
- Implement proper error handling without exposing internals

### User Experience
- Show loading states for async operations
- Provide clear error messages
- Support responsive layouts for different screen sizes
- Add refresh/reload capabilities

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `/__ping` returns 404 (backend never ready) | **Do NOT create `app = Flask(__name__)`**. DSS provides `app` globally and registers `/__ping` on it. Creating your own app shadows the DSS one. |
| `module 'dataiku' has no attribute 'customwebapp'` | Same root cause — you're running outside DSS context. Remove `app = Flask(__name__)` and let DSS inject `app`. The `dataiku.customwebapp` module is only available inside DSS webapp runtime. |
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
