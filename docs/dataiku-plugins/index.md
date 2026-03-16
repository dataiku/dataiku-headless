# Dataiku DSS Plugin Development Guide

> **For AI Coding Agents**: This is the authoritative reference for building production-grade Dataiku DSS plugins. Use this guide when creating, modifying, or debugging plugin components.

---

## Quick Reference

| Component Type | Folder | Config File | Code File | Use Case |
|---------------|--------|-------------|-----------|----------|
| [Recipes](./recipes.md) | `custom-recipes/` | `recipe.json` | `recipe.py` | Data transformations |
| [Datasets](./datasets.md) | `python-connectors/` | `connector.json` | `connector.py` | External data sources |
| [Webapps](./webapps.md) | `custom-webapps/` | `webapp.json` | `backend.py` | Interactive UIs |
| [Macros](./macros.md) | `python-runnables/` | `runnable.json` | `runnable.py` | One-click utilities |
| [LLM Tools](./llm-tools.md) | `python-agent-tools/` | `tool.json` | `tool.py` | Agent capabilities |
| [Custom Agents](./llm-tools.md#custom-agents) | `python-agents/` | `agent.json` | `agent.py` | Full LLM agents |

---

## Documentation Index

### Core Concepts
- **[Plugin Structure](./plugin-structure.md)** - Folder layout, plugin.json anatomy, packaging
- **[Parameters Reference](./parameters.md)** - All parameter types and configuration options
- **[Code Environments](./code-environments.md)** - Managing Python dependencies

### Component Guides
- **[Recipes](./recipes.md)** - Custom recipe development (Python, R, SQL)
- **[Datasets & Connectors](./datasets.md)** - External data source integration
- **[Webapps](./webapps.md)** - Interactive dashboards and UIs (Vue, Flask, Dash)
- **[Macros](./macros.md)** - Runnable utilities and automation
- **[LLM Tools & Agents](./llm-tools.md)** - GenAI agent extensions

### Development Practices
- **[Testing & Debugging](./testing.md)** - Unit tests, integration tests, CI/CD
- **[Best Practices](./best-practices.md)** - Design patterns and production guidelines

---

## Plugin Architecture Overview

```
my-plugin-id/
├── plugin.json              # Plugin metadata & manifest (REQUIRED)
├── python-lib/              # Shared Python code (importable by all components)
│   └── my_plugin_id/        # Python package root
│       ├── __init__.py
│       └── utils.py
├── code-env/                # Code environment specification
│   └── python/
│       └── spec/
│           └── requirements.txt
├── custom-recipes/          # Recipe components
│   └── my-recipe/
│       ├── recipe.json
│       └── recipe.py
├── python-connectors/       # Dataset connectors
│   └── my-connector/
│       ├── connector.json
│       └── connector.py
├── custom-webapps/          # Webapp components
│   └── my-webapp/
│       ├── webapp.json
│       ├── backend.py
│       └── resource/frontend/
├── python-runnables/        # Macros
│   └── my-macro/
│       ├── runnable.json
│       └── runnable.py
├── python-agent-tools/      # LLM agent tools
│   └── my-tool/
│       ├── tool.json
│       └── tool.py
├── python-agents/           # Custom agents
│   └── my-agent/
│       ├── agent.json
│       └── agent.py
├── custom-steps/            # Preparation processor steps
├── resource/                # Static assets (icons, templates, built frontend)
│   └── dist/                # Built webapp assets
└── _resource/               # Dynamic parameter setup scripts
    └── select_llms.py
```

---

## Essential plugin.json Template

```json
{
  "id": "my-plugin-id",
  "version": "1.0.0",
  "meta": {
    "label": "My Plugin",
    "description": "Brief description of what the plugin does",
    "author": "Your Name",
    "icon": "icon-puzzle-piece",
    "licenseInfo": "Apache 2.0",
    "url": "https://github.com/your/repo",
    "tags": ["LLM", "Data Quality", "Automation"]
  },
  "params": []
}
```

### Key plugin.json Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier (A-Za-z0-9_- only), immutable after release |
| `version` | Yes | Semantic version (e.g., "2.1.0") |
| `meta.label` | Yes | Display name in UI |
| `meta.description` | Yes | User-facing description |
| `meta.icon` | Yes | FontAwesome 3.2.1 icon name |
| `meta.author` | No | Plugin author |
| `meta.tags` | No | Filtering tags |
| `params` | No | Plugin-level configuration parameters |

---

## Common Development Tasks

### Creating a New Recipe
1. Create folder: `custom-recipes/my-recipe/`
2. Add `recipe.json` with meta, inputRoles, outputRoles, params
3. Add `recipe.py` with transformation logic
4. See [Recipes Guide](./recipes.md) for full details

### Adding a Webapp Dashboard
1. Create folder: `custom-webapps/my-webapp/`
2. Add `webapp.json` with parameters
3. Add `backend.py` (Flask) or framework-specific files
4. Build frontend to `resource/dist/`
5. See [Webapps Guide](./webapps.md) for full details

### Extending LLM Agents
1. Create folder: `python-agent-tools/my-tool/`
2. Add `tool.json` with inputSchema
3. Add `tool.py` extending `BaseAgentTool`
4. See [LLM Tools Guide](./llm-tools.md) for full details

---

## Official Documentation Links

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

## Version Compatibility

This documentation is based on **Dataiku DSS 14** (2024-2025). Key features by version:
- **DSS 14.1+**: Knowledge Banks as recipe inputs (`acceptsKnowledgeBank`)
- **DSS 13+**: LLM Mesh, Agent Tools, Custom Agents
- **DSS 12+**: Enhanced webapp frameworks (Dash, Streamlit)
