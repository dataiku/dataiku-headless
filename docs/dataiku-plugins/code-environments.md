# Code Environments Guide

> Complete reference for managing Python dependencies in Dataiku plugins.

---

## Overview

Code environments provide isolated Python environments for plugins. They ensure:
- Reproducible dependency versions
- Isolation from other plugins
- Consistent execution across DSS nodes

---

## Folder Structure

```
my-plugin/
└── code-env/
    └── python/
        └── spec/
            ├── requirements.txt       # Production dependencies
            └── requirements.dev.txt   # Development dependencies (optional)
```

---

## requirements.txt Best Practices

### Pin Exact Versions

```txt
# Always pin exact versions for reproducibility
pandas==2.1.4
numpy==1.26.2
requests==2.31.0
pydantic==2.5.2

# For packages with frequent updates, pin major.minor
flask>=3.0.0,<4.0.0

# Dataiku internal client (if needed)
dataiku-internal-client>=12.0.0
```

### Common Plugin Dependencies

```txt
# Data Processing
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=14.0.0

# Web/API
requests>=2.31.0
flask>=3.0.0
flask-cors>=4.0.0
flask-socketio>=5.3.0

# LLM/AI
langchain>=0.1.0
openai>=1.0.0
anthropic>=0.8.0
tiktoken>=0.5.0

# Validation
pydantic>=2.0.0
jsonschema>=4.20.0

# Utilities
python-dateutil>=2.8.0
tenacity>=8.2.0
tqdm>=4.66.0
```

### Development Dependencies

```txt
# requirements.dev.txt

# Testing
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.12.0

# Linting
ruff>=0.1.0
mypy>=1.7.0

# Type stubs
pandas-stubs>=2.1.0
types-requests>=2.31.0
```

---

## Code Environment Configuration

### desc.json (Alternative Format)

Some plugins use `desc.json` instead of `requirements.txt`:

```json
{
  "acceptedPythonInterpreters": ["PYTHON36", "PYTHON37", "PYTHON38", "PYTHON39", "PYTHON310", "PYTHON311"],
  "forceConda": false,
  "installCorePackages": true,
  "installJupyterSupport": false,
  "basePackagesInstallMethod": "PIP_INSTALL",
  "pipPackages": [
    {"name": "pandas", "version": ">=2.0.0"},
    {"name": "requests", "version": ">=2.31.0"},
    {"name": "flask", "version": ">=3.0.0"}
  ],
  "condaPackages": [],
  "jarFiles": []
}
```

### Field Reference

| Field | Description |
|-------|-------------|
| `acceptedPythonInterpreters` | List of supported Python versions |
| `forceConda` | Force Conda instead of pip |
| `installCorePackages` | Include Dataiku core packages |
| `installJupyterSupport` | Include Jupyter packages |
| `basePackagesInstallMethod` | `PIP_INSTALL` or `CONDA_INSTALL` |
| `pipPackages` | List of pip packages with versions |
| `condaPackages` | List of Conda packages |
| `jarFiles` | Java JAR files (for Spark) |

---

## Creating Code Environments

### Via Plugin Editor

1. Open plugin in Dataiku
2. Go to Settings > Code env
3. Click "Create" or "Update"
4. DSS builds the environment

### Via API

```python
import dataiku

client = dataiku.api_client()
plugin = client.get_plugin("my-plugin")

# Create or update code env
plugin.create_code_env()

# Check status
env_info = plugin.get_code_env()
print(f"Status: {env_info['status']}")
```

### Build Logs

View build logs in:
- Plugin editor > Settings > Code env > View logs
- `$DATA_DIR/code-envs/plugins/my-plugin/build.log`

---

## Environment Variables

### Accessing in Code

```python
import os

# Standard environment variables
python_version = os.environ.get("DKU_PYTHON_VERSION")
dss_version = os.environ.get("DKU_DSS_VERSION")
project_key = os.environ.get("DKU_CURRENT_PROJECT_KEY")

# Custom variables (set in code env settings)
custom_value = os.environ.get("MY_CUSTOM_VAR")
```

### Setting Custom Variables

In `desc.json`:

```json
{
  "envVars": [
    {"name": "MY_CUSTOM_VAR", "value": "custom_value"},
    {"name": "API_TIMEOUT", "value": "30"}
  ]
}
```

---

## Common Patterns

### Lazy Import for Performance

```python
# python-lib/my_plugin/utils.py

# Don't import heavy libraries at module level
# Import them in functions where needed

def process_data(df):
    """Process data using pandas."""
    import pandas as pd
    import numpy as np

    # Use pandas/numpy here
    return df.apply(np.mean)

def call_llm(prompt):
    """Call LLM using langchain."""
    from langchain.llms import OpenAI

    llm = OpenAI()
    return llm(prompt)
```

### Conditional Imports

```python
# Handle optional dependencies gracefully

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

def embed_text(text):
    if not TORCH_AVAILABLE:
        raise ImportError("torch is required for embeddings. Add it to requirements.txt")

    # Use torch
    ...
```

### Version Checking

```python
import sys
import importlib.metadata

def check_dependencies():
    """Verify required dependencies are installed."""
    required = {
        "pandas": "2.0.0",
        "requests": "2.31.0",
        "flask": "3.0.0"
    }

    for package, min_version in required.items():
        try:
            installed = importlib.metadata.version(package)
            if installed < min_version:
                raise ImportError(
                    f"{package} {installed} is installed, "
                    f"but {min_version}+ is required"
                )
        except importlib.metadata.PackageNotFoundError:
            raise ImportError(f"{package} is not installed")
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Build fails | Check build logs, verify package availability on PyPI |
| Version conflict | Use compatible version ranges, check dependency tree |
| Import errors at runtime | Verify package is in requirements.txt, rebuild env |
| Slow startup | Use lazy imports for heavy packages |
| Memory issues | Limit concurrent imports, use memory-efficient alternatives |

### Debugging Build Failures

```bash
# Check build log
cat $DATA_DIR/code-envs/plugins/my-plugin/build.log

# Test locally
python -m venv test_env
source test_env/bin/activate
pip install -r code-env/python/spec/requirements.txt
```

### Force Rebuild

```python
import dataiku

client = dataiku.api_client()
plugin = client.get_plugin("my-plugin")

# Force rebuild
plugin.update_code_env(force_rebuild=True)
```

---

## Multi-Python Version Support

### Specify Compatible Versions

```json
{
  "acceptedPythonInterpreters": [
    "PYTHON39",
    "PYTHON310",
    "PYTHON311"
  ]
}
```

### Version-Specific Requirements

```txt
# requirements.txt

# Use environment markers for version-specific deps
numpy>=1.24.0; python_version >= "3.9"
numpy>=1.21.0; python_version < "3.9"

# Backport packages for older Python
typing_extensions>=4.0.0; python_version < "3.10"
```

---

## Conda Environments

For packages requiring Conda (e.g., some ML frameworks):

```json
{
  "forceConda": true,
  "condaPackages": [
    {"name": "pytorch", "version": "2.1.0"},
    {"name": "cudatoolkit", "version": "11.8"}
  ],
  "pipPackages": [
    {"name": "transformers", "version": "4.35.0"}
  ]
}
```

---

## Best Practices

### Security
- Regularly update dependencies for security patches
- Use `pip-audit` or similar tools to check for vulnerabilities
- Pin versions to prevent supply chain attacks

### Performance
- Minimize dependencies to reduce build time
- Use lazy imports for heavy packages
- Consider package size impact on deployment

### Maintenance
- Document why each dependency is needed
- Review and update dependencies quarterly
- Test with multiple Python versions
