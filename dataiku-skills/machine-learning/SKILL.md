---
name: machine-learning
description: Inspect Dataiku visual ML analyses and saved models. Use when an agent must understand existing ML objects before asking Cobuild to create or modify project assets.
---

# Machine Learning Inspection

Use this skill to inspect existing ML analyses and saved models.

## Workflow

1. Use `list_ml_analyses`, `get_ml_analysis_summary`, and `get_ml_analysis_settings` to inspect analyses.
2. Use `list_ml_analysis_models` and `get_ml_model_details` to inspect trained models within an analysis.
3. Use `list_saved_models`, `list_saved_model_versions`, and `get_saved_model_version_details` to inspect saved models.
4. Route ML creation, tuning, training, deployment, or updates through `./dataiku-skills/cobuild/SKILL.md`.
5. Use the ML task-type subskills as supporting context only when the user needs a specific ML-task interpretation before a Cobuild write.

## Preferred Tools

- `list_ml_analyses`
- `get_ml_analysis_summary`
- `get_ml_analysis_settings`
- `list_ml_analysis_models`
- `get_ml_model_details`
- `list_saved_models`
- `list_saved_model_versions`
- `get_saved_model_version_details`

## Safety Rules

- Never invent analysis ids, model ids, or saved model ids.
- Keep this skill focused on inspection and Cobuild grounding.
