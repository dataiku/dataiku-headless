---
name: ml-recipes
description: Conceptual guide to selecting and interpreting Dataiku visual ML recipes for Cobuild requests.
---

# ML Recipes

Read this reference when a Flow transformation creates features, scores records, or evaluates model outputs. Use `../machine-learning.md` to inspect the relevant analysis, trained model, or saved model before describing the work to Cobuild.

| Type | Concept |
| --- | --- |
| `generate_features` | Creates derived features through visual joins, transformations, and aggregations. Preserve the intended entity grain. |
| `prediction_scoring` | Applies a saved prediction model to compatible records. |
| `clustering_scoring` | Assigns cluster labels using a trained clustering model. |
| `evaluation` | Evaluates a model against reference data. |
| `standalone_evaluation` | Evaluates prediction outputs when no Dataiku saved model is available. |

## Selection Notes

- Training recipes appear in the Flow after an ML analysis is deployed. They are configured through the ML analysis, not as ordinary recipes.
- Scoring requires input records compatible with the selected model's expected features and schema. Inspect model and dataset context before requesting scoring work.
- Evaluation needs a clear reference outcome, evaluation population, and success criterion. State what decision the evaluation should support rather than only requesting an evaluation recipe.
