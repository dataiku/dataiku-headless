# Accessing Parameters in Code

How recipes, connectors, runnables, webapps, and R code read parameter values.

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
