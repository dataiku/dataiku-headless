---
name: data-prep-recipes
description: Conceptual guide to selecting and interpreting Dataiku visual data-prep recipes for Cobuild requests.
---

# Data Prep Recipes

Read this reference when inspecting or describing a visual data-prep recipe. Use the recipe type that expresses the intended transformation directly; do not use a Code recipe unless the user explicitly requests code.

| Intent | Recipe types | Selection guidance |
| --- | --- | --- |
| Clean and enrich columns | `prepare` | Use visual processors for common parsing, cleanup, standardization, enrichment, and column changes. See the [prepare processor catalog](../shared/prepare_processors_overview.md). |
| Combine datasets | `join`, `fuzzyjoin`, `geojoin`, `vstack`, `upsert` | Use joins for keyed matching, `vstack` for appending compatible rows, and `upsert` for merging rows into a target. |
| Aggregate and reshape | `grouping`, `window`, `pivot`, `split` | Use grouping to change data grain, window calculations for partitioned analytics, pivot for long-to-wide reshaping, and split for routing rows into multiple outputs. |
| Filter and order | `sampling`, `sort`, `distinct`, `topn` | Distinguish sampling or filtering, ordering, deduplication, and selecting ranked rows. |
| Move data or files | `sync`, `download`, `export` | Use `sync` to copy data across storage backends; `download` and `export` work with managed folders. |

## Embedded Recipe Stages

Several visual recipes contain processing stages around their named action. Inspect the full `payload` from `get_recipe_settings`; do not assume that one Flow node contains only the core action.

| Stage | Purpose and effect |
| --- | --- |
| Input pre-filter | Removes rows before the core action. It can change join inputs, group membership, aggregate denominators, or window partitions. |
| Pre-action computed columns | Derives or changes columns available to the core action. |
| Core action | Performs the recipe's named operation, such as joining, grouping, ranking, or splitting. |
| Post-action computed columns | Derives columns from the action result. For joins, these can use columns from both inputs. |
| Post-filter | Removes rows after the core action and can filter generated aggregate or joined columns. |
| Output controls | Select, rename, map, or otherwise shape delivered output columns. |

Do not move a condition between stages unless it is equivalent at both grains.

| Recipe types | Input pre-filter | Pre-action computed columns | Core action and other features | Post-action computed columns | Post-filter | Output controls |
| --- | --- | --- | --- | --- | --- | --- |
| `grouping` | Yes | Yes | Grouping keys; standard or SQL-engine custom aggregations | — | Yes | Selection and name overrides |
| `window` | Yes | Yes | Window definitions and values; window-wide global aggregations | — | Yes | Retrieved-column selection |
| `join`, `fuzzyjoin` | Per input | Per input | Join action | Yes | Yes | Selected columns |
| `sort`, `distinct`, `topn` | Yes | Yes | Ordering, deduplication, ranking, or row limits | — | Yes | Yes |
| `vstack` | Per input | Yes | Schema mapping and optional origin column | — | Yes | — |
| `split` | Yes | Yes | Split conditions and catch-all output | — | Yes | — |

Prefer one recipe when its embedded capabilities express the transformation and separating it provides no material operational, performance, governance, or reuse benefit.

## Selection Notes

- Joins can multiply rows when matching keys are not unique. Inspect key columns and data grain before requesting a join.
- `fuzzyjoin` and `geojoin` need suitable text or geospatial inputs and should be validated carefully against expected match behavior.
- Aggregations change the row-level grain. State the desired grouping keys, standard or custom measures, pre-aggregation computed columns, and any post-aggregation filter explicitly in a Cobuild request.
- `pivot` changes the schema based on values in the pivot column. `split` can create several output datasets; identify the required output behavior first.
- `sync` changes storage location rather than transformation logic. Preserve the surrounding storage context unless the user requests a change.
- `download` and `export` require managed-folder context, including the intended folder and file behavior.
- Read the [formula language reference](../shared/dataiku_formula_language.md) for formula-driven preparation or filtering.
