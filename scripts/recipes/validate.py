"""
DSS Python Recipe: Validate forecast against known Excel values.

Input:  forecast_detail
Output: validation_results

Known validation points from the Excel Formula tab:
  - Record 1, July 2025 = 263,910.17
  - June 2025 total = 37,478,820
  - July 2025 total = 43,237,566.02 (computed from full chain)
"""
import dataiku
import pandas as pd
import json

detail_ds = dataiku.Dataset("forecast_detail")
df = detail_ds.get_dataframe()

df["forecast_value"] = pd.to_numeric(df["forecast_value"], errors="coerce")
df["record_no"] = df["record_no"].astype(str)

checks = []

# Check 1: June 2025 total
june_total = df[df["month"] == "2025-06"]["forecast_value"].sum()
checks.append({
    "check": "June 2025 Total",
    "expected": 37478820.0,
    "actual": round(june_total, 2),
    "diff": round(abs(june_total - 37478820.0), 2),
    "pass": abs(june_total - 37478820.0) < 1.0,
})

# Check 2: Record 1, July 2025
r1_jul = df[(df["record_no"] == "1") & (df["month"] == "2025-07")]
if len(r1_jul) > 0:
    r1_val = r1_jul["forecast_value"].iloc[0]
    checks.append({
        "check": "Record 1 July 2025",
        "expected": 263910.17,
        "actual": round(r1_val, 2),
        "diff": round(abs(r1_val - 263910.17), 2),
        "pass": abs(r1_val - 263910.17) < 0.01,
    })

# Check 3: July 2025 total
jul_total = df[df["month"] == "2025-07"]["forecast_value"].sum()
checks.append({
    "check": "July 2025 Total",
    "expected": 43237566.02,
    "actual": round(jul_total, 2),
    "diff": round(abs(jul_total - 43237566.02), 2),
    "pass": abs(jul_total - 43237566.02) < 1.0,
})

# Check 4: No NaN forecast values in plan months
plan_nans = df[df["act_or_plan"] == "Plan"]["forecast_value"].isna().sum()
checks.append({
    "check": "No NaN in Plan months",
    "expected": 0,
    "actual": int(plan_nans),
    "diff": int(plan_nans),
    "pass": plan_nans == 0,
})

# Check 5: Row count (117 records × 48 months)
checks.append({
    "check": "Total row count",
    "expected": 5616,
    "actual": len(df),
    "diff": abs(len(df) - 5616),
    "pass": len(df) == 5616,
})

# Check 6: Actuals pass through unchanged
actuals = df[df["act_or_plan"] == "Act"]
actuals_match = (actuals["forecast_value"] == pd.to_numeric(actuals["value"])).all()
checks.append({
    "check": "Actuals unchanged",
    "expected": "True",
    "actual": str(actuals_match),
    "diff": 0 if actuals_match else 1,
    "pass": bool(actuals_match),
})

result_df = pd.DataFrame(checks)
print("\n=== Validation Results ===")
for _, row in result_df.iterrows():
    status = "PASS" if row["pass"] else "FAIL"
    print(f"  [{status}] {row['check']}: expected={row['expected']}, actual={row['actual']}, diff={row['diff']}")

all_pass = result_df["pass"].all()
print(f"\nOverall: {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")

output_ds = dataiku.Dataset("validation_results")
output_ds.write_with_schema(result_df)
