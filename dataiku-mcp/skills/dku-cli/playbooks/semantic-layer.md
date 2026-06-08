# Semantic layer

Maps datasets to business entities, relationships, and metrics for NL→SQL. One model per domain, multiple versions per model (only active version queried). Get exact flags from `dku semantic-model <cmd> --help`.

```bash
# discover → read → modify → activate+index → verify
# list/inspect
dku semantic-model list -P PROJ
dku semantic-model get SM_REF -P PROJ
dku semantic-model versions SM_REF -P PROJ
dku semantic-model get-version SM_REF -P PROJ -o json
dku semantic-model list-entities SM_REF -P PROJ
dku semantic-model list-relationships SM_REF -P PROJ
dku semantic-model list-golden-queries SM_REF -P PROJ
dku semantic-model list-glossary SM_REF -P PROJ
dku semantic-model list-metrics SM_REF --entity ENT -P PROJ
dku semantic-model list-filters SM_REF --entity ENT -P PROJ

# create
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
dku semantic-model get-version SM_REF -P PROJ -o json > sm.json
# edit with jq
dku semantic-model set-version SM_REF -d @sm.json -P PROJ
```

Use this for fields `add-*` doesn't cover: `sqlGenerationConfig`, `foreignKeys`, attribute descriptions.

## Gotchas

- `list` first — DSS assigns IDs that may not match the name
- `create-version` materializes the settings doc so `get-version` should work
  immediately. If an older DSS build still returns a lazy-materialization 404,
  run `set-version -d '{}'` once and retry.
- `set-version` is shallow merge, NOT full replace. Clear a list explicitly: `"entities": []`
- `distinctValuesHandlingMode`: `NONE` (IDs/measures), `AUTO_INDEX` (filterable dims), `MANUAL` (curated via `set-manual-values`)
- `datasetRef` in JSON payload uses `PROJECT_KEY.DATASET_NAME`; `--from-dataset` takes just the dataset name
- `--from-dataset` requires a dataset with a defined schema. Build first, or use `set-version` JSON to define entities manually
- Removing an entity cascades to its relationships
- `delete` model is tier-2 (`--yes`); remove-* commands are unguarded
- Indexing is per-version — `set-active-version` then `update-index`
- Only `indexDistinctValues=true` attributes are indexed
