---
name: source-sas-reference
description: "How to read a SAS bundle and the SAS semantics needed to extract its business logic faithfully."
---

## Source Identification

`.sas` (text program), `.egp` (Enterprise Guide ZIP archive), `.flw` (SAS Studio flow, JSON).

## Reading the bundle (wrong/incomplete inventory)

- `.egp` `project.xml` is UTF-16; decode utf-16, else garbled.
- `.egp` Query Builder generated SQL lives in `Query-*/Log-*/result.log` only, on `s`-prefixed lines.
- `.flw` flow graph = nodes plus connections.
- `datalines;` / `infile datalines;` blocks = test fixtures; keep out of production inputs.
- `.sas7bdat` numerics store as float; casting an id/key column to integer loses or drops values. Keep numeric keys as stored until confirmed integral.
- `%macro` = code generator: capture what it GENERATES at each call site only. Shared utility/function-style macros (`%mf_*`, `%mp_*`) expand per call site.
- `proc sql; connect to <engine>...` passthrough = ingest (what the warehouse delivers to WORK); model as one input dataset.
- Implicit OUTPUT: zero explicit OUTPUT statements → one row per iteration. ANY explicit OUTPUT suppresses implicit entirely — OUTPUT inside an IF acts as a filter, dropping non-matching rows.
- BY-less `merge A B;` = positional pairing by row number (output = largest input); BY-less `set A; set B;` = positional (output = smallest). Key join requires BY.
- Trailing `:` on a MERGE dataset name = prefix wildcard; merges ALL datasets matching the prefix.
- `%include` pulls an external `.sas` into the program; a missed include silently drops its logic. Resolve every `%include` before inventory.

## SAS semantics (silent meaning changes)

- Missing `.` = negative infinity for numeric comparison and sort; a lower-bound WHERE drops missing rows.
- Missing propagates through arithmetic.
- Blank string IS missing; numeric 0 is non-missing.
- Bare numeric truth test (`if var then`) is FALSE on 0 OR missing.
- Division by zero yields missing; the step continues.
- Char comparison ignores trailing blanks.
- Char length locks at first assignment or LENGTH statement; a later longer value truncates. Check LENGTH statements before SET/MERGE.
- `format var fmt.;` is display-only — stored value persists; `var = put(var, fmt.);` IS a value transform.
- `<>` in a DATA-step expression = MAX (`><` = MIN); only in WHERE/PROC SQL does `<>` mean not-equal.
- SUM statement `total + x;` auto-retains and treats missing x as 0. `retain total 0; total = total + x;` makes total permanently missing on the first missing x. Which form changes the result.
- PROC SQL selecting an aggregate alongside an unaggregated column auto-remerges the global stat onto every row (log: "requires remerging summary statistics") — read as a per-row group statistic.
- PROC SQL `calculated alias` (reference a computed column in the same SELECT) and `GROUP BY` with detail columns (remerge) are SAS-only.
- MERGE many-to-many = parallel walk within group (rows = max(countA, countB), shorter side carries its last value) — distinct from SQL's Cartesian join.
- MERGE common (non-BY) variable: the last-listed dataset wins.
- `update master transaction; by k;` overwrites master with transaction's NON-missing values only.
- `LAG()` is a queue, one push per call; wrapping it in IF skips pushes and desyncs the queue.
- PROC UNIVARIATE/MEANS standard-deviation default denominator is n-1 (sample); quantile default QNTLDEF=5 ≈ averaged-inverted-CDF.
- ROUND is half-away-from-zero for any sign.
- `INTCK('month'/'year', d1, d2)` counts boundary crossings only.
- SAS dates/datetimes are numeric serials (days/seconds since 1960-01-01).
- Special missing `.A`–`.Z` (28 subtypes) carry category meaning; the subtype is a distinct category.
- `FIRST.`/`LAST.` flags cascade hierarchically: a change in an outer BY key resets every inner key's flags; group boundaries follow the full BY list.
- WHERE-only operators (rejected in subsetting `IF`): `CONTAINS`/`?` = case-sensitive substring, `=:` = truncate-to-shorter prefix match, `=*` = SOUNDEX, plus `SAME-AND`. Translate each by meaning.
- `PROC SORT NODUPKEY` keeps the first row per BY-key; `NODUP`/`NODUPRECS` removes exact full-row duplicates only. Different grain.
- `DO WHILE (cond)` tests at the top (may run zero times); `DO UNTIL (cond)` tests at the bottom (runs at least once).
- `CALL SYMPUT` and PROC SQL `SELECT INTO :var` create the macro variable in LOCAL (enclosing-macro) scope; cross-scope use requires `%GLOBAL`/`'g'`, else it resolves empty.
