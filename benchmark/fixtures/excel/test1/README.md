# Quarterly Financial Report Fixtures

Excel workbook with raw expense transactions and formula-based summary/pivot sheets. Tests the agent's ability to replicate Excel-based reporting in Dataiku using visual recipes.

## Files

| File | Description |
|------|-------------|
| `workbook.xlsx` | Excel file with 3 sheets (Raw Data, Summary, Monthly) |
| `raw_data.csv` | CSV backup of the Raw Data sheet (for non-Excel import paths) |
| `workbook_spec.md` | Detailed description of each sheet, formulas, and Dataiku mapping |
| `expected_output.csv` | Summary sheet output: department x category aggregation (28 rows) |

## Schema: raw_data.csv / Raw Data Sheet

| Column | Type | Description |
|--------|------|-------------|
| date | date | Transaction date (YYYY-MM-DD, 2025) |
| department | string | Engineering, Marketing, Sales, Operations, Finance |
| category | string | Software, Hardware, Travel, Consulting, Office Supplies, Training |
| amount | float | Transaction amount in USD |
| vendor | string | Vendor name (8 distinct vendors) |

80 rows total.

## Schema: expected_output.csv

| Column | Type | Description |
|--------|------|-------------|
| department | string | Department name |
| category | string | Expense category |
| total_amount | float | Sum of amount for this dept+category |
| avg_amount | float | Average amount for this dept+category |
| transaction_count | int | Number of transactions |

28 rows (not all department-category combinations have transactions).

## Intended Use

Tests the agent's ability to:
1. Import Excel data into Dataiku (upload or CSV import)
2. Replicate SUMPRODUCT formulas using a Group recipe
3. Replicate pivot-style monthly breakdown using a Pivot recipe
4. Validate output totals match the expected values
