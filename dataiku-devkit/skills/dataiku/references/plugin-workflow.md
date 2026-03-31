# Dataiku Plugin Development Workflow

Master the complete plugin development lifecycle from initial development to production deployment.

## Overview

### Workflow Stages

1. **Setup** - Development environment and plugin structure
2. **Development** - Writing and testing components
3. **Version Control** - Git integration and branching
4. **Testing** - Unit tests, integration tests, validation
5. **Documentation** - Code docs, user guides, examples
6. **Versioning** - Semantic versioning and releases
7. **Distribution** - Sharing via zip, Git, or plugin store
8. **Maintenance** - Updates, bug fixes, support

## Development Environment Setup

### Prerequisites

- Dataiku DSS instance with plugin development permissions
- Python/R development environment
- Git for version control
- IDE with Dataiku support (VS Code, PyCharm)

### Creating Development Plugin

```python
# Method 1: From scratch
# Navigate to: Plugins > Add Plugin > Write your own

# Method 2: Convert existing component
# Open code recipe/webapp -> Click "Convert to plugin"

# Method 3: Clone from Git
# Plugins > Add Plugin > Fetch from Git -> Enable "Development mode"
```

See `plugin-structure.md` for the complete folder layout.

## Version Control with Git

### Branching Strategy

```bash
# Feature development
git checkout -b feature/new-connector

# Bug fixes
git checkout -b hotfix/fix-schema-parsing

# Release preparation
git checkout -b release/v2.0.0
```

### Recommended Branches

- **main** - Stable, production-ready code
- **develop** - Integration branch for features
- **feature/** - New features and enhancements
- **hotfix/** - Urgent bug fixes
- **release/** - Release preparation

### Commit Message Convention

```
<type>(<scope>): <subject>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples:**
```bash
git commit -m "feat(connector): add OAuth2 authentication"
git commit -m "fix(recipe): handle missing columns gracefully"
git commit -m "docs(readme): add usage examples"
```

## Semantic Versioning

### Version Format

```
MAJOR.MINOR.PATCH (e.g., 2.1.3)
```

- **MAJOR** - Breaking changes
- **MINOR** - New features, backward compatible
- **PATCH** - Bug fixes

### Updating plugin.json

```json
{
  "id": "my-plugin",
  "version": "2.1.3",
  "meta": {
    "label": "My Plugin",
    "description": "Custom data processing tools",
    "author": "Your Name",
    "icon": "icon-puzzle-piece",
    "licenseInfo": "Apache 2.0",
    "url": "https://github.com/username/my-plugin",
    "tags": ["Data Processing", "Custom"]
  }
}
```

### Version Tags

```bash
git tag -a v2.1.3 -m "Release version 2.1.3"
git push origin v2.1.3
```

See `testing.md` for full test patterns, mock fixtures, and integration test setup.

## Code Quality

### Linting & Formatting

Use **ruff** (single tool replacing flake8, black, isort) with **120-char line length** (Dataiku standard):

```bash
pip install ruff
ruff check python-lib/ custom-recipes/ --line-length=120
ruff format python-lib/ custom-recipes/
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff          # lint + isort
        args: [--fix]
      - id: ruff-format   # formatting
```

## Distribution

### Method 1: Zip Archive

```bash
zip -r my-plugin-v2.1.3.zip * -x "*.git*" "*.dku-backup" "__pycache__/*"
```
Install: Plugins > Add Plugin > Upload zip

**Zip exclusions matter for plugins with frontends.** Dev-only files inflate the zip and can cause issues. Exclude: `docs/`, `scripts/`, `CLAUDE.md`, `*.pptx`, lock files, frontend source (`resource/frontend/src/`), `alembic/`, `node_modules/`, `tests/`, dev databases.

### Method 2: Git Repository

```bash
git tag v2.1.3
git push origin main --tags
```
Install: Plugins > Add Plugin > Fetch from Git

### Method 3: Plugin Store

Prerequisites: Public Git repo, complete docs, multi-version testing, license file.

## CI/CD Integration

### GitHub Actions

```yaml
name: Plugin CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11"]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -r code-env/python/spec/requirements.txt
          pip install pytest pytest-cov flake8
      - name: Lint
        run: ruff check python-lib/ custom-recipes/ --line-length=120
      - name: Run tests
        run: pytest tests/ --cov=python-lib --cov-report=xml

  package:
    needs: test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Create plugin zip
        run: zip -r plugin.zip * -x "*.git*" "tests/*" ".github/*"
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: plugin-${{ github.ref_name }}
          path: plugin.zip
```

## Debugging Plugin Installation

### Common Installation Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Invalid plugin.json` | Malformed JSON | Validate JSON syntax |
| `Code environment creation failed` | Incompatible packages | Check requirements.txt |
| `Module not found` | python-lib path issue | Ensure `__init__.py` exists |
| `Component not found` | JSON descriptor missing | Verify recipe.json exists |
| `Permission denied` | Missing dev permissions | Admin must grant "Develop plugins" |

### Debugging Checklist

```bash
# Validate plugin.json
python -c "import json; json.load(open('plugin.json'))"

# Check Python imports
PYTHONPATH=python-lib python -c "import my_plugin; print('OK')"

# Verify requirements
pip install -r code-env/python/spec/requirements.txt --dry-run
```

### Plugin Reload vs. Reinstall

| Action | When to Use |
|--------|-------------|
| **Reload** | Code changes in recipes, processors, webapps |
| **Rebuild code env** | Added/changed packages in requirements.txt |
| **Reinstall** | Changed plugin.json structure, added/removed components |

## CLI-Based Plugin Deployment

The `dku` CLI supports the full plugin lifecycle without dropping to Python:

```bash
# First install: push + create code env + assign
dku plugin push plugin.zip --install && \
dku plugin create-code-env my-plugin && \
dku plugin set-code-env my-plugin plugin_my_plugin_managed

# Update: push + optionally rebuild code env
dku plugin push plugin.zip && \
dku plugin update-code-env my-plugin   # Only if deps changed

# Check state and available recipe types
dku plugin get my-plugin -o json
dku plugin recipes my-plugin
dku plugin usages my-plugin
```

**Code env is NOT auto-created on install.** You must explicitly create and assign it. Without it, DSS runs backend code on its base Python with none of your dependencies.

**IMPORTANT: Recipe Type Registration Gotcha.** After `dku plugin push`, DSS extracts plugin files but does NOT refresh its in-memory recipe type registry. Plugin recipe types (`CustomCode_<pluginId>_<recipeId>`) become available only after:
1. DSS restart, OR
2. Plugin reload from DSS UI (Plugins > Actions > Reload)

This means a push-then-create-recipe workflow may fail with "unknown recipe type". After pushing, verify types are registered with `dku plugin recipes my-plugin`. If types are missing, restart DSS or reload from the UI.

## Code Environment Patterns

**code-env/python/desc.json:**
```json
{
  "acceptedPythonInterpreters": ["PYTHON311", "PYTHON312"],
  "forceConda": false,
  "installCorePackages": false,
  "installJupyterSupport": false
}
```

**CRITICAL:** `installCorePackages` must be `false`. If `true`, DSS installs its own packages (pandas, scikit-learn) which conflict with your pinned versions on Python 3.11+.

## Common Patterns Across Plugins

**Error Messages:**
```python
if not config.get('api_key'):
    raise ValueError("API key is required. Please configure in plugin settings.")
```

**Logging:**
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"Processing {len(rows)} rows")
logger.warning(f"Column {col} not found, skipping")
```

**Progress Reporting:**
```python
total = len(items)
for i, item in enumerate(items):
    process(item)
    if i % 100 == 0:
        progress_callback(int(100 * i / total))
```

## Backward Compatibility

```python
# Version-aware code
try:
    df = dataset.get_fast_path_dataframe(columns=["col_a"])  # DSS 13+
except AttributeError:
    df = dataset.get_dataframe(columns=["col_a"])  # Fallback for DSS 12
```

### Version Constraints in plugin.json

```json
{
  "meta": {
    "supportedDSSVersions": ">=12.0.0"
  }
}
```
