"""
DSS Python Recipe: Compute the monthly new business forecast.

Input:  enriched_full (input_prepped joined with all 5 lookup tables)
Output: forecast_detail (individual record-level forecast values)
        forecast_monthly (monthly totals for dashboard)

Calculation chain per record per month:
  value = prior_month_total × (1 + monthly_rate) × platform_weight
          × share_of_solution × seasonality × headcount_mom

Where prior_month_total = SUM(all records for the prior month).
This creates a recursive dependency solved by iterating month-by-month.
"""
import dataiku
import pandas as pd
import numpy as np

# --- Load enriched data ---
enriched_ds = dataiku.Dataset("enriched_full")
df = enriched_ds.get_dataframe()

# Ensure numeric types
for col in ["value", "monthly_rate", "weight", "share_rate",
            "seasonality_factor", "headcount_mom"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["year"] = df["year"].astype(int)
df["month_num"] = df["month_num"].astype(int)

# Sort by month for iteration
df = df.sort_values(["month", "record_no"]).reset_index(drop=True)

# --- Identify actuals vs plan months ---
actuals = df[df["act_or_plan"] == "Act"].copy()
plan_months = sorted(df[df["act_or_plan"] == "Plan"]["month"].unique())

# --- Compute composite factor per record-month ---
# composite = (1 + monthly_rate) × platform_weight × share_of_solution × seasonality × headcount_mom
df["composite"] = (
    (1 + df["monthly_rate"])
    * df["weight"]
    * df["share_rate"]
    * df["seasonality_factor"]
    * df["headcount_mom"]
)

# --- Recursive monthly total calculation ---
# Start from the last actuals month
last_actual_month = actuals["month"].max()
prior_total = actuals[actuals["month"] == last_actual_month]["value"].sum()

monthly_totals = {}
# Include actual months' totals
for m in sorted(actuals["month"].unique()):
    monthly_totals[m] = actuals[actuals["month"] == m]["value"].sum()

# Compute plan months iteratively
results = []
for month in plan_months:
    month_mask = df["month"] == month
    month_df = df[month_mask].copy()

    # Each record's value = prior_month_total × composite_factor
    month_df["forecast_value"] = prior_total * month_df["composite"]

    # Store this month's total for next iteration
    month_total = month_df["forecast_value"].sum()
    monthly_totals[month] = month_total

    results.append(month_df)
    prior_total = month_total

# --- Combine actuals + forecast ---
actuals_out = actuals.copy()
actuals_out["forecast_value"] = actuals_out["value"]

if results:
    forecast_df = pd.concat(results, ignore_index=True)
    output_df = pd.concat([actuals_out, forecast_df], ignore_index=True)
else:
    output_df = actuals_out

# --- Select output columns ---
output_cols = [
    "record_no", "platform", "channel", "bp_segment", "product", "solution",
    "fund_entity", "growth_entity", "month", "year", "month_num", "half_year",
    "act_or_plan", "value", "forecast_value",
    "monthly_rate", "weight", "share_rate", "seasonality_factor", "headcount_mom",
    "composite",
]
# Keep only columns that exist
output_cols = [c for c in output_cols if c in output_df.columns]
output_df = output_df[output_cols].sort_values(["month", "record_no"])

# --- Write forecast detail ---
detail_ds = dataiku.Dataset("forecast_detail")
detail_ds.write_with_schema(output_df)

# --- Write monthly summary ---
summary = (
    output_df.groupby(["month", "year", "act_or_plan"])
    .agg(
        total_new_business=("forecast_value", "sum"),
        record_count=("record_no", "count"),
    )
    .reset_index()
    .sort_values("month")
)
summary_ds = dataiku.Dataset("forecast_monthly")
summary_ds.write_with_schema(summary)
