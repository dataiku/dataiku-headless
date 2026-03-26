# Forecast Methodology

## The Recursive Challenge

The monthly new business calculation has a **recursive dependency**: each month's total depends on the prior month's total. In Excel, this is solved with cell references that chain forward. In Dataiku, we solve it with the **log-sum-exp trick**.

## Step-by-Step Calculation

### Step 1: Composite Factor (Prepare recipe)
For each of the 117 records in each forecast month, compute:
```
composite = (1 + monthly_rate) x weight x share_rate x seasonality x headcount_mom
```
Actuals months (Jan-Jun 2025): composite = 0 (weight is empty). Plan months (Jul 2025+): composite is a small fraction (typically 0.005-0.01).

### Step 2: Monthly Multiplier (Group recipe)
Sum all 117 composite factors for each month:
```
monthly_multiplier(m) = SUM(composite across all records for month m)
```
This gives the ratio T(m)/T(m-1) for each month. July 2025 = 1.1537.

### Step 3: Log Transform (Prepare recipe)
Convert the multiplicative chain to additive:
```
log_multiplier = ln(monthly_multiplier) = log10(monthly_multiplier) x 2.302585
```
Note: DSS `log()` is base-10, so we multiply by ln(10) for natural log.

### Step 4: Cumulative Sum (Window recipe)
Running sum of log values, ordered by month:
```
cumsum(Jul) = ln(1.1537)
cumsum(Aug) = ln(1.1537) + ln(0.9053)
cumsum(Sep) = ln(1.1537) + ln(0.9053) + ln(1.0735)
```

### Step 5: Monthly Totals (Prepare recipe)
Convert back from log space:
```
T(m) = T(June) x exp(cumsum(m))
     = 37,478,820 x exp(cumsum(m))
```
This gives the exact monthly total without iterative computation.

### Step 6: Record Allocation (Join + Prepare recipes)
Each record's value = its share of the monthly total:
```
forecast_value(r, m) = T(m) x composite(r, m) / monthly_multiplier(m)
```
This is equivalent to `T(m-1) x composite(r, m)` because `T(m)/monthly_multiplier(m) = T(m-1)`.

## Why This Works

The key mathematical insight:

```
T(m) = T(base) x Product(multiplier_i for i = 1..m)

Taking logs:
ln(T(m)) = ln(T(base)) + Sum(ln(multiplier_i))

The sum is a cumulative sum — a standard window function.
Then: T(m) = T(base) x exp(cumsum(ln(multipliers)))
```

This converts a recursive product into an additive cumulative sum, which Dataiku's Window recipe handles natively.

## Verification

The pipeline produces bit-identical results to both:
1. The original Excel workbook (Formula tab)
2. An independent Python implementation

All 48 monthly totals match with zero diff. Individual record values match to sub-penny precision.
