---
name: data-prep-recipes
description: Select and interpret Dataiku visual data-prep recipes, including their embedded pre-filters, computed columns, aggregations, post-filters, and output controls, for grounded Cobuild requests.
---

# Data Prep Recipes

Read this reference when inspecting or describing a visual data-prep recipe. Use the recipe type that expresses the intended transformation directly; do not use a Code recipe unless the user explicitly requests code.

| Intent | Recipe types | Selection guidance |
| --- | --- | --- |
| Clean and enrich columns | `prepare` | Use visual processors for common parsing, cleanup, standardization, enrichment, and column changes. See the [prepare processor catalog](../shared/prepare_processors_overview.md). |
| Combine datasets | `join`, `fuzzyjoin`, `geojoin`, `vstack`, `upsert` | Use joins for keyed matching, `vstack` for appending compatible rows, and `upsert` for merging rows into a target. |
| Aggregate and reshape | `grouping`, `window`, `pivot`, `split` | Use grouping to change data grain, window calculations for partitioned analytics, pivot for long-to-wide reshaping, and split for routing rows into multiple outputs. |
| Filter and order | `prepare`, `sampling`, `sort`, `distinct`, `topn` | Use a Prepare filter processor or a compatible recipe's embedded pre/post-filter for row filtering. Reserve `sampling` for actual sampling; use the other recipes for ordering, deduplication, and selecting ranked rows. |
| Move data or files | `sync`, `download`, `export` | Use `sync` to copy data across storage backends; `download` and `export` work with managed folders. |

## Embedded Recipe Stages

Several visual recipes contain processing stages around their named action. Inspect the full `payload` from `get_recipe_settings`; do not assume that one Flow node contains only the core action.

| Recipe types | Embedded capabilities |
| --- | --- |
| `grouping` | Top-level `preFilter` and `computedColumns`; grouping keys; standard aggregations or SQL-engine custom aggregations using `customExpr` and `customName`; top-level `postFilter`; output selection and name overrides. |
| `window` | Top-level `preFilter` and `computedColumns`; window definitions and values; window-wide `globalAggregations`; top-level `postFilter`; retrieved-column selection. |
| `join`, `fuzzyjoin` | Per-input `virtualInputs[].preFilter` and computed columns; join action; top-level post-join computed columns that can use both inputs; top-level `postFilter`; selected output columns. |
| `sort`, `distinct`, `topn` | Top-level `preFilter` and `computedColumns`; ordering, deduplication, ranking, or row-limit action; top-level `postFilter`; output controls. |
| `vstack` | Per-input pre-filters; computed columns; schema remapping and optional origin column; top-level `postFilter`. |
| `split` | Top-level `preFilter` and `computedColumns`; split conditions and catch-all output; top-level `postFilter`. |

A pre-filter runs before the action and can change join inputs, group membership, aggregate denominators, or window partitions. A post-filter evaluates action output and can reference generated aggregate or joined columns. Do not move a condition between them unless it is equivalent at both grains.

Use one recipe when its embedded capabilities express the transformation and no intermediate result needs to be delivered, reused, audited, or run with a different engine. After Cobuild work, re-read the payload, build the output, and validate its schema, sample values, row count, and grain.

## Selection Notes

- Joins can multiply rows when matching keys are not unique. Inspect key columns and data grain before requesting a join.
- `fuzzyjoin` and `geojoin` need suitable text or geospatial inputs and should be validated carefully against expected match behavior.
- Aggregations change the row-level grain. State the desired grouping keys, standard or custom measures, pre-aggregation computed columns, and any post-aggregation filter explicitly in a Cobuild request.
- A Sampling recipe is not a general row filter. Use `FilterOnCustomFormula` or another appropriate Prepare filter processor when no compatible recipe-level pre/post-filter owns the condition.
- `pivot` changes the schema based on values in the pivot column. `split` can create several output datasets; identify the required output behavior first.
- `sync` changes storage location rather than transformation logic. Preserve the surrounding storage context unless the user requests a change.
- `download` and `export` require managed-folder context, including the intended folder and file behavior.
- Read the [formula language reference](../shared/dataiku_formula_language.md) for formula-driven preparation or filtering.
