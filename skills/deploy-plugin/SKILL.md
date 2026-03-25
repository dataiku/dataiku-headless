---
name: deploy-plugin
description: Build and deploy a Dataiku DSS plugin to an instance using dku CLI or dataikuapi. Handles zip creation, upload, and code environment setup.
disable-model-invocation: true
context: fork
---

Build and deploy a plugin to a Dataiku DSS instance.

## Steps

### 1. Determine Plugin

If `$ARGUMENTS` is provided, use it as the plugin path/name. Otherwise, look for directories containing `plugin.json` in the current working directory and ask which one to deploy.

### 2. Verify Plugin Structure

Before deploying, check that the plugin has the minimum required files:
- `plugin.json` — valid JSON with `id` and `version` fields
- `code-env/python/desc.json` — if the plugin has Python dependencies

Read `plugin.json` to get the plugin ID and version.

### 3. Deploy via dku CLI (Recommended)

The `dku plugin push` command handles both new installs and updates automatically:

```bash
# Push a plugin directory (auto-zips and uploads)
dku plugin push {plugin-directory}

# Push a pre-built zip file
dku plugin push {plugin-name}.zip

# Target a specific DSS instance via profile
dku plugin push {plugin-directory} --profile my-instance

# Or via explicit URL and API key
dku plugin push {plugin-directory} --url https://dss.example.com --api-key YOUR_KEY
```

The CLI detects whether the plugin already exists on the target instance and calls the appropriate API (install or update).

### 4. Create/Update Code Environment

After pushing the plugin, create or update its code environment:

```bash
# List existing code environments
dku code-env list

# If the plugin's code env doesn't exist yet, create it in DSS UI
# or use the dataikuapi approach below
```

For code environment creation via the API (when the CLI doesn't cover it):

```python
import dataikuapi

client = dataikuapi.DSSClient("https://dss.example.com", api_key="YOUR_KEY")
plugin = client.get_plugin("your-plugin-id")

# Create the code env defined in the plugin's desc.json
future = plugin.create_code_env()
result = future.wait_for_result()
print("Code env created:", result)
```

**Code environment gotcha**: NEVER use `installCorePackages: true` in `desc.json` — the `LEGACY_PANDAS023` core set installs `pandas==0.23.4` which fails on Python 3.11+. Always use `installCorePackages: false` with explicit deps in `requirements.txt`.

**Cleanup on failure**: When `create_code_env()` fails, the broken env persists. Delete it before retrying:
```python
ce = client.get_code_env("PYTHON", "code-env-name")
ce.delete()
future = plugin.create_code_env()
result = future.wait_for_result()
```

### 5. Verify Deployment

```bash
# Confirm the plugin appears
dku plugin list

# Check plugin settings
dku plugin settings {plugin-id}
```

### 6. dataikuapi Fallback (Without dku CLI)

If the dku CLI is not available, deploy directly with `dataikuapi`:

```python
import dataikuapi

client = dataikuapi.DSSClient("https://dss.example.com", api_key="YOUR_KEY")
plugin_id = "your-plugin-id"

# --- Option A: Install new plugin ---
with open("plugin.zip", "rb") as f:
    client.install_plugin_from_archive(f)

# --- Option B: Update existing plugin ---
plugin = client.get_plugin(plugin_id)
with open("plugin.zip", "rb") as f:
    plugin.update_from_zip(f)
```

**Important API notes:**
- `install_plugin_from_archive()` fails if the plugin directory already exists — remove it first or use `update_from_zip()`
- Both `update_from_zip()` and `install_plugin_from_archive()` return `None` (not a future)
- The ZIP must have `plugin.json` at root level (don't zip a wrapper folder)

### Building a zip manually

If you need to create a zip from a plugin directory:

```bash
(cd {plugin-directory} && zip -r ../my-plugin.zip . -x "*.pyc" -x "__pycache__/*" -x ".git/*" -x "tests/*")
```

## Notes

- Always check plugin.json is valid before deploying
- Format code before deploying (e.g., `ruff check --fix . && ruff format .`)
- For iterative development, `dku plugin push` is the fastest workflow
- The `dku plugin push` command can be integrated into CI/CD pipelines for automated deployment
