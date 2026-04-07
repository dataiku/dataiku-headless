# Alteryx Customer Segmentation Fixtures

Simulates an Alteryx Designer workflow that computes RFM customer segmentation. Used to test whether an AI agent can translate a non-Dataiku workflow specification into Dataiku visual recipes.

## Files

| File | Rows | Description |
|------|------|-------------|
| `input.csv` | 100 | Customer metrics: spend, order count, recency, channel |
| `workflow_spec.md` | - | Natural-language description of the Alteryx workflow |
| `expected_output.csv` | 90 | Computed RFM scores, segments, LTV, at-risk flags |

## Schema: input.csv

| Column | Type | Description |
|--------|------|-------------|
| customer_id | string | Unique ID (AC0001-AC0100) |
| name | string | Full name |
| total_spend_12mo | float | Total spend in last 12 months ($0-$15,000) |
| order_count_12mo | int | Number of orders in last 12 months (0-40) |
| avg_order_value | float | Average order value (derived from spend/count) |
| days_since_last_order | int | Days since most recent order (1-400) |
| region | string | Northeast, Southeast, Midwest, West, Southwest |
| channel | string | online, retail, partner |
| signup_date | date | YYYY-MM-DD, range 2022-01 to 2024-09 |

## Schema: expected_output.csv

| Column | Type | Description |
|--------|------|-------------|
| customer_id | string | Same as input |
| name | string | Same as input |
| rfm_score | int | Composite RFM score (3-15) |
| segment | string | Gold (12-15), Silver (8-11), Bronze (3-7) |
| lifetime_value | float | avg_order_value * order_count * 3 |
| at_risk | boolean | True if (Gold or Silver) AND days_since > 60 |

## Data Distribution

The input data has intentional distribution patterns:
- 10 high spenders ($5k-$15k, 15-40 orders, recent activity)
- 20 medium spenders ($1k-$5k, 5-15 orders)
- 40 low spenders ($100-$1k, 1-5 orders)
- 20 churned/inactive ($50-$500, 1-3 orders, 180+ days)
- 10 zero-order customers (filtered out in step 1)

## Intended Use

Tests the agent's ability to:
1. Read and understand a workflow specification written for a different tool
2. Translate each step to the appropriate Dataiku recipe type
3. Use visual recipes (filter, prepare) instead of writing Python
4. Produce output that matches expected_output.csv
