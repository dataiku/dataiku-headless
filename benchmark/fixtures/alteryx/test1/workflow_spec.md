# Alteryx Customer Segmentation Workflow

## Overview

This workflow takes raw customer metrics and produces a segmented customer list with RFM scores, lifetime value estimates, and at-risk flags. The original runs in Alteryx Designer and needs to be recreated in Dataiku DSS.

## Input

`input.csv` - 100 customers with 12-month behavioral metrics.

## Workflow Steps

### Step 1: Filter Zero-Order Customers

Remove any customer where `order_count_12mo = 0`. These are inactive accounts that should not be scored.

**Expected result**: ~90 rows remain (10 customers have zero orders).

### Step 2: Calculate RFM Scores

For each remaining customer, compute Recency (R), Frequency (F), and Monetary (M) scores on a 1-5 scale:

**Recency Score** (based on `days_since_last_order`):
| Days Since Last Order | R Score |
|----------------------|---------|
| 0-30 | 5 |
| 31-60 | 4 |
| 61-90 | 3 |
| 91-180 | 2 |
| 181+ | 1 |

**Frequency Score** (based on `order_count_12mo`):
| Order Count | F Score |
|------------|---------|
| 15+ | 5 |
| 10-14 | 4 |
| 5-9 | 3 |
| 3-4 | 2 |
| 1-2 | 1 |

**Monetary Score** (based on `total_spend_12mo`):
| Total Spend | M Score |
|------------|---------|
| $5,000+ | 5 |
| $2,000-$4,999 | 4 |
| $1,000-$1,999 | 3 |
| $500-$999 | 2 |
| Under $500 | 1 |

**Composite RFM Score** = R + F + M (range: 3-15)

### Step 3: Assign Segments

Based on composite RFM score:

| RFM Score | Segment |
|-----------|---------|
| 12-15 | Gold |
| 8-11 | Silver |
| 3-7 | Bronze |

### Step 4: Calculate Lifetime Value

Estimated lifetime value over 3 years:

```
lifetime_value = avg_order_value * order_count_12mo * 3
```

This assumes current purchasing behavior continues for 3 years.

### Step 5: Flag At-Risk Customers

A customer is **at-risk** if:
- They are Gold OR Silver segment (high value)
- AND `days_since_last_order > 60` (showing signs of churn)

## Output

`expected_output.csv` with columns:
- `customer_id` - Original ID
- `name` - Customer name
- `rfm_score` - Composite RFM score (3-15)
- `segment` - Gold, Silver, or Bronze
- `lifetime_value` - Estimated 3-year lifetime value
- `at_risk` - True/False flag

## Notes for Dataiku Implementation

- Step 1 (filter) maps to a **Filter recipe** or **Prepare recipe** with row filter
- Steps 2-3 (scoring) map to a **Prepare recipe** with formula steps using conditional expressions
- Step 4 (LTV calculation) maps to a **Prepare recipe** formula step
- Step 5 (at-risk flag) maps to a **Prepare recipe** formula step with compound condition
- The entire workflow can be done with visual recipes -- no Python recipe needed
