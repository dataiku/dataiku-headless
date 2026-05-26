# Dynamic Parameters

Dynamic parameter setup, params helper patterns, and reload behavior.

## Dynamic Parameter Setup

### Python Setup Script

Create `resource/params_helper.py`:

```python
def do(payload, config, plugin_config, inputs):
    """
    Generate dynamic choices for SELECT/MULTISELECT parameters.

    Args:
        payload: dict with:
            - parameterName: name of parameter being populated
            - parameterId: unique parameter ID
        config: current component configuration
        plugin_config: plugin-level configuration
        inputs: list of input dataset/folder specs

    Returns:
        dict with "choices" key containing list of {value, label} dicts
    """
    param_name = payload.get("parameterName")

    if param_name == "llm_model":
        from dataiku import api_client
        client = api_client()
        project = client.get_default_project()
        llms = project.list_llms()

        return {
            "choices": [
                {"value": llm["id"], "label": llm.get("friendlyName", llm["id"])}
                for llm in llms
            ]
        }

    if param_name == "input_columns":
        # Get columns from first input dataset
        if inputs and len(inputs) > 0:
            import dataiku
            ds = dataiku.Dataset(inputs[0]["fullName"])
            schema = ds.read_schema()
            return {
                "choices": [
                    {"value": col["name"], "label": col["name"]}
                    for col in schema
                ]
            }

    return {"choices": []}
```

### Advanced: Service-Layer Dynamic Params

For complex plugins, route param resolution through your service layer instead of calling DSS API directly. This enables cascading params (e.g., model → version):

```python
# resource/params_helper.py
import logging

logger = logging.getLogger(__name__)

def _get_service(config):
    """Create service from current config — reuses python-lib/ code."""
    from my_plugin.services.factory import get_service
    from my_plugin.services.client import LocalClient
    client = LocalClient(config.get("project_key"))
    return get_service(client=client)

def do(payload, config, plugin_config, inputs):
    param_name = payload.get("parameterName")
    logger.info("params_helper: param=%s config=%s", param_name, config)

    if param_name == "semantic_model_id":
        return _list_models(config)
    elif param_name == "version_number":
        return _list_versions(config)

    return {"choices": []}

def _list_models(config):
    try:
        service = _get_service(config)
        models = service.list_models()
        return {"choices": [{"value": m.id, "label": m.name} for m in models]}
    except Exception as e:
        logger.warning("list_models failed: %s", e)
        return {"choices": []}

def _list_versions(config):
    """Cascading param — depends on semantic_model_id being set first."""
    model_id = config.get("semantic_model_id")
    if not model_id:
        return {"choices": [{"value": "", "label": "Select a model first"}]}

    try:
        service = _get_service(config)
        model = service.get_model(model_id)
        choices = [{"value": "", "label": "Active version (default)"}]
        for v in model.versions:
            label = v.id
            if v.id == model.active_version_id:
                label += " (active)"
            choices.append({"value": v.id, "label": label})
        return {"choices": choices}
    except Exception as e:
        logger.warning("list_versions failed: %s", e)
        return {"choices": [{"value": "", "label": "Active version (default)"}]}
```

In `tool.json`, use `triggerParameters` so the version dropdown reloads when the model changes:

```json
{
    "name": "semantic_model_id",
    "type": "SELECT",
    "label": "Semantic Model",
    "getChoicesFromPython": true,
    "mandatory": true
},
{
    "name": "version_number",
    "type": "SELECT",
    "label": "Version",
    "getChoicesFromPython": true,
    "triggerParameters": ["semantic_model_id", "project_key"]
}
```

> **Note:** The `resource/` folder (not `_resource/`) is where params_helper.py lives for plugins. The `_resource/` path was used in older DSS versions.

### Reference in Component JSON

```json
{
  "paramsPythonSetup": "my_params.py",
  "params": [
    {
      "name": "llm_model",
      "type": "SELECT",
      "label": "LLM Model",
      "getChoicesFromPython": true
    }
  ]
}
```

### Controlling Reload Behavior

```json
{
  "name": "provider",
  "type": "SELECT",
  "label": "Provider",
  "selectChoices": [
    {"value": "openai", "label": "OpenAI"},
    {"value": "anthropic", "label": "Anthropic"}
  ]
},
{
  "name": "model",
  "type": "SELECT",
  "label": "Model",
  "getChoicesFromPython": true,
  "disableAutoReload": true,
  "triggerParameters": ["provider"]
}
```

| Option | Description |
|--------|-------------|
| `disableAutoReload` | Don't reload on form open, only when triggered |
| `triggerParameters` | Reload when these parameter values change |

---
