# Dataiku Web Applications

## Two Types of Webapps

Dataiku has two distinct webapp types — do not conflate them:

| | Project-level webapp | Plugin webapp |
|---|---|---|
| **Lives in** | A DSS project (under Webapps section) | A plugin (`plugins/my-plugin/webapps/`) |
| **Scope** | Project-specific | Reusable across projects |
| **Distribution** | Part of project export, or deployed via API | Packaged in plugin zip |
| **Accessed via** | `/webapps/PROJECTKEY/webappId` | Instantiated from plugin in any project |
| **Use when** | Building a one-off or project-specific app | Building a reusable, configurable component |

**Project-level webapps** are created directly in a DSS project under the Webapps section. They are standalone — not part of any plugin. To version-control them, maintain source files in a repo and deploy via `dataikuapi`.

**Plugin webapps** are packaged inside a plugin and distributed with it. The rest of this file documents plugin webapp components specifically.

---

## Plugin Webapp Overview

Webapp plugin components allow you to create reusable, configurable web applications that can be instantiated on datasets, folders, or standalone. They support multiple frameworks and provide seamless integration with Dataiku's data ecosystem.

### Supported Frameworks

- **HTML/JavaScript** - Full control with vanilla JS or libraries
- **Python Flask** - Standard REST API backend (DSS injects `app` in plugin webapps)
- **Python FastAPI** - Async REST API backend (DSS 14+, DSS injects `app` in plugin webapps)
- **Python Bokeh** - Interactive visualizations
- **Python Dash** - Reactive dashboards
- **Python Streamlit** - Rapid app development
- **R Shiny** - Interactive R applications

### Use Cases

- Custom data visualizations
- Interactive dashboards
- Data exploration tools
- Custom analytics interfaces
- Report generators
- Data entry forms

## Creating a Webapp Component

### From Existing Webapp

1. Create a regular webapp in a project
2. Go to Actions -> Plugin
3. Select "Convert to plugin webapp"
4. Choose target plugin
5. Provide identifier

### Component Structure

```
webapps/
└── my-webapp/
    ├── webapp.json       # Configuration (REQUIRED)
    ├── body.html         # HTML content (HTML/JS)
    ├── app.js            # JavaScript logic (HTML/JS)
    ├── style.css         # Styling (HTML/JS)
    ├── backend.py        # Python backend (Flask/Standard)
    ├── app.py            # Alternative: Dash/Bokeh/Streamlit app
    ├── server.R          # Server logic (R Shiny)
    ├── ui.R              # UI definition (R Shiny)
    └── resource/
        └── frontend/     # Frontend source (Vue, React, etc.)
            ├── package.json
            ├── src/
            └── dist/     # Built assets
```

For DSS to serve a compiled frontend, copy built assets to `resource/dist/` at the plugin root level.

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
  "backendAPIAccessEnabled": true,
  "enableJavascriptModules": "true",
  "standardWebAppLibraries": ["dataiku"],
  "codeEnv": {
    "envMode": "PLUGIN_MANAGED"
  },
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
| `hasBackend` | boolean/string | **Required for Flask backends.** Set `true` to enable `backend.py`. Note: some fields use string `"true"`, not boolean. |
| `noJSSecurity` | boolean/string | Set `true` for React/Vue apps that load external JS from `resource/dist/`. Without this, DSS blocks script loading. |
| `backendAPIAccessEnabled` | boolean | Allow backend to access the Dataiku API. |
| `enableJavascriptModules` | string | Set `"true"` to enable JS module imports. |
| `standardWebAppLibraries` | array | Set `["dataiku"]` to make `dataiku.getWebAppConfig()` and `getWebAppBackendUrl()` available in JS. |
| `codeEnv.envMode` | string | Set `"PLUGIN_MANAGED"` to use the plugin's own code env. |
| `params` | array | Webapp instance parameters (DATASET, STRING, INT, etc.) |

### baseType Options

| Type | Description | Files Required |
|------|-------------|----------------|
| `STANDARD` | HTML/JS with Python backend | `backend.py`, `body.html`, `app.js` (can be empty) |
| `BOKEH` | Bokeh server app | `backend.py` |
| `DASH` | Plotly Dash app | `app.py` |
| `STREAMLIT` | Streamlit app | `app.py` |
| `SHINY` | R Shiny app | `ui.R`, `server.R` |

### Parameter Types

- `DATASET` - Dataset selector
- `COLUMN` - Column from dataset
- `COLUMNS` - Multiple columns
- `STRING` - Text input
- `INT` - Integer input
- `DOUBLE` - Float input
- `BOOLEAN` - Checkbox
- `SELECT` - Dropdown
- `MULTISELECT` - Multiple selection
- `TEXTAREA` - Multi-line text
- `LLM` - LLM selector

---

## Standard Backend (Flask)

> **CRITICAL**: DSS injects a pre-configured `app` (Flask instance) into the global scope of `backend.py`.
> Do **NOT** create your own `app = Flask(__name__)` — this breaks DSS health checks (`/__ping`)
> and the `dataiku.customwebapp` module won't be available in your context.
> This applies only to plugin webapps (HTML/JS tab mode). Dash/Streamlit backends define their own app object.

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

## HTML/JavaScript Webapps (Vanilla JS)

### body.html

```html
<!DOCTYPE html>
<html>
<head>
    <title>Custom Visualization</title>
    <!-- Include libraries via CDN -->
    <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
    <div id="controls">
        <h2 id="plot-title"></h2>
        <div class="control-group">
            <label for="color-scale">Color Scale:</label>
            <select id="color-scale">
                <option value="viridis">Viridis</option>
                <option value="plasma">Plasma</option>
                <option value="inferno">Inferno</option>
            </select>
        </div>
    </div>

    <div id="visualization"></div>

    <script src="app.js"></script>
</body>
</html>
```

### app.js

```javascript
// Access webapp configuration
let config = dataiku.getWebAppConfig();

// Extract parameters
let datasetName = config['input_dataset'];
let xColumn = config['x_column'];
let yColumn = config['y_column'];
let colorColumn = config['color_column'];
let plotTitle = config['plot_title'];

// Set title
document.getElementById('plot-title').textContent = plotTitle;

// Load and visualize data
async function loadData() {
    try {
        let dataset = dataiku.datasets.get(datasetName);

        let data = await dataset.fetchSamples({
            limit: 10000
        });

        createScatterPlot(data);
    } catch (error) {
        console.error('Error loading data:', error);
        document.getElementById('visualization').innerHTML =
            '<p class="error">Error loading data: ' + error.message + '</p>';
    }
}

function createScatterPlot(data) {
    const margin = {top: 20, right: 20, bottom: 50, left: 50};
    const width = 800 - margin.left - margin.right;
    const height = 600 - margin.top - margin.bottom;

    const svg = d3.select('#visualization')
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    const xScale = d3.scaleLinear()
        .domain(d3.extent(data, d => d[xColumn]))
        .range([0, width]);

    const yScale = d3.scaleLinear()
        .domain(d3.extent(data, d => d[yColumn]))
        .range([height, 0]);

    const colorScale = d3.scaleOrdinal(d3.schemeCategory10);

    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale));

    svg.append('g')
        .call(d3.axisLeft(yScale));

    svg.selectAll('circle')
        .data(data)
        .enter()
        .append('circle')
        .attr('cx', d => xScale(d[xColumn]))
        .attr('cy', d => yScale(d[yColumn]))
        .attr('r', 5)
        .attr('fill', d => colorColumn ? colorScale(d[colorColumn]) : 'steelblue')
        .attr('opacity', 0.7);
}

loadData();
```

---

## Python Bokeh Webapps

### backend.py

```python
from bokeh.plotting import figure
from bokeh.models import HoverTool, ColumnDataSource
from bokeh.layouts import column, row
from bokeh.io import curdoc
import dataiku
from dataiku.customwebapp import get_webapp_config

config = get_webapp_config()

dataset_name = config['input_dataset']
x_column = config['x_column']
y_column = config['y_column']
color_column = config.get('color_column')
plot_title = config.get('plot_title', 'Scatter Plot')

dataset = dataiku.Dataset(dataset_name)
df = dataset.get_dataframe(limit=10000)

source = ColumnDataSource(df)

p = figure(
    title=plot_title,
    x_axis_label=x_column,
    y_axis_label=y_column,
    width=800,
    height=600,
    tools='pan,wheel_zoom,box_zoom,reset,save'
)

if color_column and color_column in df.columns:
    from bokeh.transform import factor_cmap
    categories = df[color_column].unique()

    scatter = p.circle(
        x=x_column, y=y_column, source=source,
        size=8, alpha=0.7,
        color=factor_cmap(color_column, 'Category10_10', categories),
        legend_field=color_column
    )
else:
    scatter = p.circle(
        x=x_column, y=y_column, source=source,
        size=8, alpha=0.7, color='steelblue'
    )

hover = HoverTool(tooltips=[
    (x_column, f'@{{{x_column}}}'),
    (y_column, f'@{{{y_column}}}')
])
if color_column:
    hover.tooltips.append((color_column, f'@{{{color_column}}}'))

p.add_tools(hover)

if color_column:
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"

# Add to document
curdoc().add_root(column(p, sizing_mode="stretch_width"))
curdoc().title = plot_title
```

---

## Python Dash Webapps

### app.py

```python
import dash
from dash import dcc, html, Input, Output, callback
import plotly.express as px
import dataiku
from dataiku.customwebapp import get_webapp_config

config = get_webapp_config()
input_dataset = config.get("input_dataset")

app = dash.Dash(__name__)

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
    if not input_dataset or not column:
        return {}

    ds = dataiku.Dataset(input_dataset)
    df = ds.get_dataframe()

    fig = px.histogram(df, x=column, title=f"Distribution of {column}")
    return fig
```

---

## R Shiny Webapps

### server.R

```r
library(shiny)
library(ggplot2)
library(dataiku)

config <- dkuPluginConfig()

dataset_name <- config$input_dataset
x_column <- config$x_column
y_column <- config$y_column
color_column <- config$color_column
plot_title <- config$plot_title

dataset <- dkuReadDataset(dataset_name)
df <- dataset$get_dataframe(limit = 10000)

function(input, output, session) {
    filtered_data <- reactive({
        data <- df
        if (input$show_outliers == FALSE) {
            q <- quantile(data[[y_column]], c(0.25, 0.75), na.rm = TRUE)
            iqr <- q[2] - q[1]
            lower <- q[1] - 1.5 * iqr
            upper <- q[2] + 1.5 * iqr
            data <- data[data[[y_column]] >= lower & data[[y_column]] <= upper, ]
        }
        data
    })

    output$main_plot <- renderPlot({
        data <- filtered_data()
        p <- ggplot(data, aes_string(x = x_column, y = y_column))
        if (!is.null(color_column) && color_column != "") {
            p <- p + geom_point(aes_string(color = color_column), size = 3, alpha = 0.7)
        } else {
            p <- p + geom_point(color = "steelblue", size = 3, alpha = 0.7)
        }
        p <- p + labs(title = plot_title, x = x_column, y = y_column) +
            theme_minimal() +
            theme(plot.title = element_text(size = 16, hjust = 0.5),
                  axis.title = element_text(size = 12))
        if (input$add_smooth) {
            p <- p + geom_smooth(method = "lm", se = TRUE, color = "red")
        }
        p
    })

    output$summary <- renderPrint({
        data <- filtered_data()
        summary(data[[y_column]])
    })
}
```

### ui.R

```r
library(shiny)

config <- dkuPluginConfig()
plot_title <- config$plot_title

fluidPage(
    titlePanel(plot_title),
    sidebarLayout(
        sidebarPanel(
            checkboxInput("show_outliers", "Show Outliers", value = TRUE),
            checkboxInput("add_smooth", "Add Trend Line", value = FALSE),
            hr(),
            h4("Summary Statistics"),
            verbatimTextOutput("summary")
        ),
        mainPanel(
            plotOutput("main_plot", height = "600px")
        )
    )
)
```

---

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
