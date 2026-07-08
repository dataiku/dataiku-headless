# Semantic Layer Playbook

Maps datasets to business entities, relationships, and metrics for NL→SQL. One model per domain, multiple versions per model (only active version queried).

Entities must point at **SQL-backed datasets** — Filesystem/UploadedFiles sources fail at query time with a polite refusal ("not accessible via SQL"); sync to a SQL connection first and point the entity at the synced dataset (`references/mlops.md` § Semantic models).

## Canonical commands

```bash
# golden order: describe datasets → create → entities → relationships → glossary/metrics/golden-queries → activate+index → verify
# list/inspect
dku semantic-model list -P PROJ
dku semantic-model get SM_REF -P PROJ
dku semantic-model versions SM_REF -P PROJ
dku --format json semantic-model get-version SM_REF -P PROJ
dku semantic-model list-entities SM_REF -P PROJ
dku semantic-model list-relationships SM_REF -P PROJ
dku semantic-model list-golden-queries SM_REF -P PROJ
dku semantic-model list-glossary SM_REF -P PROJ
dku semantic-model list-metrics SM_REF --entity ENT -P PROJ
dku semantic-model list-filters SM_REF --entity ENT -P PROJ

# create — describe datasets FIRST: add-entity snapshots their schema, so
# descriptions only flow in if they exist before the entity is created
dku dataset ai-describe DS --save -P PROJ
dku semantic-model create "Model Name" -P PROJ
dku semantic-model create-version SM_REF v2 -P PROJ
dku semantic-model create-version SM_REF v2 --duplicate-of v1 -P PROJ

# add structure
dku semantic-model add-entity SM_REF --from-dataset DS --name "customer" --pk CustomerID --index-values Name,Email -P PROJ
dku semantic-model add-relationship SM_REF --from customer --to orders --on CustomerID -P PROJ
dku semantic-model add-relationship SM_REF --from a --to b --expression "LOWER(left.email) = LOWER(right.email)" -P PROJ
dku semantic-model add-metric SM_REF --entity customer --name "Total Customers" --expression "COUNT(CustomerID)" -P PROJ
dku semantic-model add-filter SM_REF --entity customer --name "Active" --expression "Status = 'active'" -P PROJ
dku semantic-model add-golden-query SM_REF --name "monthly revenue" --question "What was revenue by product last month?" --sql "SELECT ..." -P PROJ
dku semantic-model add-glossary-term SM_REF --term "customer" --description "..." --synonyms "client,account,buyer" -P PROJ
dku semantic-model sync-descriptions SM_REF -P PROJ   # backfill entity+attribute descriptions if datasets were described after add-entity

# configure
dku semantic-model set-manual-values SM_REF --entity customer --attribute Status --values "Active,Inactive" -P PROJ
dku semantic-model set-manual-values SM_REF --entity customer --attribute Status --clear -P PROJ

# activate + index
dku semantic-model set-active-version SM_REF v2 -P PROJ
dku semantic-model update-index SM_REF --wait -P PROJ

# remove (model delete is tier-2, --yes required)
dku semantic-model delete SM_REF -P PROJ --yes
dku semantic-model remove-entity SM_REF ENT -P PROJ
dku semantic-model remove-relationship SM_REF --from ENT1 --to ENT2 -P PROJ
dku semantic-model remove-metric SM_REF --entity ENT --name METRIC -P PROJ
dku semantic-model remove-filter SM_REF --entity ENT --name FILTER -P PROJ
dku semantic-model remove-glossary-term SM_REF --term TERM -P PROJ
dku semantic-model remove-golden-query SM_REF --name NAME -P PROJ

# distinct values
dku semantic-model distinct-values SM_REF -P PROJ
dku semantic-model distinct-values SM_REF --entity ENT --attribute ATTR -P PROJ
```

## Bulk edit via `set-version` (shallow merge)

```bash
dku --format json semantic-model get-version SM_REF -P PROJ > sm.json
# edit with jq
dku semantic-model set-version SM_REF -d @sm.json -P PROJ
```

Payload shapes for fields `add-*` doesn't cover: `../references/semantic-models.md`.

## Gotchas

- `list` first — DSS assigns IDs that may not match the name
- Entities are a **snapshot**, not a live link: `add-entity` copies column
  descriptions (schema `comment` field — what `dataset ai-describe --save` and
  `set-column-description` write) and the dataset `shortDesc` at creation time,
  and never re-reads them. Describe datasets first; backfill a late model with
  `sync-descriptions`. The `described` column of `list-entities` is the
  coverage gate — `0/N` means text2SQL runs without column context.
- Column descriptions survive sync recipes (CSV → SQL), but dataset-level
  `shortDesc` does not — so run `ai-describe` on the SQL dataset the entity
  points at (not just the upstream upload), or entity descriptions stay empty.
- `create-version` materializes the settings doc so `get-version` should work
  immediately. `set-version` returns a lazy-materialization 404 → run
  `dku semantic-model set-version -d '{}'` once and retry.
- `set-version` is shallow merge, NOT full replace. Clear a list explicitly: `"entities": []`
- `distinctValuesHandlingMode` semantics: `../references/semantic-models.md`.
- `datasetRef` in JSON payload uses `PROJECT_KEY.DATASET_NAME`; `--from-dataset` takes just the dataset name
- `--from-dataset` requires a dataset with a defined schema. Build first, or use `set-version` JSON to define entities manually
- Removing an entity cascades to its relationships
- `delete` model is tier-2 (`--yes`); remove-* commands are unguarded
- Indexing is per-version — `set-active-version` then `update-index`
- Only `indexDistinctValues=true` attributes are indexed

## Done when

- `dku semantic-model list-entities SM_REF -P PROJ` shows `described` coverage at `N/N`, not `0/N`.
- `dku semantic-model versions SM_REF -P PROJ` shows the intended version as active.
- Golden queries return the expected rows when run through the Semantic Model Query agent tool (or `dku semantic-model list-golden-queries SM_REF -P PROJ` matches what you added).
