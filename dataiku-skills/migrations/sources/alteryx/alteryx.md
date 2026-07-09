---
name: source-alteryx-reference
description: "How to read an Alteryx bundle and the Alteryx semantics needed to extract its business logic faithfully."
---

## Source Identification

`.yxmd` / `.yxwz` / `.yxzp` (UTF-8 XML, root `<AlteryxDocument>`) · `.yxdb` (native binary dataset).

## Reading the bundle (wrong/incomplete inventory)

- Cached `<Properties><MetaInfo>` field schema is STALE (Alteryx skips upstream propagation). Type truth = downstream `AlteryxSelect` only.
- Predictive Tools macros carry EMPTY `GuiSettings/@Plugin`. Real tool type lives in `EngineSettings/@Macro` (a `.yxmc` path). Empty Plugin → check Macro attr.
- `.yxwz` (Analytic App) = same XML schema as `.yxmd`. Solution pairs often ship `solution.yxwz` alone; extension change is the only signal.
- `Action` tool mutates a downstream tool's config at runtime. Default value baked in the source tool ≠ value that produced the expected output. Read the value from the `BrowseV2`-attached TextInput in the solution.
- TextInput data lives INLINE in the XML (`<Data><r><c>…</c></r>`). `.yxzp` = ZIP of `.yxmd` plus packaged data.
- `<Connections>` encode the graph (Join emits Left/Join/Right outputs); node order in the file is meaningless. Walk connections.
- Ground truth = cached `BrowseV2` data OR a shipped expected-output `.yxdb` (read via the `yxdb` PyPI lib: `YxdbReader(path=...)`, fields at `r._fields`, type attr `data_type`). Cached BrowseV2 can be EMPTY. Solution tool params may DISAGREE with cached output (author edited params after capture) — trust cached output for values, params only for which-field/where.
- `.yxdb` Date/DateTime fields are timezone-naive.
- Non-primary outputs carry logic: `Filter` False, `Unique` Duplicate, `Join` unmatched anchors often feed downstream. Planning only the primary output silently drops that branch.
- A terminal `Browse` is often the real deliverable in analyst workflows (`Output Data` tool absent). Treat a consumed or terminal Browse as an output.
- `.yxzp` references macros plus bundled data by RELATIVE path. Resolve every relatively-referenced dependency before inventory; a missed one silently drops its logic.
- A project often spans SEVERAL workflow files (`.yxmd`/`.yxzp`) sharing `.yxdb` intermediates or an external model — train in one, score in another.
- `DynamicRename` / `DynamicSelect` / macro-interface `Action` resolve column names at RUNTIME. Captured static names diverge when names depend on runtime data — read the controlling value, Open Item when data-driven.

## Alteryx semantics (silent meaning changes)

- `<FormulaField size="N">` truncates the formula's string result to N chars at write; downstream split/regex sees the shorter input. (`AlteryxSelect size` is a width hint only.)
- `*No0` Summarize actions (`AvgNo0`/`SumNo0`/`MinNo0`/`MaxNo0`/`CountNo0`) ignore ZERO as well as null.
- `PearsonCorrelation` substitutes 0 for null cells; pairwise-complete deletion diverges.
- Null three-valued logic: `[a] = Null()` is null (use `IsNull`). String null is distinct from empty: `IsNull("")` false, `IsEmpty("")` true. Numeric null propagates through arithmetic.
- Truthiness: `IF [x]` is true on non-zero/non-empty, FALSE on null.
- Mixed-type comparison auto-casts: `"5" = 5` is true.
- Implicit numeric→string cast: `[id] + "_label"` concatenates.
- `Round` is half-away-from-zero.
- `FixedDecimal(p.s)` is exact decimal — drift-free.
- String join keys / comparisons are case-sensitive; null keys route to Left/Right anchors only.
- `MultiRowFormula` / `RunningTotal` evaluate AFTER sort, in input row order.
- `MultiRowFormula` `<OtherRows>Nearest` returns the partition's first/last edge value at the boundary.
- `Union` aligns by NAME, POSITION, or manual config. Read the Union mode.
- `Transpose` folds the selected columns to rows, keeping rows whose folded value is null.
- `Unique` keeps the FIRST row per KEY-SUBSET and preserves non-key columns — key-subset grain, full-row distinct diverges.
