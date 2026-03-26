"""
DSS Python Recipe: Add derived join columns to input_data_long.

Input:  input_data (long format: 5616 rows with month as YYYY-MM)
Output: input_prepped (adds year, month_num, half_year columns for joins)
"""
import dataiku
import pandas as pd

input_ds = dataiku.Dataset("input_data")
df = input_ds.get_dataframe()

# Derive join keys from month (YYYY-MM)
df["year"] = df["month"].str[:4].astype(int)
df["month_num"] = df["month"].str[5:7].astype(int)
df["half_year"] = df["year"].astype(str) + "_" + df["month_num"].apply(
    lambda m: "H1" if m <= 6 else "H2"
)

output_ds = dataiku.Dataset("input_prepped")
output_ds.write_with_schema(df)
