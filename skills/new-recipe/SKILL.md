---
name: new-recipe
description: Add a custom recipe to an existing Dataiku DSS plugin. Generates recipe.json configuration and recipe.py implementation.
disable-model-invocation: true
context: fork
---

Create a new Dataiku custom recipe in an existing plugin.

## Gather Info

Ask the user for:
1. **Plugin** — which plugin to add the recipe to (look for directories containing `plugin.json`)
2. **Recipe name** — kebab-case name (e.g., `compute-embeddings`)
3. **Description** — what the recipe does
4. **Input roles** — datasets/folders the recipe reads from (name, label, arity: UNARY/NARY)
5. **Output roles** — datasets/folders the recipe writes to (name, label, arity, acceptsDataset/acceptsManagedFolder)
6. **Parameters** — recipe configuration params (name, type: STRING/INT/TEXTAREA/SELECT/LLM/BOOLEAN, label, description)

## Generate Files

Create the recipe directory at `{plugin}/custom-recipes/{recipe-name}/` with:

### `recipe.json`
Reference `skills/dataiku/references/recipes.md` for detailed patterns.

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

### `recipe.py`
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

## After Generation

1. Format the code (e.g., `ruff format {plugin}/custom-recipes/{recipe-name}/`)
2. Show generated files and ask if the user wants to adjust roles, params, or implementation
3. Remind them to deploy with `dku plugin push {plugin}` when ready
