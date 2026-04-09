import pandas as pd

# Load
df = pd.read_csv("input.csv")

# Clean: drop rows where amount is null, filter to completed only
df = df.dropna(subset=["amount"])
df = df[df["status"] == "completed"]

# Transform: add month column, convert amount to float
df["month"] = pd.to_datetime(df["timestamp"]).dt.to_period("M").astype(str)
df["amount"] = df["amount"].astype(float)

# Aggregate: total and average amount by category and region
summary = (
    df.groupby(["category", "region"])
    .agg(
        total_amount=("amount", "sum"),
        avg_amount=("amount", "mean"),
        tx_count=("amount", "count"),
    )
    .reset_index()
)

# Sort by total amount descending
summary = summary.sort_values("total_amount", ascending=False)

summary.to_csv("output.csv", index=False)
