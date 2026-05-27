# Webapp Frontends

Frontend patterns for standard HTML/JS, Vue/Vite, Bokeh, Dash, and Shiny webapps.

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
