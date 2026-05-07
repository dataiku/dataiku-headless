# Flow organization

Any non-trivial DSS project produces dozens of recipes and datasets — migrations especially can hit 30–80. A flat flow at that size is unreadable, and a flow nobody can read is a flow nobody can extend. Organize as you build, not in a post-hoc cleanup pass. The CLI verbs covered here: `dku flow zones`, `dku flow move`, `dku wiki create`, `dku dataset set-metadata`, `dku project ai-describe`, `dku dataset ai-describe`.

## Zones

`dku flow zones` and `dku flow move` operate on the project's flow graph. Pick a zoning convention up front and apply it after each recipe runs.

Two conventions work well — pick one, stick with it.

### By stage (default)

```
ingest      — uploaded files, raw datasets, sync/landing recipes
prepare     — Prepare and Filter recipes that clean / cast / split
join        — Joins, including cross-connection landings
aggregate   — Group, Window, Pivot
output      — final datasets, exports, dashboards
```

Best for linear flows where every record passes through the same five stages. Reviewers can scan left-to-right.

### By functional area (large projects)

```
credit_risk
collateral
reporting
shared_lookups
```

Best when a single migration spans multiple business domains and the linear-stage view becomes meaningless ("aggregate" contains 30 group recipes from 6 different domains).

### When to use both

Nest functional zones inside stage zones, or vice versa. Don't try to express both axes at the same level.

## Recipe naming

Default DSS recipe names (`compute_<output>`, `prepare_<n>`) are forgettable. Rename as you go:

| Replace | With |
|---|---|
| `compute_he_clean` | `clean_homeequity` |
| `compute_joined_3` | `join_homeequity_to_us_data` |
| `compute_grouped_4` | `aggregate_by_state` |
| `compute_filter_active` | `filter_active_accounts` |

Verb-first, short, descriptive. The output dataset name should generally NOT match the recipe name — recipe describes the *action*, dataset describes the *thing*.

## Dataset descriptions

Every dataset deserves a one-liner. Bootstrap with AI, then refine the ones that matter:

```bash
dku dataset ai-describe DATASET -P PROJ --save           # AI-generated short_desc
dku dataset set-metadata DATASET -P PROJ --short-desc "Cleaned home equity loans (LTV ≥ 0.8 only)"
```

Reviewers reading the flow graph see these as hover-tooltips. Datasets with no description force them to open the dataset in a separate tab to figure out what it is — that's friction you can save them.

## Project wiki

Before reporting a project "done" (built, migrated, refactored), create at least one wiki article:

```bash
dku project ai-describe -P PROJ --save                   # AI-generated long_desc
dku wiki create -P PROJ --title "Project map" --content @project-map.md
```

Minimum content depends on what the project is:

- **Built from scratch:** purpose, data sources, flow stages, runbook (how to rebuild, expected runtime).
- **Migration:** source layout, step-to-recipe map (the same table from the migration plan, refined with final names), deviations (skipped steps, alternative implementations, edge cases handled differently), runbook.

The wiki is the artifact a future engineer reads when the original author has long since moved on. Don't skip it.

## Auto-bootstrap order

If the project is large and descriptions/wiki feel onerous, do them in this order:

1. After every recipe run: `dku dataset set-metadata --short-desc <one-line>` immediately, while the recipe is fresh in your head.
2. When the flow is feature-complete: `dku project ai-describe --save` for the project-level description.
3. After (2): `dku dataset ai-describe --save` for any dataset you didn't write a description for in (1) — bulk over the survivors.
4. Manual wiki article as the final step — AI can't write the deviation/decision list because those are choices only the author made.
