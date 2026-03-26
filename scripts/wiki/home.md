# Wealth Manager — Monthly New Business Forecast

## Overview

This project replicates a wealth management FP&A department's monthly new business calculations that previously lived in a complex Excel workbook with 6 tabs. The entire calculation pipeline uses **visual DSS recipes only — zero Python code**.

| Metric | Value |
|--------|-------|
| Records | 117 investment products |
| Actuals | Jan–Jun 2025 (6 months) |
| Forecast | Jul 2025–Dec 2028 (42 months) |
| Total rows | 5,616 (117 x 48) |
| FY2025 | 518M |
| FY2026 | 605M (+17%) |
| FY2027 | 658M (+9%) |
| FY2028 | 697M (+6%) |

## The 5-Factor Forecast Model

Each record's monthly forecast value is computed as:

```
value(record, month) = Prior_Month_Total
  x (1 + Asset Price Growth rate)      -- Tab A lookup
  x Platform Weighting                  -- Tab B lookup
  x Share of Solution                   -- Tab C lookup
  x Seasonality Factor                  -- Tab D lookup
  x Headcount & Productivity MoM        -- Tab E lookup
```

Where `Prior_Month_Total = SUM(all 117 records for the prior month)`. This creates a **recursive month-over-month dependency** — each month's output feeds the next month's input.

The recursive chain is solved using the **log - cumulative sum - exp** trick in visual recipes, avoiding Python entirely.

## Pipeline Architecture

### Zone 1: Data Ingestion (7 datasets)
6 source CSVs parsed from the Excel workbook (input data + 5 assumption lookup tables) plus 1 expected values dataset for automated validation.

### Zone 2: Enrichment (5 Join recipes)
Sequential joins attach all 5 assumption factors to each of the 5,616 record-month rows:
1. **join_asset_growth** — on growth_entity + solution + year
2. **join_platform_weight** — on bp_segment + platform + half_year
3. **join_share_solution** — on concat_key + year
4. **join_seasonality** — on channel + year + month_num
5. **join_headcount** — on bp_segment + month

### Zone 3: Forecast Calculation (8 visual recipes)
1. **prep_composite** (Prepare) — Formula: `(1 + rate) x weight x share x season x headcount`
2. **group_monthly** (Group) — SUM composite by month -> monthly multiplier
3. **prep_log** (Prepare) — Natural log of multiplier
4. **win_cumsum** (Window) — Cumulative SUM of log values, ordered by month
5. **prep_totals** (Prepare) — Monthly total: `june_total x exp(cumsum)`
6. **join_totals** (Join) — Attach totals back to individual records
7. **prep_forecast** (Prepare) — Allocate: `total x composite / composite_sum`
8. **group_summary** (Group) — Monthly summary for dashboard

### Zone 4: Validation & Output
- Automated validation comparing computed values against known Excel answers
- FP&A Agent — LLM-powered Q&A against the forecast data
- Dashboard — Executive overview with charts and drill-down tables

## Validation

All checks pass with zero diff against the original Excel workbook:
- June 2025 Total: 37,478,820 (exact match)
- July 2025 Total: 43,237,566 (exact match)
- Record 1, July 2025: 263,910.17 (exact match)
- All 48 monthly totals verified
- 5,616 rows, 117 records per month

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Visual recipes over Python | Auditable, maintainable, accessible to finance teams |
| Log/cumsum/exp trick | Converts recursive product into additive window function |
| Separate lookup datasets | Each assumption factor is independently updatable |
| Expected values dataset | Validation is data-driven, not hardcoded |
| DatasetRowLookup agent tools | Agent queries live data, not cached summaries |
