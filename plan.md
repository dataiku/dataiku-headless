# Implementation Plan

## 1. `dku ml predict-row` (ML WhatIfAnalysis analog)

**File:** `src/dku_cli/commands/ml.py`

Add `predict-row` command that takes a saved model ID and a features JSON dict.
Since `DSSSavedModel` has no `score()` in dataikuapi 14.5.1, the command makes
a raw API call via `client._session.post()` to the DSS predict endpoint:

```
POST /projects/{projectKey}/savedmodels/{modelId}/versions/{versionId}/predict
Body: {"features": {"age": 32, "income": 80000}}
```

Flags: `--features` (JSON string/@file/-), `--version` (optional, defaults to active).

Render: print the prediction result as JSON (primary use case is agent consumption).

## 2. `dku dataset analyze-column`

**File:** `src/dku_cli/commands/dataset.py`

Add `analyze-column DS COL -P PROJ` command.
Uses DSS statistics worksheet API to compute column analysis:
- Distribution (value counts)
- Null rate
- Top-K values
- Outlier detection
- Basic stats (min, max, mean, stddev for numeric)

Implementation: creates a temporary statistics worksheet card, runs it, extracts
the column analysis from the result. Falls back to showing what's available if
the API doesn't support all facets.

## 3. Log --grep/--tail flags

**Files:**
- `src/dku_cli/commands/job.py` — add `--grep` filter to existing log command (already has --tail)
- `src/dku_cli/commands/scenario.py` — add `--grep` and `--tail` to `run-log`
- `src/dku_cli/commands/webapp.py` — add `logs` command with `--grep` and `--tail`

Webapp logs: dataikuapi has no webapp log API, so use `client._session.get()`
on `/projects/{projectKey}/webapps/{webappId}/backend/logs` (the backend log endpoint).

## 4. Recipe lint-formula / lint-sql / lint-python

**File:** `src/dku_cli/commands/recipe.py`

Add `lint-formula`, `lint-sql`, `lint-python` commands.
dataikuapi has no compile/lint methods, so these approximate via `recipe.get_status()`
which returns severity-coded messages (ERROR/WARNING/INFO).

For formula linting: parse the GREL expression in the recipe's payload and report issues.
For SQL/Python: run the recipe's status check which validates engine compatibility + syntax.

## 5. Split prepare-processors.md

Create `dataiku-devkit/skills/dataiku/references/processors/` directory with per-processor files.
Mirror Cobuild's structure: one file per processor with description, params, examples.
Update `dataiku-devkit/skills/dataiku/SKILL.md` to point to per-processor refs.
Update `dku-cli` SKILL.md rules 10 and 15.

## 6. DQ skill section

Expand the DQ reference in `dataiku-devkit/skills/dataiku/SKILL.md` with clearer
rule-family routing and add the 10 rule families (volume, numeric range, emptiness,
uniqueness, allowed values, top-mode, meaning, schema, metric-compare, record count).

---

## Sequence

1. CLI commands (predict-row, analyze-column, log filters, lint) — these are pure code changes
2. Docs split (prepare-processors, DQ section, SKILL.md updates)
