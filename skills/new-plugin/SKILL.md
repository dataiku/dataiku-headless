---
name: new-plugin
description: Scaffold a new Dataiku DSS plugin from scratch with proper structure, code environment, and initial components.
disable-model-invocation: true
context: fork
---

Scaffold a new Dataiku DSS plugin.

## Gather Info

Ask the user for:
1. **Plugin directory name** — kebab-case (e.g., `my-new-plugin`)
2. **Plugin ID** — unique identifier (e.g., `my-new-plugin`)
3. **Label** — human-readable name (e.g., "My New Plugin")
4. **Description** — what the plugin does
5. **Category** — e.g., "Generative AI", "Data Quality", "Connectivity"
6. **Initial components** — which component types to scaffold:
   - Agent tools (ask for names)
   - Recipes (ask for names)
   - Guardrails (ask for names)
   - Python agents (ask for names)

## Generate Structure

Create the full plugin directory at the current working directory (or a user-specified path):

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

## After Scaffolding

1. Scaffold any initial components using the `new-tool`, `new-recipe`, `new-webapp`, or `new-guardrail` skills
2. Review the plugin structure against `skills/dataiku/references/plugin-structure.md` for completeness
3. Show the user the full structure and next steps
4. Suggest deploying with `dku plugin push <plugin-dir>` when ready
