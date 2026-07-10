---
name: recipes
description: Inspect Dataiku recipes and use their current settings as grounding for Cobuild. Use when an agent must discover recipes, inspect recipe settings, or understand recipe types before asking Cobuild to create, edit, or build project assets.
---

# Recipe Inspection

Use this skill to inspect existing recipes and gather context for Cobuild.

## Workflow

1. Use `get_flow_items_in_traversal_order`, `list_recipes`, and `list_datasets` when you need flow context.
2. Use `get_recipe_settings` to inspect a specific recipe before asking Cobuild to modify it.
3. Use dataset inspection tools when input or output schema details matter; for recipe types noted below, also inspect the extra context they depend on.
4. If the task requires creating, editing, wiring, or executing a recipe, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Recipe Type Catalog

The available recipe family types are: Data prep (visual), ML (visual), GenAI (visual), and Code. Visual recipe types should be preferred unless the user specifically requests transformations be performed via "code". Descriptions below ground interpretation of `get_recipe_settings` output and precise Cobuild prompts; "Extra context" names read tools to consult beyond the recipe's own settings and its input/output datasets.

Dataiku's formula language (GREL) shows up across several recipe types — most often `prepare` (`CreateColumnWithGREL`, `FilterOnCustomFormula`) but also formula-driven filters and computed fields in other visual recipes. See [formula language reference](references/dataiku_formula_language.md) whenever a recipe's settings contain a formula expression, regardless of recipe type.

### Data prep (visual)

| Type | Use when | Extra context |
| --- | --- | --- |
| `prepare` (shaker) | Column-level cleansing/enrichment with visual processors | [Processor catalog](references/prepare_processors_overview.md) |
| `join` | Join datasets on keys, optional pre/post filters | — |
| `fuzzyjoin` | Join exactly two datasets using fuzzy distances, optional text normalization, and matching-detail output | — |
| `geojoin` | Join datasets on geospatial predicates such as distance, containment, and intersection | — |
| `grouping` | Aggregate rows by group keys | — |
| `window` | Window analytics (rank, running totals, partitioned calcs) | — |
| `sampling` | Sampling rows (randomly, first N, class rebalance, etc.) and/or filtering rows (based on rules, formula, etc.) | — |
| `split` | Dispatch rows of one dataset into several other datasets, based on rules | — |
| `sort` | Order rows by one or more columns | — |
| `distinct` | Deduplicate rows | — |
| `topn` | Keep top and/or bottom N rows sorted by one or more columns | — |
| `vstack` | Union all/append rows from multiple datasets | — |
| `sync` | Copy between storage backends | — |
| `pivot` | Long → wide reshape | — |
| `download` | Files-based connection → managed folder | Managed folders |
| `export` | Dataset → files in managed folder | Managed folders |
| `upsert` | Merge/upsert rows into a target dataset | — |

### ML (visual)

| Type | Use when | Extra context |
| --- | --- | --- |
| `generate_features` | Auto-generate features via joins/transforms/aggregations | — |
| `prediction_scoring` | Score records with a trained prediction model | Saved models |
| `clustering_scoring` | Label records with a trained clustering model | Saved models |
| `evaluation` | Evaluate a model against reference data | Evaluation stores |
| `standalone_evaluation` | Evaluate the prediction outputs of external models (no model object in the Dataiku project) | Evaluation stores |

**ML training recipes** (`prediction_training`, `clustering_training`, `causal_prediction_training`, `timeseries_forecasting_training`) appear in the flow after deploying an ML analysis. Inspect them via `../machine-learning/SKILL.md` (`get_ml_analysis_settings`/`get_ml_analysis_summary`), not `get_recipe_settings` — they're ML-managed, not plain recipes. Edits route through Cobuild same as everything else.

### GenAI (visual)

| Type | Use when | Extra context |
| --- | --- | --- |
| `prompt` | Run column values through an arbitrary LLM prompt | LLM context (`list_llms`/`get_llm_info`) |
| `nlp_llm_model_provided_classification` | LLM classify text into predefined categories | LLM context |
| `nlp_llm_user_provided_classification` | LLM classify text into user-defined classes | LLM context |
| `nlp_llm_summarization` | LLM summarize column text | LLM context |
| `nlp_llm_rag_embedding` | Embeddings from column text → Knowledge Bank | Knowledge banks, LLM context |
| `embed_documents` | Embeddings from docs in a managed folder → folder + optional Knowledge Bank | Managed folders, knowledge banks |
| `extract_content` | Extract text/images from docs in a managed folder | Managed folders |
| `nlp_llm_finetuning` | Fine-tune LLM from prompt/completion data | LLM context |
| `nlp_llm_evaluation` | Evaluate LLM outputs | Evaluation stores, LLM context |
| `nlp_agent_evaluation` | Evaluate agent outputs incl. tool use | Evaluation stores, agent context |

### Code (only when the user specifically requests transformations be performed via "code")

| Type | Use when | Extra context |
| --- | --- | --- |
| `python` | External library / stateful / custom ML training | Code environment (`list_code_envs`), library files |
| `r` | R required | Code environment, library files |
| `sql_query` | Single-statement SELECT, DSS-managed output plumbing | Code environment, SQL-dataset context |
| `sql_script` | Multi-statement SQL workflow | Code environment, SQL-dataset context |
| `pyspark` | Spark required | Code environment |
| `spark_scala` | Spark Scala required | Code environment |
| `spark_sql_query` | Spark SQL required | Code environment |
| `shell` | Shell-based flow step | Code environment |

## Preferred Tools

- `get_flow_items_in_traversal_order`
- `list_recipes`
- `get_recipe_settings`
- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`

## Safety Rules

- Prefer visual recipe families unless the user explicitly requests code.
- Keep this skill focused on inspection and Cobuild grounding.
- Do not document non-Cobuild recipe mutation workflows here.
