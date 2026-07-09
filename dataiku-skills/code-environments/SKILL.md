---
name: code-environments
description: Discover and configure Dataiku DSS code environments. Use when an agent must list available code environments or set the code environment used by a Python, R, or PySpark recipe or an ML analysis.
---

# Code Environments

## Discover

Call `list_code_envs` to see all code environments on the instance with their name, language, and deployment type. Never invent an environment name.

## Set a Recipe's Code Environment

Use `set_recipe_settings` with the `set_code_env` action. Applies to `python`, `r`, and `pyspark` recipes.

```json
{"action": "set_code_env", "env_mode": "EXPLICIT_ENV", "env_name": "my_env"}
{"action": "set_code_env", "env_mode": "INHERIT"}
{"action": "set_code_env", "env_mode": "USE_BUILTIN_MODE"}
```

- `EXPLICIT_ENV` — requires `env_name`; use an exact name from `list_code_envs`
- `INHERIT` — recipe inherits the project or instance default
- `USE_BUILTIN_MODE` — use DSS built-in environment for the language

## Set an ML Analysis Code Environment

Pass `env_mode` and `env_name` to any of the update analysis tools:
- `update_prediction_analysis`
- `update_clustering_analysis`
- `update_causal_prediction_analysis`
- `update_timeseries_forecasting_analysis`

The same three `env_mode` values apply. The current value is visible in `get_ml_analysis_settings` under `mltask_settings.envSelection`.

## When to Change the Code Environment

Do not change the code environment proactively. Only act on it when a recipe run or ML training job fails with an error that indicates an environment problem — missing package, import error, or incompatible Python version. When that happens:

1. Call `list_code_envs` and filter by the relevant language (`PYTHON`, `R`, etc.).
2. Tell the user how many environments of that language exist and ask them to provide the exact name to use.
3. Set `env_mode=EXPLICIT_ENV` with the name they provide.

## Safety Rules

- Always discover with `list_code_envs` before setting `EXPLICIT_ENV`.
- Do not apply `set_code_env` to visual recipes or SQL recipes — it will fail.
