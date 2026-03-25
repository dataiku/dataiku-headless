# Plugin Structure & Anatomy

> Complete reference for Dataiku plugin folder structure, plugin.json configuration, and packaging requirements.

---

## Quick Start

Dataiku DSS plugins are self-contained packages that extend the platform with custom components. Each plugin follows a standardized folder structure and is described by a mandatory `plugin.json` manifest.

### Component Quick Reference

| Component Type | Folder | Config File | Code File | Use Case |
|---------------|--------|-------------|-----------|----------|
| Recipes | `custom-recipes/` | `recipe.json` | `recipe.py` | Data transformations |
| Datasets | `python-connectors/` | `connector.json` | `connector.py` | External data sources |
| Webapps | `webapps/` | `webapp.json` | `backend.py` | Interactive UIs |
| Macros | `python-runnables/` | `runnable.json` | `runnable.py` | One-click utilities |
| LLM Tools | `python-agent-tools/` | `tool.json` | `tool.py` | Agent capabilities |
| Custom Agents | `python-agents/` | `agent.json` | `agent.py` | Full LLM agents |
| Guardrails | `python-guardrails/` | `guardrail.json` | `guardrail.py` | LLM safety controls |
| Visual Agent Blocks | `python-blocks-graph-blocks/` | `block.json` | `block.py` | Structured agent blocks (DSS 14+) |
| File Formats | `python-formats/` | `format.json` | `format.py` | Custom file extractors/exporters |
| Filesystem Providers | `python-fs-providers/` | `fsprovider.json` | `fsprovider.py` | Custom storage backends |
| Metric Probes | `python-probes/` | `probe.json` | `probe.py` | Custom dataset/model metrics |
| Checks | `python-checks/` | `check.json` | `check.py` | Data quality checks |
| Scenario Steps | `python-steps/` | `step.json` | `step.py` | Custom automation steps |
| Scenario Triggers | `python-triggers/` | `trigger.json` | `trigger.py` | Custom automation triggers |
| Parameter Sets | `parameter-sets/` | `parameterset.json` | — | Reusable parameter groups |

### Common Development Tasks

**Creating a New Recipe:**
1. Create folder: `custom-recipes/my-recipe/`
2. Add `recipe.json` with meta, inputRoles, outputRoles, params
3. Add `recipe.py` with transformation logic

**Adding a Webapp Dashboard:**
1. Create folder: `webapps/my-webapp/`
2. Add `webapp.json` with parameters
3. Add `backend.py` (Flask) or framework-specific files
4. Build frontend to `resource/dist/`

**Extending LLM Agents:**
1. Create folder: `python-agent-tools/my-tool/`
2. Add `tool.json` with inputSchema
3. Add `tool.py` extending `BaseAgentTool`

### Version Compatibility

This documentation is based on **Dataiku DSS 14** (2024-2025). Key features by version:
- **DSS 14+**: Visual Agent Blocks, FastAPI webapps, A2A Server
- **DSS 14.1+**: Knowledge Banks as recipe inputs (`acceptsKnowledgeBank`)
- **DSS 13+**: LLM Mesh, Agent Tools, Custom Agents
- **DSS 12+**: Enhanced webapp frameworks (Dash, Streamlit)

### Plugin Management API

**Dev plugin file management** (dev plugins only):
```python
plugin = client.get_plugin("my-plugin")
plugin.list_files()                      # List all files
plugin.get_file("python-lib/utils.py")   # Read file contents
plugin.put_file("python-lib/utils.py", f) # Write file
plugin.rename_file("old.py", "new.py")   # Rename
plugin.move_file("a/b.py", "c/b.py")    # Move
```

**Check usages before deletion:**
```python
usages = plugin.list_usages()  # Find all projects using this plugin
if usages:
    print(f"Plugin in use by: {[u['projectKey'] for u in usages]}")
else:
    plugin.delete()
```

### Official Documentation Links

| Resource | URL |
|----------|-----|
| Plugin Overview | https://doc.dataiku.com/dss/latest/plugins/index.html |
| Plugin Components | https://doc.dataiku.com/dss/latest/plugins/reference/plugins-components.html |
| Recipe Reference | https://doc.dataiku.com/dss/latest/plugins/reference/recipes.html |
| Parameters Reference | https://doc.dataiku.com/dss/latest/plugins/reference/params.html |
| Webapp Reference | https://doc.dataiku.com/dss/latest/plugins/reference/webapps.html |
| Developer Guide | https://developer.dataiku.com/latest/concepts-and-examples/plugins/index.html |
| Plugin Template (GitHub) | https://github.com/dataiku/dss-plugin-template |
| Community Plugins | https://github.com/dataiku/dataiku-contrib |

---

## Plugin Folder Structure

A Dataiku plugin is a self-contained folder (or ZIP archive) with a specific structure:

```
my-plugin-id/
├── plugin.json              # REQUIRED: Plugin manifest
├── python-lib/              # Shared Python code
│   └── my_plugin_id/        # Python package (use plugin ID as package name)
│       ├── __init__.py
│       ├── utils.py         # Shared utilities
│       └── models.py        # Pydantic/dataclass models
├── code-env/                # Code environment specification
│   └── python/
│       └── spec/
│           ├── requirements.txt
│           └── requirements.dev.txt
├── custom-recipes/          # Recipe components
│   └── recipe-name/
│       ├── recipe.json      # Recipe descriptor
│       └── recipe.py        # Recipe implementation
├── python-connectors/       # Dataset connectors
│   └── connector-name/
│       ├── connector.json
│       └── connector.py
├── webapps/                 # Webapp components (NOT custom-webapps/)
│   └── webapp-name/
│       ├── webapp.json
│       ├── backend.py       # DSS injects 'app' (Flask) — don't create your own
│       ├── app.js           # Required by DSS even if empty
│       └── body.html        # HTML shell loading assets from resource/dist/
├── python-runnables/        # Macros (runnables)
│   └── macro-name/
│       ├── runnable.json
│       └── runnable.py
├── python-agent-tools/      # LLM agent tools
│   └── tool-name/
│       ├── tool.json
│       └── tool.py
├── python-agents/           # Custom LLM agents
│   └── agent-name/
│       ├── agent.json
│       └── agent.py
├── custom-steps/            # Preparation processor steps
│   └── step-name/
│       ├── processor.json
│       └── processor.py
├── resource/                # Static assets
│   ├── dist/                # Built webapp assets
│   └── icons/               # Custom icons
├── _resource/               # Dynamic parameter scripts
│   └── select_llms.py       # Dynamic SELECT choices
├── Makefile                 # Build automation
├── pyproject.toml           # Python project config
└── README.md                # Plugin documentation
```

---

## plugin.json Reference

The `plugin.json` file is the **mandatory manifest** that describes the plugin.

### Complete plugin.json Template

```json
{
  "id": "my-plugin-id",
  "version": "2.1.0",
  "meta": {
    "label": "My Plugin Name",
    "description": "Comprehensive description of what this plugin provides",
    "author": "Your Name or Organization",
    "icon": "icon-puzzle-piece",
    "iconColor": "blue",
    "licenseInfo": "Apache 2.0",
    "url": "https://github.com/your/plugin-repo",
    "tags": ["LLM", "Governance", "Data Quality"],
    "recipesCategory": "genai"
  },
  "params": [
    {
      "name": "api_key",
      "type": "PASSWORD",
      "label": "API Key",
      "description": "API key for external service",
      "mandatory": true
    },
    {
      "name": "default_timeout",
      "type": "INT",
      "label": "Default Timeout (seconds)",
      "defaultValue": 30
    }
  ],
  "permissions": {
    "requiredPermission": "MODERATE_MODELS"
  }
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique plugin identifier. Only A-Za-z0-9_- allowed. **Immutable after first release**. |
| `version` | string | Yes | Semantic version (MAJOR.MINOR.PATCH). Use for tracking releases. |
| `meta.label` | string | Yes | Display name shown in Dataiku UI. Keep short. |
| `meta.description` | string | Yes | Longer description explaining plugin purpose. |
| `meta.author` | string | No | Plugin author/organization name. |
| `meta.icon` | string | Yes | FontAwesome 3.2.1 icon class (e.g., `icon-cogs`, `icon-cloud`). |
| `meta.iconColor` | string | No | Icon color: red, pink, purple, blue, green, sky, yellow, orange, brown, gray. |
| `meta.licenseInfo` | string | No | License information (e.g., "Apache 2.0", "MIT"). |
| `meta.url` | string | No | URL for documentation or repository. |
| `meta.tags` | array | No | Tags for filtering in plugin list. |
| `meta.recipesCategory` | string | No | Category for recipes: `visual`, `code`, `genai`, or `other`. |
| `params` | array | No | Plugin-level configuration parameters. |
| `permissions` | object | No | Required DSS permissions to use the plugin. |

### Icon Reference

Common FontAwesome 3.2.1 icons for plugins:

| Icon | Use Case |
|------|----------|
| `icon-puzzle-piece` | General plugins |
| `icon-cogs` | Configuration/settings |
| `icon-cloud` | Cloud/API integrations |
| `icon-comments` | Chat/LLM applications |
| `icon-bar-chart` | Analytics/metrics |
| `icon-shield` | Security/governance |
| `icon-rocket` | Performance/optimization |
| `icon-magic` | AI/ML features |
| `icon-database` | Data connectors |
| `icon-dashboard` | Dashboards/webapps |

---

## Shared Python Code (python-lib/)

The `python-lib/` folder contains shared code accessible by all plugin components.

### Best Practices

```python
# python-lib/my_plugin_id/__init__.py
"""
My Plugin shared library.

Import pattern for components:
    from my_plugin_id.utils import call_llm, extract_json
    from my_plugin_id.models import Scenario, EvalResult
"""

from .utils import call_llm, extract_json, sanitize_string
from .models import Scenario, EvalResult

__all__ = ["call_llm", "extract_json", "sanitize_string", "Scenario", "EvalResult"]
```

### Recommended Module Structure

```
python-lib/
└── my_plugin_id/
    ├── __init__.py          # Public API exports
    ├── utils.py             # Shared utilities (LLM calls, JSON parsing)
    ├── models.py            # Pydantic/dataclass models
    ├── constants.py         # Constants and configuration
    └── domain/              # Domain-specific modules
        ├── __init__.py
        ├── evaluation.py    # Evaluation logic
        └── generation.py    # Generation logic
```

### Thread-Safe LLM Caching Pattern

```python
# python-lib/my_plugin_id/utils.py
import threading
from typing import Optional
import dataiku

_thread_local = threading.local()

class ThreadLocalLLMCache:
    """Thread-safe cache for LLM instances in parallel processing."""

    def get_llm(self, project, llm_id: str):
        cache_key = f"llm_{llm_id}"
        cached = getattr(_thread_local, cache_key, None)
        if cached is None:
            cached = project.get_llm(llm_id)
            setattr(_thread_local, cache_key, cached)
        return cached

llm_cache = ThreadLocalLLMCache()
```

---

## Dynamic Parameter Scripts (_resource/)

Scripts in `_resource/` provide dynamic choices for SELECT/MULTISELECT parameters.

### Example: Dynamic LLM List

```python
# _resource/select_llms.py
"""Dynamically populate LLM choices from project."""

def do(payload, config, plugin_config, inputs):
    """
    Called by Dataiku when parameter needs choices.

    Args:
        payload: Contains parameterName being populated
        config: Current component config
        plugin_config: Plugin-level config
        inputs: Input datasets/objects

    Returns:
        dict with "choices" list of {value, label} dicts
    """
    from dataiku import api_client

    if payload.get("parameterName") == "llm_id":
        client = api_client()
        project = client.get_default_project()
        llms = project.list_llms()

        return {
            "choices": [
                {"value": llm["id"], "label": llm.get("friendlyName", llm["id"])}
                for llm in llms
            ]
        }

    return {"choices": []}
```

Reference in recipe.json:
```json
{
  "paramsPythonSetup": "select_llms.py",
  "params": [
    {
      "name": "llm_id",
      "type": "SELECT",
      "label": "LLM Model",
      "getChoicesFromPython": true
    }
  ]
}
```

---

## Packaging & Distribution

### Plugin ZIP Structure

When exporting a plugin, the ZIP must have `plugin.json` at the **root level**:

```
my-plugin-id.zip
├── plugin.json          # At root, NOT in a subfolder
├── python-lib/
├── custom-recipes/
└── ...
```

**Common Mistake**: Zipping the parent folder creates `my-plugin-id/plugin.json` which DSS rejects.

### Makefile Template

```makefile
# Makefile for Dataiku plugin packaging

PLUGIN_ID := my-plugin-id
VERSION := $(shell python -c "import json; print(json.load(open('plugin.json'))['version'])")
DIST_DIR := dist

.PHONY: clean build package install-deps build-frontend

clean:
	rm -rf $(DIST_DIR)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

install-deps:
	cd resource/frontend && npm ci

build-frontend:
	cd resource/frontend && npm run build
	cp -r resource/frontend/dist resource/dist

build: clean build-frontend

package: build
	mkdir -p $(DIST_DIR)
	zip -r $(DIST_DIR)/$(PLUGIN_ID)-$(VERSION).zip . \
		-x "*.git*" \
		-x "*.venv*" \
		-x "*node_modules*" \
		-x "*__pycache__*" \
		-x "*.pytest_cache*" \
		-x "dist/*" \
		-x "resource/frontend/node_modules/*"
	@echo "Created $(DIST_DIR)/$(PLUGIN_ID)-$(VERSION).zip"

# Tag release in git
release: package
	git tag -a v$(VERSION) -m "Release $(VERSION)"
	git push origin v$(VERSION)
```

---

## Git Integration

### Recommended .gitignore

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/

# Node
node_modules/
.npm/

# Build artifacts
dist/
*.zip

# IDE
.idea/
.vscode/
*.swp

# Testing
.pytest_cache/
.coverage
htmlcov/

# Dataiku
*.dss/
```

### Versioning Strategy

1. Use semantic versioning: `MAJOR.MINOR.PATCH`
2. Tag releases in git: `v1.0.0`, `v1.1.0`
3. Update `plugin.json` version before each release
4. Maintain a CHANGELOG.md

---

## Plugin-Level Configuration Access

### In Python Recipes

```python
from dataiku.customrecipe import get_plugin_config

plugin_config = get_plugin_config()
api_key = plugin_config.get("api_key")
timeout = plugin_config.get("default_timeout", 30)
```

### In Python Connectors

```python
class MyConnector(Connector):
    def __init__(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config
        self.api_key = plugin_config.get("api_key")
```

### In Webapps

```python
from dataiku.customwebapp import get_webapp_config

# DSS provides 'app' (Flask) in global scope — do NOT create app = Flask(__name__)
webapp_config = get_webapp_config()
```

---

## Hot Reload During Development

1. Make changes to plugin files
2. In Dataiku UI: Plugin Editor > Actions > Reload this plugin
3. Or call the admin API: `POST /admin/plugins/<plugin-id>/actions/reload`

Plugin components are reloaded without restarting DSS.
