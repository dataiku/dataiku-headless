# Pandas ETL Migration Fixtures

A Python pandas script performing load, clean, transform, aggregate, and sort operations. Tests whether an AI agent migrates this to Dataiku visual recipes instead of writing a Python recipe.

## Files

| File | Rows | Description |
|------|------|-------------|
| `input.csv` | 200 | Transactions with nulls in amount and mixed statuses |
| `script.py` | - | The pandas script to migrate to Dataiku |
| `expected_output.csv` | 25 | Aggregated output (category x region) |

## Schema: input.csv

| Column | Type | Description |
|--------|------|-------------|
| tx_id | string | Transaction ID (TX00001-TX00200) |
| user_id | string | User ID (U001-U050) |
| amount | float (nullable) | Transaction amount (~10% are null/empty) |
| category | string | Electronics, Clothing, Food, Services, Travel |
| timestamp | datetime | ISO format (2025-MM-DDThh:mm:00) |
| status | string | completed (~70%), pending (~15%), refunded (~15%) |
| region | string | US-East, US-West, EU-North, EU-South, APAC |

## Schema: expected_output.csv

| Column | Type | Description |
|--------|------|-------------|
| category | string | Product category |
| region | string | Geographic region |
| total_amount | float | Sum of amount |
| avg_amount | float | Mean of amount |
| tx_count | int | Count of transactions |

Sorted by total_amount descending.

## Pipeline Steps (from script.py)

1. **Load**: Read input.csv
2. **Clean**: Drop rows where amount is null
3. **Filter**: Keep only rows where status = "completed"
4. **Aggregate**: Group by (category, region), compute sum/mean/count of amount
5. **Sort**: Order by total_amount descending

## Dataiku Visual Recipe Mapping

| Pandas Step | Dataiku Recipe | Notes |
|-------------|---------------|-------|
| `dropna(subset=["amount"])` | Prepare: filter rows where amount is empty | Or Filter recipe |
| `df[df["status"] == "completed"]` | Prepare: filter rows or Filter recipe | status == "completed" |
| `groupby().agg()` | Group recipe | Keys: category, region. Aggregations: sum, avg, count on amount |
| `sort_values()` | Sort recipe | Sort by total_amount descending |

The month column extraction in the script is NOT used in the final output -- it can be ignored unless a scenario specifically tests it.

## Data Characteristics

- ~14 rows have null/empty amounts (will be dropped)
- ~139 rows are "completed" status
- After both filters: ~129 rows remain for aggregation
- 5 categories x 5 regions = up to 25 output rows
