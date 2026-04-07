# Excel Workbook Specification

## Overview

This workbook (`workbook.xlsx`) is a quarterly financial report maintained by an analyst. It contains raw transaction data and two derived sheets with formulas. The goal is to replicate this reporting pipeline in Dataiku DSS using visual recipes.

## Sheet 1: Raw Data

80 rows of expense transactions.

| Column | Type | Example |
|--------|------|---------|
| date | date | 2025-03-15 |
| department | string | Engineering |
| category | string | Software |
| amount | float | 4,250.00 |
| vendor | string | TechCorp |

**Departments**: Engineering, Marketing, Sales, Operations, Finance
**Categories**: Software, Hardware, Travel, Consulting, Office Supplies, Training
**Vendors**: TechCorp, CloudVend, TravelPro, ConsultMax, OfficeHub, LearnFast, DataServ, NetSolutions

## Sheet 2: Summary

Aggregation by department and category. Each row uses SUMPRODUCT formulas against the Raw Data sheet.

| Column | Formula |
|--------|---------|
| department | (lookup value) |
| category | (lookup value) |
| total_amount | `=SUMPRODUCT((Raw Data!B:B=A2)*(Raw Data!C:C=B2)*(Raw Data!D:D))` |
| avg_amount | `=IF(E2>0, C2/E2, 0)` (total / count) |
| transaction_count | `=SUMPRODUCT((Raw Data!B:B=A2)*(Raw Data!C:C=B2)*1)` |

Only department-category combinations that have at least one transaction appear.

**Dataiku equivalent**: Group recipe on (department, category) with SUM(amount), AVG(amount), COUNT(amount).

## Sheet 3: Monthly

Pivot-style breakdown showing total spend by department (rows) and month (columns).

| | 2025-01 | 2025-02 | ... | 2025-12 |
|---|---------|---------|-----|---------|
| Engineering | $X | $Y | ... | $Z |
| Marketing | ... | ... | ... | ... |

Each cell uses a SUMPRODUCT formula matching department + month prefix from the date column.

**Dataiku equivalent**: Pivot recipe with department as row key, month (extracted from date) as column key, SUM(amount) as value.

## Replication Requirements

To replicate this workbook in Dataiku:

1. **Import** the Raw Data sheet (or `raw_data.csv`) as a dataset
2. **Summary**: Create a Group recipe on `department` + `category`, computing:
   - `total_amount` = SUM(amount)
   - `avg_amount` = AVG(amount)
   - `transaction_count` = COUNT(amount)
3. **Monthly**: Either:
   - Create a Prepare recipe to extract month from date (`YYYY-MM` format)
   - Then create a Pivot recipe with `department` as row, `month` as column, SUM(amount) as value
   - OR use a Group recipe on (department, month) followed by a Pivot

## Validation

Compare the Dataiku output against `expected_output.csv` for the Summary sheet. The Monthly sheet is validated by checking that row totals match the Summary department totals.
