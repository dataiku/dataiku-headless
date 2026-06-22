# Native ingestion — reshape sheets to tidy with visual recipes

How to turn messy workbook sheets into tidy (long) DSS datasets **without a Python staging script**. Read `overview.md` first (native format, `create-from-file`, format-params table). This is the deeper playbook for sheets that aren't one clean rectangle.

## Principle — native in, visual reshape, no Python

Upload the workbook as native sheet-targeted datasets and reshape to tidy tables with visual Prepare recipes only. Folds, fill-down, filters, and renames cover every messy-sheet case. The payoff over a Python export script: the reshape stays **on the flow graph**, it **re-runs when next cycle's workbook is dropped in**, and it obeys the Visual→SQL→Python altitude rule (SKILL.md rule 1). A Python recipe is a fallback only for a sheet too pathological for visual recipes — and even then it is scaffolding to be replaced by a source-system connection.

## One dataset per sheet selection (not a smell)

```bash
dku dataset create-from-file in1   book.xlsx --sheet "In1" -P PROJ
dku dataset create-from-file lines book.xlsx --sheet-indices "13,15" --sheets-to-column -P PROJ
```

The same workbook file feeds several datasets, one per sheet or sheet-selection — that is the native pattern. Per sheet, set format params explicitly and re-detect:

- `parseHeaderRow: true` + `skipRowsBeforeHeader: N` — **autodetect picks DATA rows as the header** on sheet-targeted reads; set the title-row offset yourself.
- `preserveNumberFormatting: false` — `true` renders numerics with display formatting and a typed schema then reads them null (it nulled a swathe of typed rows in one build before this was set).
- After hand-editing params: `dku dataset detect --keep-format --infer-types --save` (plain `detect --save` re-detects the format and snaps back to sheet 0).

## The reshape toolkit — messy sheet → tidy

| Mess in the sheet | Visual fix |
|---|---|
| Wide month columns (`Jan-19, Feb-19, …`) | `add-fold --pattern '^[A-Z][a-z]{2}-[0-9]{2}$' --key-column month --value-column value` (emits `MultiColumnByPrefixFold`). Fold **silently drops rows whose folded value is null** — `add-fill-empty` first if those rows matter |
| Merged-cell keys (only the top-left cell holds the value, rest read null) | `UpDownFiller` fill-down on the key column |
| Same-layout sheets to union (e.g. In2+In4; a DEFAULT + an OVERLAY assumption layer) | `create-from-file --sheet-indices "a,b" --sheets-to-column` — the sheet name becomes the tag/version column, zero recipes |
| Lookup/clone rows that duplicate real rows (VLOOKUP rows, a selected-scenario copy row) | filter them out by a **fingerprint** column that is blank/zero only on the clones; dedupe scenario-copies with `create-distinct` |
| Title / doc rows above the header | `skipRowsBeforeHeader: N` — never a Prepare |

## GREL for date/number reshaping — the xlsx-specific bits

- **No `formatDate`.** Build an ISO month from a parsed date with `format`: `format("%04d-%02d-01", datePart(d, "years"), datePart(d, "months"))` (`datePart` months are **1-based**).
- **Month label → month-end:** `inc(inc(asDateOnly(lbl, "MMM-yy"), 1, "months"), -1, "days")`.
- **A bare `null` literal in a formula errors.** Return `""` and guard: `if(isBlank(x), "", …)`.

(General GREL traps — `strval()` on a non-string column → `""`, no leading unary minus, etc. — live in `../../dku-cli/references/formulas.md`.)

## Grafting native ingestion under an existing flow

`dku recipe replace-input OLD_DS NEW_DS -P PROJ` re-wires every consumer of a dataset in one call (no recipe rebuild) — the clean way to swap a CSV-staged input for the native-reshaped one, or to retarget the `10_inputs` zone at a real source connection once it exists.

## Verify equivalence by row count

The reshape output must match the workbook's Table / used-range row count **exactly** (the Table-ref row-count contract, `overview.md` rule 3). A near-miss — 180 where the table has 181 — is a clone or blank row leaking through; find it, don't shrug. Verifying *values* against the parity reference is the engine's job: `model-workbooks.md` § Verification.

## Reference map

`overview.md` (native format + format-params table) · `model-workbooks.md` § rule 4 (where reshape belongs) · `../../dku-cli/references/prepare-processors.md` (`MultiColumnFold`/`MultiColumnByPrefixFold`/`UpDownFiller` params, fold null-drop) · `../../dku-cli/references/formulas.md` (GREL).
