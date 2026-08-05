# Validate

Read this when selecting a parity anchor, proving parity, or judging completion. Return to [Excel](../excel.md) for the delivery contract.

## Validating the Migration

Read `<bundle_dir>/migration_v<n>/validation_plan.md`. If any check fails, repeat the build and re-validate.

Parity tiers:
- Real expected data: full row x column parity.
- Non-exhaustive expected sample: containment check `expected EXCEPT produced = ∅`, not equality.
- Synthetic-only: exact ordered schema-shape parity.
- Synthetic inputs engineered to printed margins: the reproduced margins are full value parity; only non-engineered joint distributions fall back to schema-shape.
- Numeric values compare at the precision serialized by the workbook, not machine epsilon.

A wider output is a defect, not a documentable deviation. So is a narrower one: rows the source prints are contract, including zero rows. Produce never-observed combinations with an explicit key cross instead of letting aggregation drop them.

## Parity Anchors

Choose the anchor before building the check.

- Prove parity per terminal dataset against its source sheet. A consolidated table sliced locally at diff time validates data no SME can review in the project.
- Validate cached pivot or output values, cleaned-table row counts, formula-column spot rows, and shipped chart or dashboard behavior.
- After each reshape, row count must match the workbook table contract. Near misses usually indicate clone rows, leaked totals, or blank-row pollution.
- Compare raw and cleaned data across every column. Compare floats at stored precision, not display text.
- A column that does not converge can be hand-authored data. Preserve its source values and validate the downstream deliverable.
- For model workbooks, cover one series per forecast method and window variant. Validate the seam month, then horizon samples, then the full sweep.

## Parity Mechanism

Aggregates are gates, never verdicts. Compare fresh, exhaustive row counts and useful column aggregates against workbook-derived values before the conclusive check. `get_dataset_profile` can truncate at `max_rows`, and `get_dataset_metrics` returns last-computed values; treat either as diagnostic unless its coverage and freshness are verified.

Default to a full local export diff. Use in-Dataiku verification instead when the output exceeds a declared local disk or comparison-memory budget, CSV cannot preserve a required distinction, or the verdict must remain in the project. Name the path and reason in the validation plan.

Both paths must enforce the selected parity tier's ordered schema, cardinality, and cell coverage. Validate business-key uniqueness before a keyed comparison; without a unique key, use a multiset-safe comparison that preserves duplicate counts.

**Local export diff.** `export_dataset` streams every row to a local UTF-8 CSV and returns column types; it is not sample-capped. Read it with those explicit types, normalize workbook and Dataiku values under the same contract, and compare at workbook-serialized precision. Leading-zero or long text identifiers and Unicode survive when kept as strings, but null and empty string both export as an empty field; use in-Dataiku verification when that distinction matters. This creates no Dataiku asset or Cobuild write turn. Record the evidence, then delete the scratch export.

**In-Dataiku verification.** Upload the expected output and verify its ingested schema, then build a keyed full-outer comparison or multiset-safe equivalent. Write `parity_mismatches` and a one-row summary (`rows_expected`, `rows_actual`, `mismatch_count`); parity is `mismatch_count == 0`. This persists the evidence and avoids exporting the produced output, but requires Cobuild work and migration-created assets. Record that the same Cobuild built the flow and the check.

- `get_dataset_sample` caps at 100 rows. Use it to read the one-row verdict or localize a failure, never to prove a larger dataset.
- Keep parity reference datasets and verification recipes out of the delivered flow; delete them during cleanup after recording the verdict.

## Excel-Sensitive Validation

- Prove parity at entity grain from the planned inputs, not by joining cached outputs back into the result.
- For parameterized or branchy logic, change one input, variable, or predicate; rebuild the affected branch; confirm the expected delta; then restore it.
- When configuration and cached output disagree, test a row or value that distinguishes the competing interpretations and let parity choose.
- Verify identifier values and cardinality after build. Leading zeros, letters, masking characters, and formatted codes remain strings.
- Ensure date-only delivery values render as `yyyy-MM-dd`, without a time suffix.
- When float ties affect source order, sort on a rounded helper while retaining the full-precision metric, then remove the helper before delivery.
- Probe both states of every project variable used in workbook logic; an unset variable can flow through as literal text while the build remains green.

## Reading a Diff

Once `parity_mismatches` is nonzero, the shape of the divergence names the defect faster than reading rows. Compare produced against expected on the entity or period key and classify:

- Values match everywhere: parity holds. Suspect the key or the join, not the logic.
- Every value negated: sign contract is wrong. Carry sign as contract and verify sign, not magnitude.
- Constant delta across all rows: a bound, anchor, or seed value is wrong.
- Delta grows along an ordered axis: telescoping or path dependence is wrong. Fix the recurrence, not the arithmetic.
- Delta confined to a subset of columns, entities, or a date span: a branch, variant formula, or day-count basis differs only there. Localize by comparing a component upstream of the seam.
- Mixed with no pattern: compare an upstream component to find where the divergence enters.

## Local Workbook Inspection

Local `openpyxl` inspection is expected. Optional helpers in `../helpers/` are `dump_anatomy.py` and `dump_workbook.py`; each script's first docstring line is authoritative for purpose, inputs, outputs, and dependencies.

Both helpers read OOXML only. A legacy `.xls` cannot be opened by `openpyxl` at all — inventory it through an alternate reader or convert once to `.xlsx` for inspection, and keep the original `.xls` as the uploaded source. See [Source Identification](./reading-workbooks.md#source-identification).

Before reporting completion, apply the completion rule from [Excel](../excel.md) to the final delivered state.
