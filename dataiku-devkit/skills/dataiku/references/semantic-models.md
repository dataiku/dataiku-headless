# Semantic Models — Schema Reference

> Semantic models map business context onto datasets so that the **Semantic Model Query** agent tool can turn natural-language questions into SQL. DSS 14.4+.

## Why this doc exists

`dataikuapi.dss.semantic_model` exposes entities/relationships/golden queries/glossary as **opaque `dict`s** with no inner class definitions. The DSS public docs describe these concepts but do not publish the JSON schema. This file captures the verified shapes so agents don't have to guess.

**Source of truth:** live instances of DSS 14.4.3. When in doubt, build one example in the UI and run:

```bash
dku semantic-model get-version SM_ID -P PROJECT -o json
```

---

## Workflow (the only reliable path)

1. **Establish in UI first.** Create the semantic model, one entity, one relationship via the DSS Semantic Model editor. This is the only way to see exactly how DSS stores the shape.
2. **Export.** `dku semantic-model get-version SM -P PROJ -o json > sm.json`
3. **Templatize.** Use the exported JSON as a template. Bulk-edit with `jq` or a scripted loop, not hand-written JSON.
4. **Apply.** `dku semantic-model set-version SM --version v1 --definition @sm.json -P PROJ`
5. **Activate.** `dku semantic-model set-active-version SM v1 -P PROJ` — the text-to-SQL tool uses the ACTIVE version only.
6. **Index.** `dku semantic-model update-index SM --wait -P PROJ` — without this, distinct-value resolution is stale.

**Do not guess relationship shapes.** `firstEntity` vs `leftEntity` vs `fromEntity` — all three are plausible; only one is correct. Export first.

## Full from-scratch workflow (no UI needed, verified DSS 14.4.3)

**Preferred: splice-level verbs.** No JSON hand-coding, no shallow-merge hazard:

```bash
PROJ=MY_PROJECT
SM_NAME="My Model"

# 1. Create the SM container (no versions yet).
dku semantic-model create "$SM_NAME" -P $PROJ
SM_ID=$(dku semantic-model list -P $PROJ -o json | jq -r ".[] | select(.name==\"$SM_NAME\") | .id")

# 2. Create a blank version. IMPORTANT: `create` does NOT auto-create one.
dku semantic-model create-version $SM_ID v1 -P $PROJ

# 3. Activate it NOW so later commands can omit --version.
dku semantic-model set-active-version $SM_ID v1 -P $PROJ

# 4. Add entities — schema auto-generated from dataset column metadata.
dku semantic-model add-entity $SM_ID --from-dataset Customers \
  --pk CustomerID --index-values Name,RiskTolerance -P $PROJ

dku semantic-model add-entity $SM_ID --from-dataset Orders \
  --pk OrderID --index-values ProductName -P $PROJ

# 5. Add relationships. --on for simple equi-joins; --expression for custom predicates.
dku semantic-model add-relationship $SM_ID --from customers --to orders \
  --on CustomerID -P $PROJ

# Composite join key:
# dku semantic-model add-relationship $SM_ID --from account_monthly --to usage_monthly \
#   --on ACCOUNT_SK,MONTH -P $PROJ

# 6. Add glossary terms (auto-UUIDs).
dku semantic-model add-glossary-term $SM_ID \
  --term ARR --description "Annual Recurring Revenue" \
  --synonyms "annual recurring revenue,subscription revenue" -P $PROJ

# 7. Metrics & filters (pseudo-SQL). These give the text-to-SQL agent
# approved aggregates/predicates to compose. Without them it hand-rolls SQL
# from raw columns, which is lower quality.
dku semantic-model add-metric $SM_ID --entity customers \
  --name "Total Customers" --expression "COUNT(CustomerID)" -P $PROJ
dku semantic-model add-filter $SM_ID --entity customers \
  --name "Subscribed" --expression "Subscribed = 'true'" -P $PROJ

# 8. Curated manual values on categorical attributes. Flips the attribute to
# MANUAL mode and enables fuzzy resolution (user says "high risk" →
# RiskTolerance = 'High'). Use --clear to revert.
dku semantic-model set-manual-values $SM_ID --entity customers \
  --attribute RiskTolerance --values "Low,Medium,High" -P $PROJ

# 9. Golden queries — NL→SQL few-shot examples. Biggest single driver of quality.
dku semantic-model add-golden-query $SM_ID \
  --name "count subscribers" \
  --question "How many subscribed customers do we have?" \
  --sql "SELECT COUNT(*) FROM Customers WHERE Subscribed='true'" -P $PROJ

# 10. Verify.
dku semantic-model list-entities $SM_ID -P $PROJ
dku semantic-model list-relationships $SM_ID -P $PROJ
dku semantic-model list-glossary $SM_ID -P $PROJ
dku semantic-model list-metrics $SM_ID --entity customers -P $PROJ
dku semantic-model list-filters $SM_ID --entity customers -P $PROJ
dku semantic-model list-golden-queries $SM_ID -P $PROJ

# 11. Index distinct values (async — use --wait to block).
dku semantic-model update-index $SM_ID --wait -P $PROJ
```

**Fallback: raw JSON via `set-version`.** Use only for bulk changes or top-level fields (description, indexingSettings):

```bash
dku semantic-model get-version $SM_ID -P $PROJ -o json > sm.json
# bulk edit sm.json with jq/python
dku semantic-model set-version $SM_ID --version v1 --definition @sm.json -P $PROJ
```

⚠ `set-version` shallow-merges at the top level. Passing `{"relationships": [...]}` alone **replaces the whole array** — always read current state, edit, save back.

### Ordering gotchas (verified)

- **`create` does NOT auto-create a version.** A freshly created SM has `versions: []`. `get-version` will fail until you `create-version`.
- **`set-version` without `--version` fails when no active version is set.** On a new SM, either pass `--version v1` explicitly or `set-active-version v1` first. The CLI emits a prescriptive error, but agents sometimes retry without reading — always pass `--version` explicitly on the first `set-version` of a new SM.
- **Text-to-SQL agents only read the ACTIVE version.** Forgetting `set-active-version` is the #1 cause of "my model isn't being used."
- **`update-index` must run after any change to entities or `manualValues`.** The indexer is the source of truth for value resolution.

---

## Top-level version shape

```json
{
  "id": "v1",
  "description": "",
  "created": { "on": "ISO-8601", "by": "username" },
  "entities": [ /* see Entity */ ],
  "relationships": [ /* see Relationship */ ],
  "goldenQueries": [ /* see Golden Query */ ],
  "glossaryTerms": [ /* see Glossary Term */ ],
  "glossaryBindings": [ /* shape unknown — empty in observed samples */ ],
  "indexingSettings": {
    "maxDistinctValuesPerAttribute": 1000,
    "maxScannedRowsForSQLDatasets": -1,
    "maxScannedRowsForNonSQLDatasets": 1000000
  },
  "privateEditorData": {
    "indexingStale": false,
    "lastSavedAt": "ISO-8601",
    "lastIndexedAt": "ISO-8601"
  },
  "sqlGenerationConfig": {}
}
```

- `privateEditorData` is server-managed. Do not hand-edit.
- `indexingSettings.maxScannedRowsForSQLDatasets = -1` means "no limit". For non-SQL the default cap is 1M rows.

---

## Entity

```json
{
  "name": "customer",
  "description": "Represents individual customers: profile, subscription, engagement metrics.",
  "tags": [],
  "type": "DATASET",
  "datasetRef": "PROJECT_KEY.DATASET_NAME",
  "metrics": [
    {
      "name": "Total Customers",
      "description": "Total number of customer records",
      "pseudoSQLExpression": "COUNT(CustomerID)",
      "created": {}
    }
  ],
  "filters": [
    {
      "name": "Subscribed = true",
      "description": "Filters to customers who are currently subscribed",
      "pseudoSQLExpression": "Subscribed = 'true'",
      "created": {}
    }
  ],
  "primaryKey": { "attributes": ["CustomerID"] },
  "foreignKeys": [],
  "attributes": [
    {
      "name": "RiskTolerance",
      "dssType": "string",
      "type": "COLUMN",
      "column": "RiskTolerance",
      "distinctValuesHandlingMode": "MANUAL",
      "manualValues": ["Low", "Medium", "High"],
      "indexDistinctValues": true,
      "resolveInUserRequests": true,
      "sqlGenerationConfig": {}
    }
  ]
}
```

### Key points

- **`type: "DATASET"`** is the only observed entity type so far.
- **`datasetRef`** must be fully qualified: `PROJECT_KEY.DATASET_NAME`.
- **`metrics`** and **`filters`** are *named pseudoSQL expressions* — the agent uses them as pre-approved ways to aggregate/filter. Write SQL fragments, not GREL.
  - A metric's `pseudoSQLExpression` is an aggregate: `COUNT(...)`, `SUM(...)`, `AVG(...)`, `COUNT(DISTINCT ...)`, conditional `COUNT(CASE WHEN ... THEN col END)`.
  - A filter's `pseudoSQLExpression` is a predicate: `col = 'value'`, `col >= CURRENT_DATE - INTERVAL '30 days'`.
- **`primaryKey.attributes`** is a list of attribute *names* (not column names), forming the PK. Usually a single-element list.
- **`foreignKeys`** — shape unknown from observed samples (always empty). **Action:** create one in the UI next time, export to update this doc.
- **`attributes`** — each column or computed attribute.
  - `dssType`: observed values `"string"`, `"bigint"`. Expect the full DSS type set (`double`, `boolean`, `date`, `int`, `float`, etc.).
  - `type: "COLUMN"` means a direct dataset column — there may be a `"COMPUTED"` variant for expressions, not yet observed.
  - `column` — the actual column name in the underlying dataset.
  - `distinctValuesHandlingMode: "NONE" | "MANUAL"` — if `"MANUAL"`, `manualValues[]` is used; if `"NONE"`, the indexer populates values (controlled by `indexDistinctValues`).
  - `manualValues` — hand-curated enum for categorical columns. Massively improves text-to-SQL value resolution.
  - `indexDistinctValues: true` — indexer scans the dataset to learn distinct values. Triggered by `dku semantic-model update-index`.
  - `resolveInUserRequests: true` — enables fuzzy/semantic matching of user-supplied value strings against distinct values at query time.

---

## Relationship ⚠ SIMPLER THAN YOU THINK

```json
{
  "firstEntity": "customer",
  "secondEntity": "investment_product",
  "pseudoSQLExpression": "left.CustomerID = right.CustomerID"
}
```

**That's it.** Three fields. Captured from a UI-created relationship on DSS 14.4.3.

### Key points

- **`firstEntity` / `secondEntity`** — entity *names* (matching `entity.name`), not IDs, not `datasetRef`.
- **`pseudoSQLExpression`** is a SQL predicate. Use the aliases `left` (= `firstEntity`) and `right` (= `secondEntity`):
  - Simple: `"left.CustomerID = right.CustomerID"`
  - Composite: `"left.ACCOUNT_SK = right.ACCOUNT_SK AND left.MONTH = right.MONTH"`
  - Computed: `"LOWER(left.email) = LOWER(right.email)"`
- **No cardinality field.** DSS infers cardinality from each entity's `primaryKey` and `foreignKeys`. If you need JOINs to behave a certain way, ensure the `primaryKey.attributes` on each entity is correct.
- **No `id` field on relationships.** They're identified by the `(firstEntity, secondEntity)` pair. Adding a duplicate pair is undefined behavior — dedupe before saving.
- **Symmetry.** The join expression is symmetric in naming, but direction matters for interpretation (which side is the "one" in a one-to-many). Use `primaryKey` on the "one" side.

### Chaining example (bulk append)

```bash
# 1. Export current version
dku semantic-model get-version OgATbkw -P MY_PROJ -o json > sm.json

# 2. Append relationships with jq
jq '.relationships += [
  {"firstEntity":"customer","secondEntity":"sales_opportunity","pseudoSQLExpression":"left.CustomerID = right.CustomerID"},
  {"firstEntity":"sales_opportunity","secondEntity":"sales_call","pseudoSQLExpression":"left.OpportunityID = right.OpportunityID"}
]' sm.json > sm_updated.json

# 3. Apply
dku semantic-model set-version OgATbkw --definition @sm_updated.json -P MY_PROJ

# 4. Reindex
dku semantic-model update-index OgATbkw --wait -P MY_PROJ
```

---

## Golden Query

Hand-curated NL → SQL examples the agent can reference.

```json
{
  "name": "monthly revenue by product",
  "question": "What was revenue by product last month?",
  "generatedSql": "SELECT p.ProductName, SUM(o.Amount) FROM orders o JOIN products p ON o.ProductID = p.ProductID WHERE o.Date >= CURRENT_DATE - INTERVAL '1 month' GROUP BY p.ProductName",
  "created": { "on": "ISO-8601" }
}
```

- `created` is set server-side — `{}` is accepted on write.
- `generatedSql` is the *target* SQL for that question — used as a few-shot example, not as a query template.

---

## Glossary Term

```json
{
  "id": "uuid",
  "term": "ARR",
  "description": "Annual Recurring Revenue",
  "source": "MANUAL",
  "userModified": true,
  "created": { "on": "ISO-8601" },
  "synonyms": ["annual recurring revenue", "yearly subscription revenue"],
  "privateEditorData": {}
}
```

- `id` — UUID. Server generates on create; re-using an existing UUID updates in place.
- `source`: `"MANUAL"` observed. Other values may exist (e.g. `"IMPORTED"`) — not confirmed.
- `synonyms` massively improve agent recognition — list colloquial forms, abbreviations, misspellings.

---

## Glossary Binding

Shape unknown — always empty in observed samples. Bindings tie glossary terms to entity attributes. **Action:** create one in the UI and re-export to complete this reference.

---

## `sqlGenerationConfig`

Observed: `{}` (empty). Likely contains per-model SQL dialect hints. Shape to be confirmed when populated examples appear.

---

## Semantic Model Gotchas

| Symptom | Root cause | Fix |
|---|---|---|
| 400 or silent no-op from `set-version` with relationship JSON | Guessed wrong field names (`leftEntity` instead of `firstEntity`) | Use verified shape above |
| Old relationships disappeared after `set-version --definition '{"relationships":[...]}'` | `set-version` shallow-merges at the version level — passing `relationships` REPLACES the whole array | Read current, append, save; or use a future `dku semantic-model add-relationship` helper |
| Text-to-SQL agent returns no rows for value queries ("customers with High risk") | `indexDistinctValues: false` or stale index | Set `indexDistinctValues: true`, run `update-index --wait` |
| Text-to-SQL agent invents join keys | No relationship defined between the two entities; agent guesses | Add relationship with explicit `pseudoSQLExpression` |
| Metric returns literal SQL not computed value | Metric lives under `entity.metrics`, not `entity.attributes` | Put aggregates in `metrics`, filterable expressions in `filters` |
| Entity has no `primaryKey` | Entity still saves, but cardinality inference breaks | Always set `primaryKey.attributes` |

---

## CLI coverage matrix (as of 2026-04)

| Shape | Dedicated splice verb | Fallback |
|---|---|---|
| Entity (with auto-scanned attributes) | `add-entity --from-dataset` / `remove-entity` / `list-entities` | — |
| Entity metric (pseudoSQL aggregate) | `add-metric` / `remove-metric` / `list-metrics` | — |
| Entity filter (pseudoSQL predicate) | `add-filter` / `remove-filter` / `list-filters` | — |
| Attribute `manualValues` + mode | `set-manual-values --values \| --clear` | — |
| Relationship | `add-relationship --on \| --expression` / `remove-relationship` / `list-relationships` | — |
| Glossary term | `add-glossary-term` / `remove-glossary-term` / `list-glossary` | — |
| Golden query | `add-golden-query` / `remove-golden-query` / `list-golden-queries` | — |
| Distinct-values index | `update-index --wait` / `distinct-values` (read) | — |
| Version top-level (`description`, `indexingSettings`) | — | `set-version --definition '{"description":"..."}'` (shallow merge at top level) |
| Delete version | — | Delete whole SM + recreate |
| `foreignKeys[]` on entity | — | Schema unknown; hand-edit via `set-version` once shape captured |
| `glossaryBindings[]` | — | Schema unknown; ditto |
| `sqlGenerationConfig` (attribute + version) | — | Shape unknown (`{}` in all samples); ditto |

## Open questions (to confirm with future UI exports)

- `foreignKeys[]` inner shape (assumed `{"attributes": ["FK_COL"], "referencedEntity": "other", "referencedAttributes": ["PK_COL"]}` — unverified)
- `glossaryBindings[]` inner shape
- Full set of `source` values on `glossaryTerms`
- `attribute.type` values besides `"COLUMN"` (e.g. computed?)
- `entity.type` values besides `"DATASET"`
- `sqlGenerationConfig` populated shape

When you hit one of these in a real project, export and update this file.
