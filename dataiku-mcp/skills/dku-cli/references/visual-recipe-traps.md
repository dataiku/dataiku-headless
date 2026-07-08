# Reference: Visual Recipe Traps

Failure modes that pass payload validation, survive a `set-definition`, look
correct in `get-settings`, and still bite — at the next UI open, at build time,
or as a silent no-op. Each entry: **symptom → cause → correct payload**.

Read `visual-recipe-payloads.md` for the full payload shapes; this file is the
trap catalog only. Flags come from `dku <cmd> --help`.

**Contents:**
Class 1 spurious save prompts — 1a column order · 1b missing `computedColumns: []` · 1c `$`-fields ·
Class 2 silent no-ops — 2a unknown keys · 2b `appliesTo` · 2c enum NPE ·
Class 3 plausible-but-wrong shapes — 3a Sampling-as-filter · 3b `uiData.mode` · 3c unmatched roles · 3d dropped duplicate columns ·
Class 4 type drift — 4a Prepare output types · 4b connection rejects type ·
Class 5 aggregation — 5a flagless metric · 5b `orderColumn`

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

### 1c. writing (or dropping) DSS-managed `$`-fields

- **Symptom:** intermittent save prompts, a payload that "won't stay clean," or
  a UI that re-derives keys / loses selections.
- **Cause:** `$`-prefixed fields (`$status`, `$idx`, `$selected`,
  `$latestOperator`, `$filterOptions`, `$showList`) are DSS-managed caches and
  selection metadata. Hand-writing a stale value fights DSS's regeneration;
  rebuilding `keys[]`/`values[]` from scratch drops them.
- **Fix:** never author `$`-fields; read first, mutate in place, preserve the
  ones already there. Their presence or absence does not itself trigger a
  prompt — only a *wrong* value does.

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
- **Fix:** `appliesTo` is required on scoped processors — omitting it
  short-circuits the step to a no-op rather than defaulting. Values and
  per-processor params: `prepare-processors.md` § Shared params.

### 2c. invalid enum value → NPE at build, not at write

- **Symptom:** `set-definition` succeeds; the *build* fails with a Java
  NullPointerException.
- **Cause:** some processors accept a free-string mode at write time but only
  resolve valid tokens at build (e.g. `StringTransformer` — valid tokens and
  the title-case workaround in its `prepare-processors.md` row).
- **Fix:** use only the documented enum tokens.

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

- **Symptom:** filter "runs" but ignores your condition entirely — a GREL
  `expression` under `mode:"&&"` is never read, and a `conditions[]` array
  under `mode:"CUSTOM"` is never read.
- **Fix:** `uiData.mode` selects *which field* DSS evaluates — mode table and
  canonical shapes in `visual-recipe-payloads.md` § Visual conditions.

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
- **Fix:** `AUTO_NON_CONFLICTING` drops one side of a name collision — go
  `MANUAL` with explicit `selectedColumns[]` on both inputs
  (`visual-recipe-payloads.md` § Join, incl. the round-trip rule).

---

## Class 4 — schema / type drift after a transform

### 4a. Prepare output column is the wrong storage type

- **Symptom:** a parsed date or extracted number lands as `string`; downstream
  Group/Window aggregations refuse it or mis-sort it.
- **Cause:** Prepare auto-detects output schema but defaults parsed-in-place
  results to `string`. The visual value looks right; the storage type is wrong.
- **Fix:** after the build, set the storage type explicitly
  (`set-dataset-column-storage-types`, or the equivalent CLI verb) — full type
  list in `datasets-and-types.md` § Schema. Values that don't conform to the new
  type become **null** — parse/format first, then retype.

### 4b. connection type rejects a storage type

- **Symptom:** retype to `date`/`bigint` errors or warns on certain connections.
- **Cause:** some connection types don't support some storage types.
- **Fix:** fall back to `string` for that connection rather than forcing the type.

### 4c. Prepare does not create its own output dataset

- **Symptom:** `add-step` / `set-definition` succeeds but build fails — no output
  dataset.
- **Cause:** unlike Group/Join/Window, generic Prepare creation does not always
  auto-create its output dataset.
- **Fix:** use `dku recipe create-prepare`, or create the output dataset first
  and then attach the recipe.

---

## Class 5 — grouping / aggregation misconfiguration

### 5a. selected metric with no aggregation flag

- **Symptom:** the column appears in `values[]` but no aggregate column is
  emitted.
- **Cause:** each `values[]` entry needs at least one aggregation flag enabled
  (`count`, `sum`, `avg`, `min`, `max`, `median`, `stddev`, `first`, `last`, …) or
  a `customExpr` + `customName`. A selected-but-flagless metric does nothing.
- **Fix:** enable at least one flag (or a custom aggregate) per selected metric.

### 5b. `first`/`last` without `orderColumn`

- **Symptom:** `first`/`last`/`firstLastNotNull` results are non-deterministic
  across rebuilds — `orderColumn` requirement in `visual-recipe-payloads.md`
  § Group.

---

## Permanent rule

Preserve engine settings unless the user explicitly asks to change them —
join-type and processor support vary by engine (`engineType` semantics:
`visual-recipe-payloads.md` § 4-stage pipeline).
