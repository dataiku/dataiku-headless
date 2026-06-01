# Recipe Operations

Operational patterns for creating, building, and verifying DSS flows through `dku`.

For recipe selection, read `recipe-decision.md`. For exact flags, read `commands.md`.

## End-to-End Skeleton

The default shape of a flow task — inspect, gauge, wire, build, verify. Each stage is detailed in its own section below.

```bash
# 1. Inspect project shape
dku project inspect PROJ -o json

# 2. Gauge and sample inputs
dku dataset info INPUT -P PROJ && \
dku dataset schema INPUT -P PROJ && \
dku dataset head INPUT -P PROJ -n 5

# 3. Wire DSS-native operations
dku recipe create-join join_enriched -i INPUT -i LOOKUP \
  --output-ds ENRICHED --join-key id -P PROJ && \
dku recipe create-group summarize -i ENRICHED \
  --output-ds SUMMARY -k category --agg "amount:sum,avg" -P PROJ

# 4. Build and verify
dku job run --target SUMMARY -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait && \
dku dataset head SUMMARY -P PROJ -n 5 && \
dku dataset info SUMMARY -P PROJ --recompute
```

## Inspect → Gauge → Sample

```bash
dku project inspect PROJ -o json

dku dataset info INPUT -P PROJ && \
dku dataset schema INPUT -P PROJ && \
dku dataset head INPUT -P PROJ -n 5
```

Use this before transforming data. It catches missing columns, stale assumptions, empty inputs, and expensive datasets.

## Upload Local Files

Use `UploadedFiles` for CLI uploads:

```bash
dku dataset create raw --type UploadedFiles -P PROJ && \
dku dataset upload raw ./raw.csv -P PROJ && \
dku dataset head raw -P PROJ -n 5
```

After CSV upload, set an explicit schema before numeric/date workflows when types matter.

## Wire Visual Recipes

Visual recipe shortcut commands create managed output datasets and schema payloads for common operations:

```bash
dku recipe create-join join_enriched -i raw -i lookup \
  --output-ds enriched --join-key id --join-type LEFT -P PROJ && \
dku recipe create-group summarize -i enriched \
  --output-ds summary -k category --agg "amount:sum,avg" -P PROJ
```

Prefer one multi-input join over cascading join recipes when the inputs are logically part of one enrichment step.

## Build

Build the terminal output with recursive schema propagation:

```bash
dku job run --target FINAL_OUTPUT -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

Use `dku recipe run RECIPE -P PROJ --wait` when a recipe outputs to a managed folder rather than a dataset.

## Verify

```bash
dku dataset head FINAL_OUTPUT -P PROJ -n 5 && \
dku dataset info FINAL_OUTPUT -P PROJ --recompute && \
dku recipe check-schema RECIPE -P PROJ
```

You are not done until the output has expected rows, columns, and row counts. `dku dataset head -o json` returning `[]` means zero rows, not proof of correctness.

## Analytical Lens — Interpret What You Find

When inspecting a dataset, go beyond confirming it exists. Surface what matters.

**Schema signals:**
- Column types that look wrong — strings that should be numeric, timestamps stored as text, booleans encoded as integers.
- Column names that suggest identifiers, surrogate keys, or row numbers — these are rarely useful as model features and often cause leakage.
- Cryptic or encoded column names worth clarifying before downstream work.

**Distribution signals** (from `dku dataset profile DS -P PROJ`):
- High null rates on important-looking columns — ask whether nulls are structural (always missing by design) or accidental (data quality issue).
- Unexpected value ranges or obvious outliers — flag them and ask whether they're real or errors.
- Low-cardinality columns suspiciously correlated with the target (potential leakage).
- High-cardinality columns that will be hard to use without preprocessing — free-text, raw URLs, unhashed IDs.
- Skewed categorical distributions — a column 95% one value rarely adds signal as-is.

**Size signals:**
- Very small datasets (under ~1,000 rows) — flag this if ML is the goal; small data limits what models can learn.
- Very wide datasets (many columns relative to rows) — mention overfitting risk if ML follows.

**Communicate findings as insights, not lists.** Connect what you see to what it means for the user's likely next step.

## Debug

| Symptom | First command |
|---|---|
| Build failed | `dku job log JOB_ID -P PROJ` |
| Output columns missing | `dku recipe check-schema RECIPE -P PROJ` |
| Row count stale | `dku dataset info DS -P PROJ --recompute` |
| Wrong column names | `dku dataset schema DS -P PROJ` |
| Flow topology unclear | `dku flow graph -P PROJ -o json` |

Detailed traps and recovery snippets live in `common-gotchas.md`.
