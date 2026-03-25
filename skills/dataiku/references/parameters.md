# Parameters Reference

> Complete reference for all Dataiku plugin parameter types, configuration options, and dynamic parameter setup.

---

## Parameter Structure

Every parameter is defined as a JSON object with these common fields:

```json
{
  "name": "parameter_name",
  "type": "STRING",
  "label": "Display Label",
  "description": "Help text shown to users",
  "defaultValue": "default",
  "mandatory": true,
  "visibilityCondition": "model.other_param == true"
}
```

### Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Identifier used in code (valid Python/JS variable name) |
| `type` | string | Yes | Parameter type (see types below) |
| `label` | string | Yes | Display name in UI |
| `description` | string | No | Help text shown beside field |
| `defaultValue` | varies | No | Pre-filled value matching field type |
| `mandatory` | boolean | No | Whether parameter is required |
| `visibilityCondition` | string | No | JavaScript expression controlling display |

---

## Basic Types

### STRING

Simple text input field.

```json
{
  "name": "api_endpoint",
  "type": "STRING",
  "label": "API Endpoint",
  "defaultValue": "https://api.example.com"
}
```

**Access in Python**: `config.get("api_endpoint")` -> `str`

---

### TEXTAREA

Multi-line text input for longer content.

```json
{
  "name": "system_prompt",
  "type": "TEXTAREA",
  "label": "System Prompt",
  "description": "Instructions for the LLM",
  "defaultValue": "You are a helpful assistant."
}
```

**Access in Python**: `config.get("system_prompt")` -> `str`

---

### PASSWORD

Masked text input for sensitive data.

```json
{
  "name": "api_key",
  "type": "PASSWORD",
  "label": "API Key",
  "mandatory": true
}
```

**Access in Python**: `config.get("api_key")` -> `str`

---

### INT

Integer number input.

```json
{
  "name": "batch_size",
  "type": "INT",
  "label": "Batch Size",
  "defaultValue": 100,
  "minI": 1,
  "maxI": 10000
}
```

| Option | Description |
|--------|-------------|
| `minI` | Minimum allowed value |
| `maxI` | Maximum allowed value |

**Access in Python**: `config.get("batch_size")` -> `int`

---

### DOUBLE

Decimal number input.

```json
{
  "name": "temperature",
  "type": "DOUBLE",
  "label": "Temperature",
  "defaultValue": 0.7,
  "minD": 0.0,
  "maxD": 2.0
}
```

| Option | Description |
|--------|-------------|
| `minD` | Minimum allowed value |
| `maxD` | Maximum allowed value |

**Access in Python**: `config.get("temperature")` -> `float`

---

### BOOLEAN

Checkbox control.

```json
{
  "name": "enable_caching",
  "type": "BOOLEAN",
  "label": "Enable Caching",
  "defaultValue": true
}
```

**Access in Python**: `config.get("enable_caching")` -> `bool`

---

### DATE

Calendar date picker.

```json
{
  "name": "start_date",
  "type": "DATE",
  "label": "Start Date"
}
```

**Access in Python**: `config.get("start_date")` -> `str` (Zulu DateTime format)

---

## List Types

### STRINGS

List of text values.

```json
{
  "name": "categories",
  "type": "STRINGS",
  "label": "Categories",
  "allowDuplicates": false
}
```

**Access in Python**: `config.get("categories")` -> `list[str]`

---

### INTS

List of integer values.

```json
{
  "name": "selected_ids",
  "type": "INTS",
  "label": "Selected IDs"
}
```

**Access in Python**: `config.get("selected_ids")` -> `list[int]`

---

### DOUBLES

List of decimal values.

```json
{
  "name": "thresholds",
  "type": "DOUBLES",
  "label": "Threshold Values"
}
```

**Access in Python**: `config.get("thresholds")` -> `list[float]`

---

## Selection Types

### SELECT

Single-choice dropdown.

```json
{
  "name": "output_format",
  "type": "SELECT",
  "label": "Output Format",
  "selectChoices": [
    {"value": "json", "label": "JSON"},
    {"value": "csv", "label": "CSV"},
    {"value": "parquet", "label": "Parquet"}
  ],
  "defaultValue": "json"
}
```

For dynamic choices from Python:

```json
{
  "name": "llm_model",
  "type": "SELECT",
  "label": "LLM Model",
  "getChoicesFromPython": true,
  "disableAutoReload": false,
  "triggerParameters": ["llm_provider"]
}
```

| Option | Description |
|--------|-------------|
| `selectChoices` | Static list of `{value, label}` objects |
| `getChoicesFromPython` | Enable dynamic choices from Python script |
| `disableAutoReload` | Only load choices on form initialization |
| `triggerParameters` | Reload when these parameters change |

**Access in Python**: `config.get("output_format")` -> `str`

---

### MULTISELECT

Multi-choice selection.

```json
{
  "name": "enabled_features",
  "type": "MULTISELECT",
  "label": "Enabled Features",
  "selectChoices": [
    {"value": "feature_a", "label": "Feature A"},
    {"value": "feature_b", "label": "Feature B"},
    {"value": "feature_c", "label": "Feature C"}
  ],
  "defaultValue": ["feature_a", "feature_b"]
}
```

**Access in Python**: `config.get("enabled_features")` -> `list[str]`

---

## Key-Value Types

### MAP

Key-value mapping (unordered).

```json
{
  "name": "custom_headers",
  "type": "MAP",
  "label": "Custom Headers"
}
```

**Access in Python**: `config.get("custom_headers")` -> `dict`

Example result: `{"Authorization": "Bearer xxx", "X-Custom": "value"}`

---

### KEY_VALUE_LIST

Ordered key-value pairs.

```json
{
  "name": "column_mappings",
  "type": "KEY_VALUE_LIST",
  "label": "Column Mappings"
}
```

**Access in Python**: `config.get("column_mappings")` -> `list[dict]`

Example result: `[{"from": "old_name", "to": "new_name"}, ...]`

---

### OBJECT_LIST

List of complex objects with defined structure.

```json
{
  "name": "evaluation_criteria",
  "type": "OBJECT_LIST",
  "label": "Evaluation Criteria",
  "subParams": [
    {
      "name": "name",
      "type": "STRING",
      "label": "Criterion Name"
    },
    {
      "name": "weight",
      "type": "DOUBLE",
      "label": "Weight",
      "defaultValue": 1.0
    },
    {
      "name": "enabled",
      "type": "BOOLEAN",
      "label": "Enabled",
      "defaultValue": true
    }
  ]
}
```

**Access in Python**: `config.get("evaluation_criteria")` -> `list[dict]`

Example result: `[{"name": "accuracy", "weight": 1.0, "enabled": True}, ...]`

---

## DSS Object Types

### DATASET

Single dataset selection.

```json
{
  "name": "reference_dataset",
  "type": "DATASET",
  "label": "Reference Dataset",
  "canSelectForeign": true
}
```

| Option | Description |
|--------|-------------|
| `canSelectForeign` | Allow selecting datasets from other projects |

**Access in Python**: `config.get("reference_dataset")` -> `str` (dataset name)

---

### DATASETS

Multiple dataset selection.

```json
{
  "name": "input_datasets",
  "type": "DATASETS",
  "label": "Input Datasets",
  "canSelectForeign": true
}
```

**Access in Python**: `config.get("input_datasets")` -> `list[str]`

---

### COLUMN

Single column selection from an input dataset.

```json
{
  "name": "text_column",
  "type": "COLUMN",
  "label": "Text Column",
  "columnRole": "input_dataset",
  "allowedColumnTypes": ["string", "array"]
}
```

| Option | Description |
|--------|-------------|
| `columnRole` | Input role name to select columns from |
| `allowedColumnTypes` | Filter by storage type: string, int, bigint, float, double, boolean, date, array, object |

**Access in Python**: `config.get("text_column")` -> `str` (column name)

---

### COLUMNS

Multiple column selection.

```json
{
  "name": "feature_columns",
  "type": "COLUMNS",
  "label": "Feature Columns",
  "columnRole": "input_dataset"
}
```

**Access in Python**: `config.get("feature_columns")` -> `list[str]`

---

### DATASET_COLUMN / DATASET_COLUMNS

Column selection from a DATASET parameter (not input role).

```json
{
  "name": "reference_dataset",
  "type": "DATASET",
  "label": "Reference Dataset"
},
{
  "name": "join_column",
  "type": "DATASET_COLUMN",
  "label": "Join Column",
  "datasetParamName": "reference_dataset"
}
```

---

### MANAGED_FOLDER

Managed folder selection.

```json
{
  "name": "output_folder",
  "type": "MANAGED_FOLDER",
  "label": "Output Folder",
  "canSelectForeign": true
}
```

**Access in Python**: `config.get("output_folder")` -> `str` (folder name)

---

### SAVED_MODEL

Saved model selection.

```json
{
  "name": "prediction_model",
  "type": "SAVED_MODEL",
  "label": "Prediction Model"
}
```

**Access in Python**: `config.get("prediction_model")` -> `str` (model name)

---

## LLM & AI Types

### LLM

LLM selection from Dataiku LLM Mesh.

```json
{
  "name": "generator_llm",
  "type": "LLM",
  "label": "Generator LLM",
  "mandatory": true,
  "llmUsagePurpose": "GENERIC_COMPLETION"
}
```

| `llmUsagePurpose` | Description |
|-------------------|-------------|
| `GENERIC_COMPLETION` | Text generation (default) |
| `TEXT_EMBEDDING_EXTRACTION` | Text embeddings |
| `IMAGE_EMBEDDING_EXTRACTION` | Image embeddings |
| `IMAGE_GENERATION` | Image generation |
| `IMAGE_INPUT` | Vision/multimodal models |

**Access in Python**: `config.get("generator_llm")` -> `str` (LLM ID)

---

### KNOWLEDGE_BANK

Knowledge Bank selection for RAG.

```json
{
  "name": "knowledge_base",
  "type": "KNOWLEDGE_BANK",
  "label": "Knowledge Base"
}
```

**Access in Python**: `config.get("knowledge_base")` -> `str` (KB name)

---

## Other DSS Objects

### CODE_ENV

Code environment selection.

```json
{
  "name": "execution_env",
  "type": "CODE_ENV",
  "label": "Execution Environment"
}
```

---

### CONNECTIONS

Connection selection.

```json
{
  "name": "database_connection",
  "type": "CONNECTIONS",
  "label": "Database Connection"
}
```

---

### PROJECT

Project selection.

```json
{
  "name": "target_project",
  "type": "PROJECT",
  "label": "Target Project"
}
```

---

### SCENARIO

Scenario selection.

```json
{
  "name": "trigger_scenario",
  "type": "SCENARIO",
  "label": "Trigger Scenario"
}
```

---

## Special Types

### SEPARATOR

Visual section divider (display only).

```json
{
  "type": "SEPARATOR",
  "name": "sep_advanced",
  "label": "Advanced Settings",
  "description": "<p>Configure advanced options below.</p>"
}
```

Note: `description` supports HTML for rich formatting.

---

### PRESET

Pre-defined shared values from Parameter Sets.

```json
{
  "name": "llm_config",
  "type": "PRESET",
  "label": "LLM Configuration",
  "parameterSetId": "llm-settings"
}
```

| Option | Description |
|--------|-------------|
| `parameterSetId` | ID of the Parameter Set component |

---

### CREDENTIAL_REQUEST

Per-user credential request for OAuth or secrets.

```json
{
  "name": "user_credentials",
  "type": "CREDENTIAL_REQUEST",
  "label": "Your Credentials",
  "credentialRequestSettings": {
    "type": "OAUTH2",
    "authorizationEndpoint": "https://auth.example.com/authorize",
    "tokenEndpoint": "https://auth.example.com/token",
    "scope": "read write"
  }
}
```

| `type` | Description |
|--------|-------------|
| `SINGLE_FIELD` | Single secret field |
| `BASIC` | Username/password |
| `OAUTH2` | OAuth 2.0 flow |

---

## Visibility Conditions

Control when parameters are displayed using JavaScript expressions.

```json
{
  "name": "use_custom_model",
  "type": "BOOLEAN",
  "label": "Use Custom Model"
},
{
  "name": "custom_model_path",
  "type": "STRING",
  "label": "Custom Model Path",
  "visibilityCondition": "model.use_custom_model == true"
}
```

### Available in Expressions

- `model.<param_name>` - Access other parameter values
- Standard JavaScript operators: `==`, `!=`, `&&`, `||`, `!`
- Array methods: `model.categories.includes('value')`

### Examples

```json
// Show when checkbox is checked
"visibilityCondition": "model.advanced_mode == true"

// Show when select has specific value
"visibilityCondition": "model.output_format == 'custom'"

// Show when multiselect contains value
"visibilityCondition": "model.features && model.features.indexOf('advanced') >= 0"

// Combine conditions
"visibilityCondition": "model.enabled == true && model.mode == 'advanced'"
```

---

## Dynamic Parameter Setup

### Python Setup Script

Create `_resource/my_params.py`:

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

## Accessing Parameters in Code

### Python Recipes

```python
from dataiku.customrecipe import get_recipe_config, get_plugin_config

config = get_recipe_config()      # Recipe parameters
plugin_config = get_plugin_config()  # Plugin-level parameters

# Access values
batch_size = config.get("batch_size", 100)
api_key = plugin_config.get("api_key")
```

### Python Connectors

```python
class MyConnector(Connector):
    def __init__(self, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config

        # Access values
        self.endpoint = config.get("endpoint")
        self.api_key = plugin_config.get("api_key")
```

### Python Runnables (Macros)

```python
class MyRunnable(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.config = config
        self.plugin_config = plugin_config
```

### Webapps

```python
from dataiku.customwebapp import get_webapp_config
webapp_config = get_webapp_config()
```

### R Code

```r
library(dataiku)
config <- dkuCustomRecipeConfig()
plugin_config <- dkuPluginConfig()
```

---

## Type Coercion Reference

All Python parameter values deserialize to these types:

| Parameter Type | Python Type |
|---------------|-------------|
| STRING, TEXTAREA, PASSWORD | `str` |
| INT | `int` |
| DOUBLE | `float` |
| BOOLEAN | `bool` |
| DATE | `str` (ISO format) |
| STRINGS, INTS, DOUBLES | `list` |
| SELECT | `str` |
| MULTISELECT | `list[str]` |
| MAP | `dict` |
| KEY_VALUE_LIST | `list[dict]` |
| OBJECT_LIST | `list[dict]` |
| DATASET, COLUMN, etc. | `str` |
| DATASETS, COLUMNS | `list[str]` |
