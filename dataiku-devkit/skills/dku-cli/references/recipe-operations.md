# Recipe Operations

Operational patterns for creating, building, and verifying DSS flows through `dku`.

For recipe selection, read `recipe-decision.md`. For exact flags, read `commands.md`.

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

## Debug

| Symptom | First command |
|---|---|
| Build failed | `dku job log JOB_ID -P PROJ` |
| Output columns missing | `dku recipe check-schema RECIPE -P PROJ` |
| Row count stale | `dku dataset info DS -P PROJ --recompute` |
| Wrong column names | `dku dataset schema DS -P PROJ` |
| Flow topology unclear | `dku flow graph -P PROJ -o json` |

Detailed traps and recovery snippets live in `common-gotchas.md`.
