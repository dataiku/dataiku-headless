---
name: machine-learning-prediction
description: Inspect prediction analyses and use the findings as context for Cobuild. Use when an agent must understand an existing prediction task before asking Cobuild to create or modify ML assets.
---

# Prediction Task Context

Use this skill to interpret existing prediction analyses and trained-model context.

## Workflow

1. Use `get_ml_analysis_summary` and `get_ml_analysis_settings` to inspect the current task.
2. Use `list_ml_analysis_models` and `get_ml_model_details` when trained-model details matter.
3. Route prediction-analysis creation, updates, training, and deployment through `../../../cobuild/SKILL.md`.

## Safety Rules

- Keep this skill focused on inspection and task interpretation.
- Do not document direct ML mutation workflows here.
