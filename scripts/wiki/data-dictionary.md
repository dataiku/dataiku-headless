# Data Dictionary

## Source Datasets

### input_data
The main dataset: 117 investment product records with 48 months of data (6 actuals + 42 forecast).

| Column | Type | Description |
|--------|------|-------------|
| record_no | string | Unique record identifier (1-117) |
| platform | string | Platform 1 or Platform 2 |
| channel | string | Channel 1 or Channel 2 |
| bp_segment | string | Business planning segment (Segment One) |
| product | string | Product 01-04 |
| solution | string | 17 solution types (London, Birmingham, Liverpool, etc.) |
| growth_entity | string | Growth Rate 01, 02, or 03 |
| fund_entity | string | Legal Entity 1 or 2 |
| concat_key | string | Concatenated lookup key for Tab C join |
| month | string | YYYY-MM format |
| year | int | Derived from month |
| month_num | int | 1-12 derived from month |
| half_year | string | YYYY_H1 or YYYY_H2 |
| value | numeric | Original value (actuals or 0 for plan) |
| act_or_plan | string | Act (Jan-Jun 2025) or Plan (Jul 2025+) |

### lookup_a_asset_growth
Monthly asset price growth rates by growth entity and solution.

| Column | Description |
|--------|-------------|
| growth_entity | Growth Rate 01/02/03 |
| solution | 17 solution types |
| year | 2025-2028 |
| monthly_rate | Monthly default rate (approx 0.407% = 5% annual) |

### lookup_b_platform_weight
Platform weighting by segment, varying by half-year.

| Column | Description |
|--------|-------------|
| bp_segment | Segment One |
| platform | Platform 1 (99.18%) or Platform 2 (0.82%) |
| half_year | 2025_H2 through 2028_H2 |
| weight | Allocation weight (sums to 1.0 within segment) |

### lookup_c_share_of_solution
Per-record allocation share — determines what fraction of the total each record receives.

| Column | Description |
|--------|-------------|
| concat_key | Matches input_data.concat_key |
| year | 2025-2028 |
| share_rate | Fractional share (all shares sum to approx 1.0 per month) |

### lookup_d_seasonality
Monthly seasonality factors by channel and year.

| Column | Description |
|--------|-------------|
| channel | Channel 1 or Channel 2 |
| year | 2025-2028 |
| month_num | 1-12 |
| seasonality_factor | Multiplier (>1 = above average, <1 = below) |

### lookup_e_headcount
Month-over-month headcount productivity change.

| Column | Description |
|--------|-------------|
| bp_segment | Segment One |
| month | YYYY-MM |
| headcount_mom | MoM ratio (e.g., 1.045 = 4.5% increase) |

## Output Datasets

### forecast_detail
Record-level forecast with all 5,616 rows. Key columns:
- `forecast_value` — computed forecast (or actual value for Jan-Jun 2025)
- `composite_factor` — product of all 5 assumption factors for this record-month

### forecast_monthly
Monthly aggregated totals (48 rows):
- `forecast_value_sum` — total new business for the month
- `record_no_count` — always 117
