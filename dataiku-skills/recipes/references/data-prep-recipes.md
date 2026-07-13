---
name: data-prep-recipes
description: Conceptual guide to selecting and interpreting Dataiku visual data-prep recipes for Cobuild requests.
---

# Data Prep Recipes

Read this reference when inspecting or describing a visual data-prep recipe. Use the recipe type that expresses the intended transformation directly; do not use a Code recipe unless the user explicitly requests code.

| Intent | Recipe types | Selection guidance |
| --- | --- | --- |
| Clean and enrich columns | `prepare` | Use visual processors for common parsing, cleanup, standardization, enrichment, and column changes. See the [prepare processor catalog](prepare_processors_overview.md). |
| Combine datasets | `join`, `fuzzyjoin`, `geojoin`, `vstack`, `upsert` | Use joins for keyed matching, `vstack` for appending compatible rows, and `upsert` for merging rows into a target. |
| Aggregate and reshape | `grouping`, `window`, `pivot`, `split` | Use grouping to change data grain, window calculations for partitioned analytics, pivot for long-to-wide reshaping, and split for routing rows into multiple outputs. |
| Filter and order | `sampling`, `sort`, `distinct`, `topn` | Distinguish sampling or filtering, ordering, deduplication, and selecting ranked rows. |
| Move data or files | `sync`, `download`, `export` | Use `sync` to copy data across storage backends; `download` and `export` work with managed folders. |

## Selection Notes

- Joins can multiply rows when matching keys are not unique. Inspect key columns and data grain before requesting a join.
- `fuzzyjoin` and `geojoin` need suitable text or geospatial inputs and should be validated carefully against expected match behavior.
- Aggregations change the row-level grain. State the desired grouping keys and measures explicitly in a Cobuild request.
- `pivot` changes the schema based on values in the pivot column. `split` can create several output datasets; identify the required output behavior first.
- `sync` changes storage location rather than transformation logic. Preserve the surrounding storage context unless the user requests a change.
- `download` and `export` require managed-folder context, including the intended folder and file behavior.
- Read the [formula language reference](dataiku_formula_language.md) for formula-driven preparation or filtering.
