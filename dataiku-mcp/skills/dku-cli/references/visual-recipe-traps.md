# Visual recipe traps

Failure modes that pass payload validation, survive a `set-definition`, look
correct in `get-settings`, and still bite — at the next UI open, at build time,
or as a silent no-op. Each entry: **symptom → cause → correct payload**.

Read `visual-recipe-payloads.md` for the full payload shapes; this file is the
trap catalog only. Flags come from `dku <cmd> --help`.

---

## Class 1 — spurious "you have unsaved changes" prompt

DSS re-normalizes a visual-recipe payload every time the recipe is opened in the
UI, then diffs the normalized form against what you wrote. Any difference shows
the user a save prompt on a recipe they never edited. None of these affect build
output — they are pure round-trip-fidelity bugs — but they erode trust and make
"did the agent change something?" unanswerable. Write payloads that already match
DSS's normalized form.

### 1a. `selectedColumns[]` out of source order (join, fuzzyjoin)

- **Symptom:** open the join recipe in DSS → immediate save prompt, no edit made.
- **Cause:** DSS reorders `selectedColumns[]` to match each input dataset's
  schema column order on UI save. Any other order is a diff.
- **Fix:** read each input's schema first (`dku --format json dataset get-schema DS -P PROJ`
  or `recipe get-settings` against the upstream), then emit `selectedColumns[]`
  grouped by `table` index and, within a table, in that schema's column order.

```json
"selectedColumns": [
  {"name": "id",     "table": 0, "type": "bigint"},
  {"name": "region", "table": 0, "type": "string"},
  {"name": "status", "table": 1, "type": "string"}
]
```

### 1b. missing top-level `computedColumns: []` (join, fuzzyjoin)

- **Symptom:** save prompt on next open even though `selectedColumns[]` order is
  correct.
- **Cause:** DSS injects `"computedColumns": []` at the payload top level on first
  UI save. Omitting it guarantees a diff.
- **Fix:** always write an explicit empty array, even when unused. Same applies to
  each `virtualInputs[i].computedColumns` — include `[]` per input.

```json
{
  "joins": [ ... ],
  "selectedColumns": [ ... ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```

### 1c. writing DSS-managed `$`-cache fields

- **Symptom:** intermittent save prompts, or a payload that "won't stay clean."
- **Cause:** `postFilter.$status` (and other `$`-prefixed cache fields) are
  populated by DSS after a UI save with a cached schema snapshot. Hand-writing a
  stale or empty value fights DSS's own regeneration.
- **Fix:** never write `$status`. Preserve `$`-prefixed metadata on round-trip
  when it already exists (`$idx`, `$latestOperator`, `$filterOptions`,
  `$showList`), but do not author it from scratch. Its presence or absence does
  not itself trigger a prompt — only a *wrong* value does.

---

## Class 2 — accepted-but-no-op (silent) steps

DSS validates structure loosely. A structurally valid step with a wrong field
name or a missing required scope field is accepted, persists in `get-settings`,
and does nothing at build. The output column is simply absent or unchanged.
Preview-level confidence is never enough — only a built-and-sampled output
column confirms a step.

### 2a. unknown param key → silent no-op

- **Symptom:** step is present in settings; the expected new/changed column is
  missing after build.
- **Cause:** DSS ignores unrecognized param keys instead of erroring. A misspelled
  field (`inColumn` vs `inCol`, `min`/`max` vs `lowerBound`/`upperBound`) makes
  the whole processor a no-op.
- **Fix:** resolve every param from the processor reference before writing; never
  guess field names. After build, `dku dataset head OUT -P PROJ` (or
  `--format json` profile) on the affected column.

### 2b. missing `appliesTo` on a scoped processor

- **Symptom:** `ColumnReorder`, `ColumnsSelector`, date processors etc. do
  nothing; no error.
- **Cause:** scoped processors require `appliesTo`
  (`SINGLE_COLUMN` | `COLUMNS` | `ALL` | `PATTERN`). Omitting it short-circuits the
  step to a no-op rather than defaulting.
- **Fix:** always set `appliesTo`, and set `appliesToPattern` when
  `appliesTo: "PATTERN"`.

```json
{"type": "ColumnReorder",
 "params": {"appliesTo": "COLUMNS", "columns": ["id"],
            "reorderAction": "AT_THE_BEGINNING", "referenceColumn": ""}}
```

### 2c. invalid enum value → NPE at build, not at write

- **Symptom:** `set-definition` succeeds; the *build* fails with a Java
  NullPointerException.
- **Cause:** some processors accept a free-string mode at write time but only
  resolve valid tokens at build. `StringTransformer` with `UPPERCASE`/`TITLECASE`
  (valid tokens are `TO_UPPER`/`TO_LOWER`/`TRIM`/`NORMALIZE`/`TRUNCATE`) NPEs.
- **Fix:** use only the documented enum tokens. For title-case, there is no token
  — use a GREL `toTitlecase(...)` via `CreateColumnWithGREL`.

---

## Class 3 — wrong-shape but plausible config

### 3a. Sampling recipe used to filter rows

- **Symptom:** "filter" appears configured; every row passes through.
- **Cause:** the Sampling recipe's natural-looking `uiData.expression` is silently
  rewritten to `{mode:"CUSTOM",conditions:[]}` — a match-all no-op. Sampling is
  not a filter.
- **Fix:** to keep rows matching a condition, use a Prepare recipe with
  `FilterOnCustomFormula` (or `create-filter`). Reserve Sampling for actual
  sampling.

### 3b. filter `uiData.mode` mismatched to the field DSS evaluates

- **Symptom:** filter "runs" but ignores your condition entirely.
- **Cause:** `uiData.mode` selects *which field* DSS reads. `"&&"`/`"||"` evaluate
  `uiData.conditions[]`; `"CUSTOM"` and `"SQL"` evaluate the top-level
  `expression` (GREL or raw SQL respectively). A GREL `expression` under
  `mode:"&&"` is never read; a `conditions[]` array under `mode:"CUSTOM"` is never
  read.
- **Fix:** match the mode to where the logic actually lives.

```json
{"enabled": true, "distinct": false,
 "uiData": {"mode": "&&", "conditions": [
   {"input": "status", "operator": "== [string]", "string": "active"},
   {"input": "age",    "operator": ">= [number]", "num": 18}]}}
```

### 3c. unmatched-output role incompatible with join type

- **Symptom:** a left/right "unmatched rows" output that is empty or rejected,
  or unmatched rows that are not the ones the user meant.
- **Cause:** for a `LEFT` join, `unmatchedLeft` is invalid (the left side is
  preserved into `main`); for a `RIGHT` join, `unmatchedRight` is invalid.
  `LEFT_ANTI`/`RIGHT_ANTI` already *are* the unmatched set — do not add an
  unmatched output on top. "Left-side rows whose right columns are null" is a
  different requirement from the built-in unmatched toggle and needs a downstream
  recipe.
- **Fix:** resolve the dataset side from input order (`joins[].table1` is left),
  pick the role from the matrix, verify `FULL`/`ADVANCED` against a live recipe
  before relying on it.

| Join type | Valid unmatched role(s) |
|---|---|
| `LEFT` | `unmatchedRight` only |
| `RIGHT` | `unmatchedLeft` only |
| `INNER` | `unmatchedLeft`, `unmatchedRight`, or both |
| `LEFT_ANTI` / `RIGHT_ANTI` | none — recipe is already the unmatched set |
| `CROSS` | unsupported |
| `FULL` / `ADVANCED` | verify against a live recipe first |

### 3d. duplicate column names silently dropped on join

- **Symptom:** an expected column is missing from join output; no error.
- **Cause:** `AUTO_NON_CONFLICTING` projection silently drops one side of a
  name collision (e.g. both inputs have `STATUS`).
- **Fix:** set `outputColumnsSelectionMode: "MANUAL"` on the colliding inputs and
  list every desired column in `selectedColumns[]` with its `table` index.

---

## Class 4 — schema / type drift after a transform

### 4a. Prepare output column is the wrong storage type

- **Symptom:** a parsed date or extracted number lands as `string`; downstream
  Group/Window aggregations refuse it or mis-sort it.
- **Cause:** Prepare auto-detects output schema but defaults parsed-in-place
  results to `string`. The visual value looks right; the storage type is wrong.
- **Fix:** after the build, set the storage type explicitly
  (`set-dataset-column-storage-types`, or the equivalent CLI verb) to one of
  `tinyint smallint int bigint float double boolean string date dateonly
  datetimenotz geopoint geometry array map object`. Values that don't conform to
  the new type become **null** — parse/format first, then retype.

### 4b. connection type rejects a storage type

- **Symptom:** retype to `date`/`bigint` errors or warns on certain connections.
- **Cause:** some connection types don't support some storage types.
- **Fix:** fall back to `string` for that connection rather than forcing the type.

### 4c. Prepare does not create its own output dataset

- **Symptom:** `add-step` / `set-definition` succeeds but build fails — no output
  dataset.
- **Cause:** unlike Group/Join/Window, the Prepare recipe does not auto-create its
  output dataset.
- **Fix:** create the output dataset first, then attach the recipe.

---

## Class 5 — grouping / aggregation traps

### 5a. selected metric with no aggregation flag

- **Symptom:** the column appears in `values[]` but no aggregate column is
  emitted.
- **Cause:** each `values[]` entry needs at least one aggregation flag enabled
  (`count`, `sum`, `avg`, `min`, `max`, `median`, `stddev`, `first`, `last`, …) or
  a `customExpr` + `customName`. A selected-but-flagless metric does nothing.
- **Fix:** enable at least one flag (or a custom aggregate) per selected metric.

### 5b. `first`/`last` without `orderColumn`

- **Symptom:** `first`/`last`/`firstLastNotNull` results are non-deterministic
  across rebuilds.
- **Cause:** without an explicit `orderColumn` the picked row is arbitrary.
- **Fix:** set `orderColumn` whenever using order-dependent aggregations.

### 5c. dropping DSS grouping metadata keys

- **Symptom:** payload "works" but the UI re-derives keys or loses selections.
- **Cause:** rebuilding `keys[]`/`values[]` from scratch can drop DSS metadata
  keys (`$idx`, `$selected`).
- **Fix:** read first, mutate in place, preserve unknown keys.

---

## Permanent rules

1. `--deep-merge` merges dicts but **replaces arrays entirely**. For any array
   field (`selectedColumns[]`, `joins[]`, `values[]`, `keys[]`, `steps[]`,
   `orders[]`) do a full read-edit-write — never a partial deep-merge.
2. Keep table indices consistent across `joins[]`, `selectedColumns[]`, and
   `virtualInputs[]`. The left/right side is fixed by input order, not by dataset
   name or importance.
3. `engineType` is a top-level field (`DSS|SQL|SPARK_SQL|IMPALA|HIVE`) and wins
   over `engineParams.<engine>.executionEngine`. Preserve engine settings unless
   the user explicitly asks to change them — join-type and processor support vary
   by engine.
4. Never trust `get-settings` as proof a step worked. Build the output and sample
   the affected column.
