# Plugin Scaffolding & Lifecycle

Complete guide for creating, extending, deploying, and reviewing Dataiku plugins. Covers the full lifecycle from initial scaffold to production deployment.

---

## 1. Scaffold a New Plugin

### Gather Info

Ask the user for:
1. **Plugin directory name** — kebab-case (e.g., `my-new-plugin`)
2. **Plugin ID** — unique identifier (e.g., `my-new-plugin`)
3. **Label** — human-readable name (e.g., "My New Plugin")
4. **Description** — what the plugin does
5. **Category** — e.g., "Generative AI", "Data Quality", "Connectivity"
6. **Initial components** — which component types to scaffold (tools, recipes, webapps, guardrails)

### Generate Structure

Create the full plugin directory:

```
{plugin-name}/
├── plugin.json
├── python-lib/
│   └── {plugin_id_underscored}/       # e.g., my_new_plugin/
│       ├── __init__.py
│       ├── utils.py                   # Shared utilities
│       └── constants.py               # Configuration constants
├── code-env/
│   └── python/
│       ├── spec/
│       │   └── requirements.txt
│       └── desc.json
├── tests/
│   ├── conftest.py                    # See references/testing.md for mock patterns
│   ├── unit/
│   │   └── __init__.py
│   └── integration/
│       └── __init__.py
└── CHANGELOG.md
```

The `python-lib/{plugin_id_underscored}/` package is where core business logic lives. Keep Dataiku imports OUT of this package — it should be testable without DSS. Components (recipes, tools, etc.) import from here and act as thin wrappers.

### `plugin.json`

```json
{
  "id": "{plugin-id}",
  "version": "0.1.0",
  "meta": {
    "label": "{label}",
    "category": "{category}",
    "description": "{description}",
    "author": "Your Name",
    "icon": "fas fa-project-diagram",
    "tags": ["{category}"]
  }
}
```

### `code-env/python/desc.json`

**CRITICAL**: NEVER use `"installCorePackages": true` — the `LEGACY_PANDAS023` core set installs `pandas==0.23.4` which fails on Python 3.11+. The `PANDAS1` set also fails. Always use `installCorePackages: false` with explicit dependencies.

```json
{
  "acceptedPythonInterpreters": ["PYTHON312"],
  "forceConda": false,
  "installCorePackages": false,
  "installJupyterSupport": false
}
```

### `code-env/python/spec/requirements.txt`

The `dataiku` runtime imports numpy, pandas, and dateutil at module load — you MUST include them even if your plugin doesn't use them directly.

```
pandas>=2.0,<3
numpy>=1.22,<3
python-dateutil>=2.8,<3
requests>=2.28,<3
```

Add any additional dependencies your plugin needs below these base requirements.

### After Scaffolding

1. Add initial components using the templates in Section 2 below
2. Review the plugin structure against `references/plugin-structure.md` for completeness
3. Read `references/plugin-architecture.md` to pick the right tier (1-5) for your plugin
4. Deploy with `dku plugin push <plugin-dir>` when ready (see Section 3)

---

## 2. Add Components to a Plugin

For all components below, first locate the target plugin (look for directories containing `plugin.json`).

### 2.1 Agent Tool

**Gather info**: tool name (kebab-case), description, input parameters (name, type, required?)

Create at `{plugin}/python-agent-tools/{tool-name}/`:

#### `tool.json`

```json
{
  "meta": {
    "label": "{Tool Label}",
    "description": "{description}"
  },
  "params": [],
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

#### `tool.py`

```python
"""Agent Tool: {Tool Label}

{description}
"""

import logging
from dataiku.llm.agent_tools import BaseAgentTool

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = """{description}

When to use: ...
When NOT to use: ...
"""


class {ToolClassName}(BaseAgentTool):
    def get_descriptor(self, tool_config, trace):
        return {
            "description": TOOL_DESCRIPTION,
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    def set_config(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config

    def invoke(self, input, trace):
        args = input.get("input", {})
        # Validate inputs
        # Process request
        # Return result
        return {"output": "..."}
```

**Key patterns**: Put description in a `TOOL_DESCRIPTION` constant. Args are at `input.get("input", {})`, NOT at root of input dict. Return `{"output": "..."}` from invoke. Use `trace.attributes[key] = value` for observability (NOT `trace.set_attribute()`). See `references/llm-tools.md` for advanced patterns.

### 2.2 Custom Recipe

**Gather info**: recipe name (kebab-case), description, input roles (name, label, arity: UNARY/NARY), output roles, parameters (name, type, label)

Create at `{plugin}/custom-recipes/{recipe-name}/`:

#### `recipe.json`

```json
{
  "meta": {
    "label": "{Recipe Label}",
    "description": "{description}",
    "icon": "fas fa-cog"
  },
  "kind": "PYTHON",
  "inputRoles": [
    {
      "name": "input",
      "label": "Input Dataset",
      "arity": "UNARY",
      "acceptsDataset": true
    }
  ],
  "outputRoles": [
    {
      "name": "output",
      "label": "Output Dataset",
      "arity": "UNARY",
      "acceptsDataset": true
    }
  ],
  "params": []
}
```

#### `recipe.py`

```python
"""Recipe: {Recipe Label}

{description}
"""

import dataiku
from dataiku.customrecipe import get_recipe_config, get_input_names_for_role, get_output_names_for_role

# --- Configuration ---
config = get_recipe_config()
# Extract params...

# --- Input ---
input_dataset = dataiku.Dataset(get_input_names_for_role("input")[0])
df = input_dataset.get_dataframe()

# --- Processing ---
# TODO: implement recipe logic

# --- Output ---
output_dataset = dataiku.Dataset(get_output_names_for_role("output")[0])
output_dataset.write_with_schema(result_df)
```

See `references/recipes.md` for advanced patterns (NARY roles, managed folders, streaming).

### 2.3 Webapp

**Gather info**: webapp name (kebab-case), label, description, type (standard HTML/JS/CSS or Bokeh/Dash), needs backend?

#### Plugin Webapp Structure

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

#### Project-Level Webapp Structure

Create at `webapps/{webapp-name}/`:

```
webapps/{webapp-name}/
├── webapp.json
├── body.html
├── app.js
├── style.css
└── backend.py          # if backend needed
```

#### `webapp.json`

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

#### `backend.py`

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

#### Frontend

Call the backend from JavaScript:

```javascript
const backendUrl = window.getWebAppBackendUrl("/api/data");
fetch(backendUrl)
  .then(res => res.json())
  .then(data => { /* handle response */ });
```

See `references/webapps.md` for styling patterns and `references/webapp-pitfalls.md` for common mistakes. Note: no public API exists for webapp creation — webapps must be created via the DSS UI, then managed via `dku webapp start/stop/status`.

### 2.4 Guardrail

**Gather info**: guardrail name (kebab-case), description, configuration params, check scope (queries/responses/both)

Create at `{plugin}/python-guardrails/{guardrail-name}/`:

#### `guardrail.json`

```json
{
  "meta": {
    "label": "{Guardrail Label}",
    "description": "{description}"
  },
  "params": []
}
```

#### `guardrail.py`

```python
"""Guardrail: {Guardrail Label}

{description}
"""

import logging
from dataiku.llm.guardrails import BaseGuardrail

logger = logging.getLogger(__name__)


class {GuardrailClassName}(BaseGuardrail):
    def set_config(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config

    def process(self, input, trace):
        # Check queries (before LLM call)
        messages = input.get("completionQuery", {}).get("messages", [])
        if messages:
            with trace.subspan("check-query") as span:
                last_message = messages[-1].get("content", "")
                logger.info(f"[{GuardrailClassName}] Checking query: {last_message[:100]}...")

                # Raise an exception to block:  raise Exception("Query blocked: reason")
                # Modify to filter/rewrite:     input["completionQuery"]["messages"][-1]["content"] = filtered

                span.attributes["query_checked"] = True

        # Check responses (after LLM call)
        response_text = input.get("completionResponse", {}).get("text", "")
        if response_text:
            with trace.subspan("check-response") as span:
                logger.info(f"[{GuardrailClassName}] Checking response: {response_text[:100]}...")

                # Modify response:  input["completionResponse"]["text"] = filtered_response

                span.attributes["response_checked"] = True

        return input
```

Key guardrail patterns:
- Use `trace.subspan()` for observability (NOT `trace.set_attribute()`)
- Use `trace.attributes[key] = value` or `span.attributes[key] = value` to record results
- Raise exceptions to **block** queries (for security guardrails)
- Modify `input` dict to **filter** or **rewrite** content
- Always fail safely — block on error rather than allow through
- See `references/llm-mesh.md` for guardrail configuration and chaining

### After Adding Any Component

1. Format code: `ruff format {plugin}/{component-dir}/`
2. Show the user the generated files and ask if they want to adjust
3. Deploy with `dku plugin push {plugin}` when ready (see Section 3)

---

## 3. Deploy a Plugin

### Determine Plugin

Look for directories containing `plugin.json` in the current working directory. Read `plugin.json` to get the plugin ID and version.

### Verify Plugin Structure

Before deploying, check minimum required files:
- `plugin.json` — valid JSON with `id` and `version` fields
- `code-env/python/desc.json` — if the plugin has Python dependencies

### Deploy via dku CLI (Recommended)

```bash
# Push a plugin directory (auto-zips and uploads)
dku plugin push {plugin-directory}

# Push a pre-built zip file
dku plugin push {plugin-name}.zip

# Target a specific DSS instance
dku plugin push {plugin-directory} --profile my-instance
dku plugin push {plugin-directory} --url https://dss.example.com --api-key YOUR_KEY
```

The CLI detects whether the plugin already exists and calls the appropriate API (install or update).

### Create/Update Code Environment

After pushing:

```bash
dku code-env list                    # List existing code envs
```

For code environment creation via dataikuapi:

```python
import dataikuapi

client = dataikuapi.DSSClient("https://dss.example.com", api_key="YOUR_KEY")
plugin = client.get_plugin("your-plugin-id")

future = plugin.create_code_env()
result = future.wait_for_result()
```

**Cleanup on failure**: When `create_code_env()` fails, the broken env persists. Delete before retrying:

```python
ce = client.get_code_env("PYTHON", "code-env-name")
ce.delete()
future = plugin.create_code_env()
result = future.wait_for_result()
```

### Verify Deployment

```bash
dku plugin list                      # Confirm the plugin appears
dku plugin settings {plugin-id}      # Check plugin settings
```

### dataikuapi Fallback (Without dku CLI)

```python
import dataikuapi

client = dataikuapi.DSSClient("https://dss.example.com", api_key="YOUR_KEY")

# Install new plugin
with open("plugin.zip", "rb") as f:
    client.install_plugin_from_archive(f)

# Update existing plugin
plugin = client.get_plugin("plugin-id")
with open("plugin.zip", "rb") as f:
    plugin.update_from_zip(f)
```

**Important**: `install_plugin_from_archive()` fails if plugin directory already exists — use `update_from_zip()` instead. Both return `None` (not a future). ZIP must have `plugin.json` at root level.

### Building a Zip Manually

```bash
(cd {plugin-directory} && zip -r ../my-plugin.zip . -x "*.pyc" -x "__pycache__/*" -x ".git/*" -x "tests/*")
```

### Pre-Deploy Checklist

- Validate `plugin.json` is valid JSON
- Format code: `ruff check --fix . && ruff format .`
- Run tests: `pytest tests/`

---

## 4. Review a Plugin

**Preferred**: Spawn the `plugin-reviewer` agent for deep reviews — it has full tool access and produces scored reports with severity levels.

**Fallback** (if agent spawning is unavailable):

1. Determine plugin — look for directories containing `plugin.json`
2. Read all source files in the plugin directory
3. Check against `references/plugin-review-checklist.md` — apply every item
4. Run automated checks:
   ```bash
   ruff check {plugin-directory}
   ruff format --check {plugin-directory}
   ```
5. Report findings as a structured table:
   - **critical**: Runtime errors, security issues, data loss
   - **warning**: Confusion, maintenance burden, subtle bugs
   - **info**: Style, naming, minor improvements
6. Score the plugin /10 using the rubric in the checklist reference
