# SAS DATA Step to Dataiku

Translation details for DATA step constructs and file IO.

## DATA step → recipe

| SAS construct | Recipe | Type | Notes |
|---|---|---|---|
| DATA step (filter/rename/compute) | Prepare | Visual | Processors: filter rows, rename, formula |
| DATA step (merge by key) | Join | Visual | `MERGE ... BY` |
| `merge A(in=a) B(in=b); by k; if a;` | Join (LEFT) | Visual | Keeps all A rows |
| `merge A(in=a) B(in=b); by k; if a and b;` | Join (INNER) | Visual | |
| `merge A(keep=c1 c2)` | Join + post-Prepare `add-delete-columns` | Visual | No `--keep-columns` flag — drop in a post-join Prepare |
| `SET ds1 ds2` (append) | Stack | Visual | |
| Sort + `if first.key` dedup | Sort + Prepare (RemoveDuplicates) | Visual | Keep first per group |
| Sort + count per group | Group | Visual | Not RETAIN — just aggregation |
| RETAIN with row comparison | SQL recipe | Code | `LAG()`/`LEAD()` window |
| Running total / cumulative | SQL recipe | Code | `SUM() OVER (ORDER BY ...)` |
| Hash object lookup | Join | Visual | Hash = in-memory lookup with equality keys |
| Multiple outputs (IF/OUTPUT) | Multiple Prepare filters | Visual | One filter per output |
| `DO i = 1 TO n` generating rows | Python recipe | Code | Loops that create rows from nothing — see § DO loops & SELECT |
| `DO WHILE` / `DO UNTIL` | Python recipe | Code | State-dependent row generation |
| `ARRAY` + `do over` (column-wise) | Prepare (one step per column) | Visual | Unroll the loop — see § ARRAY + `do over` |
| `ARRAY` with index-dependent expression | Prepare, N `add-formula` steps | Visual | Unroll |
| `ARRAY` cross-column shift (`a[i] = a[i-1]`) | Python recipe | Code | Needs state |
| `UPDATE` statement | Prepare + Join | Visual | Applies only non-missing values from transaction |
| `MODIFY` (in-place) | Python recipe | Code | No Dataiku equivalent — write a new dataset |
| `DATA _NULL_` (compute/log only) | Python recipe (no output) | Code | Or drop if the body was `put` / `file log` only |
| `SELECT/WHEN/OTHERWISE` | Prepare (FindReplace or nested `if()` formula) | Visual | Multi-branch conditional — see § DO loops & SELECT |
| `INFILE` + `INPUT` statement (external file) | Dataset upload + `sync` | — | See § External-file I/O |
| `FILE` + `PUT` statement (write external file) | Dataset download / Export | — | See § External-file I/O |

## RETAIN is usually not Python

Most RETAIN patterns are group aggregations or window functions. Classify before coding.

| SAS pattern | Actually is | Recipe |
|---|---|---|
| Sort + `if last.key then output` with count | Group count | Group |
| Sort + `if first.key then output` | Keep first per group | Sort (desc) + RemoveDuplicates |
| Sort + `if last.key then output` | Keep last per group | Sort + RemoveDuplicates |
| `retain counter; if first.key then counter=0; counter+1;` | Group count | Group |
| `retain max_val; if val > max_val then max_val=val;` | Group max | Group |
| `retain sum_val; sum_val + val; if last.key then output` | Group sum | Group |
| `retain last_plan; if plan ne last_plan then ...` | Row comparison | SQL recipe (`LAG` window) |
| `retain balance; balance + amt;` (all rows) | Running sum | SQL recipe (`SUM() OVER (ORDER BY ...)`) |
| `cumsum + x;` (SUM statement) | Running sum (missing-safe, treats `.` as 0) | SQL recipe |
| `retain prev; diff = val - prev; prev = val;` | Lag difference | SQL recipe (`val - LAG(val) OVER (...)`) |

**SUM statement vs explicit RETAIN+add:**
- `total + x;` (SUM statement) — auto-retains, treats missing `x` as 0. Safe.
- `retain total 0; total = total + x;` — when `x` is missing, `total` becomes `.` permanently. Dangerous.

Migration must check which pattern the SAS code uses. If SUM statement → `COALESCE(val, 0)` in SQL.

---

## ARRAY + `do over`

SAS arrays apply the same expression to many columns. Most patterns are column-wise and unroll into Prepare — the loop is SAS's way of spelling out "apply the formula to each of these columns".

```sas
array nums{*} x1-x10;
do over nums;
    nums[_i_] = coalesce(nums[_i_], 0);
end;
```
→ a single `fill-empty` step on `x1..x10`, or ten `add-formula` steps if the expression varies per column.

| SAS pattern | Recipe | Note |
|---|---|---|
| `array a{*} c1-c10; do over a; a[_i_] = f(a[_i_]); end;` | Prepare, one step per column | Unroll the loop |
| `array a{*} x1-x10; do i = 1 to 10; total + a[i]; end;` | Prepare formula `coalesce(x1,0)+…+coalesce(x10,0)` | Row-sum across columns. `NumericalCombinator` (op: `ADD`) handles the common case |
| `array out{10} y1-y10; do i = 1 to 10; out[i] = input * coef[i]; end;` | Prepare, N `add-formula` steps | Index-dependent expressions — unroll |
| `array history{*} h1-h60; do i = 60 to 2 by -1; history[i] = history[i-1]; end;` | Python recipe | Cross-column shift needs state |
| Variable-size array driven by `&count` macro | Python recipe with dynamic column list | Column count resolved at runtime |

**Array gotchas:**
- `_i_` is the automatic index inside `do over`. Regular `do i = ...` uses `i`.
- `array _numeric_` / `array _character_` take every numeric / character variable currently in the PDV — resolve to an explicit column list before migrating, then treat as a normal array.
- Array subscripts are 1-based and SAS raises `Array subscript out of range` at runtime. GREL silently returns missing on out-of-range list access — if the SAS code relied on the error, document the bound explicitly.

## DO loops & SELECT/WHEN in the DATA step

Non-macro `DO` blocks inside a DATA step usually reduce to a visual recipe — most of the time the loop is a row-wise aggregation or a column-wise array walk. Python is only needed when the loop generates rows from nothing or carries state across iterations.

| SAS pattern | Recipe | Note |
|---|---|---|
| `do i = 1 to 10; output; end;` (generate rows) | Python recipe | Explode from one row to N — no visual equivalent |
| `do i = 1 to n; sum + x[i]; end;` (reduce over array) | Prepare formula or Group | Column-wise reduce — see § ARRAY + `do over` |
| `do while (balance > 0); balance = balance - pmt; end;` | Python recipe | Iterative state per row |
| `do until (converged); …; end;` | Python recipe | Same — needs cross-iteration state |
| `do i = 1 to n by 2;` | Unroll in Prepare, or Python if n is data-driven | `by` step controls the subset |

`DO WHILE` checks at the **top** — may not execute. `DO UNTIL` checks at the **bottom** — always runs at least once. Preserve the check order when translating.

### `SELECT/WHEN/OTHERWISE`

```sas
select (region);
    when ('EMEA')            rate = 0.18;
    when ('NA', 'LATAM')     rate = 0.12;
    when ('APAC')            rate = 0.09;
    otherwise                rate = 0.15;
end;
```
→ Prepare with either a `FindReplace` step (best when the mapping is key→value only) or a formula:
```bash
dku recipe add-formula prep --column rate \
    --expr 'if(region == "EMEA", 0.18, if(region == "NA" || region == "LATAM", 0.12, if(region == "APAC", 0.09, 0.15)))' \
    -P PROJ
```

Block-form `when` with multiple statements → one `add-formula` per target column, each wrapping the same `if(region == ..., …)` branches. Don't try to emulate a multi-statement `when` block with a single step — unroll per output column.

The value-less form `select; when (cond) ...; otherwise ...;` is a chain of conditionals — identical translation.

## Log, debug & control-flow statements (drop these)

A cluster of DATA-step statements exist only to write to the SAS log, mutate internal state flags, or do intra-step `GOTO`. None of them have a recipe equivalent and most shouldn't be preserved — they're implementation detail of how a SAS program reports itself, not business logic.

| SAS statement | Purpose | What to do |
|---|---|---|
| `ABORT` | End DATA step, job, or session with a return code | Drop. Pre-run data validation moves to scenario checks (§ Scheduling) |
| `ERROR 'msg';` | Sets `_ERROR_=1` and writes to log | Drop. A recipe that encounters bad data should either fail (raise in Python) or filter the bad rows (Prepare) |
| `PUTLOG 'msg' var=;` | Write to SAS log | Drop. For a Python recipe, `print()` goes to DSS job logs. For visual recipes, there's no log writer — that's not a failure, just not a thing |
| `LIST;` | Dump the current input record to the log | Drop. Debugging aid only |
| `LOSTCARD;` | Resynchronize multi-line input when a record is missing | Drop. Upload the file, Prepare/Python to reshape if layout is irregular |
| `REDIRECT;` | Reassign input/output datasets at runtime for stored programs | Drop. Stored DATA step programs don't migrate as-is |
| `DESCRIBE;` | Extract source code from a stored compiled program | Drop. Metadata utility |
| `EXECUTE;` (DATA-step) | Run a stored compiled program | Drop. Migrate the underlying program as its own recipe |
| `REMOVE;` / `REPLACE;` (with MODIFY) | Delete / replace in-place in a SAS data set | See § DATA step → recipe row for `MODIFY` — migrate as a Python recipe writing a new dataset |
| `DISPLAY windowname;` / `WINDOW name ...;` | Pop up interactive character-mode windows (legacy SAS/AF) | Drop. Not a batch-pipeline concept |
| `LABEL var='...';` (statement) | Assign a descriptive label | Drop during migration — or, if the label matters for reporting, set `--long-desc` on the output dataset. The column-level label isn't exposed via `dku dataset set-schema` today |
| `Label:` (colon, line label) + `GOTO Label;` / `LINK Label;` | Intra-step jumps | Drop. Refactor the logic into `if/else` + `return` when translating. A `LINK … RETURN` pair is a reusable subroutine → extract into a Python helper |
| `LEAVE;` / `CONTINUE;` | Break out of / skip a DO loop iteration | Drop. When unrolling a `do` loop into Prepare steps, the control flow disappears; when translating to Python, the native `break` / `continue` works directly |
| `DATA _NULL_;` with only `file log`/`put` | Log-only DATA step | Drop the entire step |

Why drop instead of translate: these statements encode how the SAS program debugs or steers itself. Their presence does not imply the surrounding logic is non-migratable — read through them to the actual computation and migrate that. Flag in Phase 1 inventory as *"step N contains log/debug statements only — no output"* so the user confirms before you drop.

## External-file I/O (INFILE / INPUT statement, FILE / PUT statement)

The `INPUT()` and `PUT()` *functions* (covered in § Function mapping) convert between strings and numerics in memory. The `INPUT` / `PUT` *statements* and their companions `INFILE` / `FILE` read and write external files — they're how SAS does ingest and export.

| SAS statement | What it does | Dataiku equivalent |
|---|---|---|
| `infile '/path/file.csv' dsd firstobs=2;` + `input a $ b c;` | Read delimited external file | Upload → `--type UploadedFiles`, then `sync` to the target connection. Set schema after upload (defaults to all STRING) |
| `infile 'file.dat' column=@c1-c9 @10 d 8.;` | Read fixed-width | Upload as raw, then Prepare with `SplitColumn` / `substring()` per field, or a Python recipe if the layout is dense |
| `infile datalines; input ...; datalines; ...;` | Inline test data | Not migrated — treat as test fixture; write the inline rows to a CSV and upload only if the pipeline actually needs them |
| `infile 'file' missover / truncover / stopover` | Missing-field behavior | Upload then Prepare — pad with `fill-empty` for MISSOVER / TRUNCOVER; raise via schema validation for STOPOVER |
| `infile '&path' filevar=f end=eof;` | Loop over many files | Dataset with file pattern (`path/*.csv`) or a Python recipe iterating a managed folder |
| `file '/path/out.dat';` + `put a $ b c;` | Write formatted external file | Dataset download, or Sync recipe to a Filesystem / cloud connection. For fixed-width output, a Python recipe building the line and writing to a managed folder |
| `file log;` + `put ...;` | Log diagnostic | DSS job logs capture `print()` from a Python recipe — don't migrate as a pipeline step |
| `file print;` + `put ...;` | Printed report | Dashboard tile or `PROC REPORT`-style aggregate — not a recipe output |
| `%include 'config.sas';` pointing at a data file | Not I/O — macro include | See SKILL.md § `%include` chains |

**Inventory rule:** during Phase 1, list every `INFILE` / `FILE` statement and map each to an upload / sync / download step before planning the downstream DATA steps. Getting the ingest wrong silently casts columns to STRING and breaks every downstream filter.

---
