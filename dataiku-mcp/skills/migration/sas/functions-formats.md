# SAS Functions, Formats, Rounding, and Dates

Function and format mapping from SAS to GREL, SQL, and DSS processors.

## Function mapping (SAS → GREL / SQL / processor)

GREL function names are **case-sensitive**. See `../../dku-cli/references/formulas.md` for the full GREL reference and `../../dku-cli/references/prepare-processors.md` for the processor catalog.

### Core

| SAS | GREL | Wrong guess |
|---|---|---|
| `PROPCASE(s)` | `toTitlecase(s)` | ~~`toTitleCase(s)`~~ — lowercase 'c' |
| `LOWCASE(s)` | `toLowercase(s)` | ~~`lower(s)`~~ |
| `UPCASE(s)` | `toUppercase(s)` | ~~`upper(s)`~~ |
| `PUT(n, BEST12.)` | `toString(n)` | ~~`str(n)`~~ |
| `INPUT(s, BEST.)` | `toNumber(s)` | ~~`int(s)`~~ |
| `SUBSTR(s, pos, len)` | `substring(s, pos-1, pos-1+len)` | GREL is 0-based; `to` is exclusive index, NOT length |
| `ROUND(n, .01)` | `round(n * 100) / 100` for non-negative `n`; for any sign see § Rounding parity | ~~`round(n, 2)`~~ — GREL `round()` takes 1 arg. The short form rounds negatives differently from SAS |
| `INTCK('day', d1, d2)` | `diff(d1, d2, 'days')` | ~~`dateDiff()`~~ — doesn't exist |
| `INTCK('month', d1, d2)` | `diff(d1, d2, 'months')` | SAS counts boundary crossings, not elapsed |
| `LOG(n)` | `ln(n)` | SAS `LOG` = natural log; GREL `log` = base-10 |
| `EXP(n)` | `exp(n)` | Both base-e — consistent |
| `NMISS(a, b, c)` / `CMISS(a, b, c)` | `if(isBlank(a),1,0) + if(isBlank(b),1,0) + if(isBlank(c),1,0)` | Count of missing across columns, per row. Returns integer. No ternary operator in GREL — use `if()` |
| `DATDIF(d1, d2, 'act/act')` | `diff(d1, d2, "days")` | Verify dates are parsed (`asDateOnly(s, "yyyy-MM-dd")`), not raw strings — `diff` on strings throws "Unknown function" |
| `YRDIF(d1, d2, 'act/act')` | `diff(d1, d2, "years")` | SAS `YRDIF` has a `basis` arg (`'30/360'`, `'actual'`, `'act/365'`, `'act/360'`) — `diff` is always actual. For non-actual basis, compute in days and divide |
| `RANUNI(seed)` / `RANNOR(seed)` | Python recipe: `random.seed(seed); random.random()` / `random.gauss(0, 1)` | No GREL RNG. Seeded reproducibility needs Python |

### String

| SAS | GREL | Note |
|---|---|---|
| `TRIM(s)` | `strip(s)` | SAS `trim` removes trailing only; GREL `strip` is both sides |
| `STRIP(s)` | `strip(s)` | Same — both sides |
| `LEFT(s)` | `strip(s)` | SAS left-aligns; closest is `strip` |
| `COMPRESS(s)` | `replace(s, ' ', '')` | Removes all spaces |
| `COMPRESS(s, chars)` | chained `replace(...)` | One per character |
| `COMPRESS(s, , 'kd')` | no direct GREL | Keep only digits — use SQL `REGEXP_REPLACE` |
| `SCAN(s, n)` | `split(s, ' ')[n-1]` | SAS is 1-based; GREL array is 0-based |
| `COUNTW(s)` | `split(s, ' ').length()` | |
| `INDEX(s, sub)` | `indexOf(s, sub)` | SAS returns 0 if not found; GREL returns -1 |
| `FIND(s, sub, 'i')` | `indexOf(toLowercase(s), toLowercase(sub))` | Case-insensitive |
| `TRANWRD(s, old, new)` | `replace(s, old, new)` | |
| `CATS(a, b, c)` | `strip(a) + strip(b) + strip(c)` | |
| `CATX(sep, a, b, c)` | `join([strip(a), strip(b), strip(c)], sep)` | |
| `CAT(a, b)` | `a + b` | Preserves padding (rarely wanted) |
| `LENGTH(s)` | `length(s)` | |
| `IFC(cond, t, f)` | `if(cond, t, f)` | Inline character |
| `IFN(cond, t, f)` | `if(cond, t, f)` | Inline numeric |
| `COMPBL(s)` | `replace(s, /\s+/, " ")` | Collapse runs of whitespace to one space. No dedicated processor — the `StringTransformer` NORMALIZE mode does more than this (lowercase + accent strip) |
| `COUNT(s, sub)` | `(length(s) - length(replace(s, sub, ""))) / length(sub)` | Counts substring occurrences. Returns a double (`2.0`, not `2`) — wrap in `toInt(...)` if integer type needed downstream |
| `COUNTC(s, chars)` | Chained `length(s) - length(replace(s, c, ""))` per char, summed | One subtraction per character class. For large char sets use a Python recipe |
| `TRANSLATE(s, to, from)` | Chained `replace(replace(s, from_ch1, to_ch1), from_ch2, to_ch2)` | **SAS arg order is `(s, to, from)`, not `(s, from, to)`** — silent source of wrong values if copied blindly |
| `REVERSE(s)` | Python recipe: `df["rev"] = df["col"].str[::-1]` | No GREL string reverse. `arrayReverse` exists but takes an array, not a string |

`COMPRESS` modifiers: `k` = keep (instead of remove), `d` = digits, `a` = alpha, `s` = spaces, `p` = punct. `compress(s, , 'kd')` = keep only digits.

### Geography / reference-data lookups

SAS ships reference tables (`SASHELP.ZIPCODE`, `SASHELP.US_DATA`) and functions (`STFIPS`, `STNAME`, `ZIPSTATE`) that don't exist in Dataiku. The SKILL.md non-migratable patterns table flags this; at the function level:

| SAS | Dataiku answer |
|---|---|
| `STFIPS(state)` / `STNAME(fips)` / `ZIPSTATE(zip)` | Join against a reference dataset (user-provided CSV of state ↔ FIPS ↔ ZIP mappings). No Dataiku function or plugin ships this data |
| `ZIPCITYDISTANCE(zip1, zip2)` | Resolve each ZIP to lat/lon via reference join, then `GeoPointCreator` + `GeoDistanceProcessor` (or `dku recipe add-geopoint` + `add-geodistance`) |
| `GEODIST(lat1, lon1, lat2, lon2)` | Two processors: `GeoPointCreator` on each lat/lon pair, then `GeoDistanceProcessor` between the two geopoint columns. Not available as a one-line GREL function |

Prompt the user for the reference CSV during Phase 1 inventory — don't silently drop these functions.

### Dates (SQL recipe equivalents — engine-specific)

SAS date functions don't have a single portable SQL equivalent. The column below shows the most common shape, but **check your target engine** — the exact function name varies (`DATEDIFF` / `MONTHS_BETWEEN` / `DATE_DIFF`), and so does the argument order. See the Postgres-specific forms in § SAS → SQL recipe translations below.

| SAS | Shape (varies per engine) | Note |
|---|---|---|
| `INTCK('month', d1, d2)` | Oracle: `MONTHS_BETWEEN(d2, d1)`; SQL Server: `DATEDIFF(month, d1, d2)`; BigQuery: `DATE_DIFF(d2, d1, MONTH)` | Counts discrete boundary crossings |
| `INTCK('year', d1, d2)` | `DATEDIFF(year, d1, d2)` — check engine syntax | `intck('year', 15MAR2024, 01JAN2026)` = 2 |
| `INTNX('month', d, n)` | MySQL/BigQuery: `DATE_ADD(d, INTERVAL n MONTH)`; Snowflake: `DATEADD(MONTH, n, d)` | Defaults to BEGINNING of target month |
| `INTNX('month', d, n, 'end')` | Wrap the above in `LAST_DAY(...)` if available | End of target month |
| `INTNX('month', d, n, 'sameday')` | Same base `DATE_ADD` / `DATEADD` | Preserves day-of-month |
| `DATEPART(dt)` | `CAST(dt AS DATE)` | Portable |
| `MDY(m, d, y)` | `MAKE_DATE(y, m, d)` (PG/BigQuery) or `DATE(y, m, d)` | Check engine |
| `TODAY()` | `CURRENT_DATE` | Portable |
| `INPUT(s, DATE9.)` | MySQL: `STR_TO_DATE(s, '%d%b%Y')`; Snowflake: `TO_DATE(s, 'DDMONYYYY')`; PG: `TO_DATE(s, 'DDMonYYYY')` | Parses `'15MAR2024'` |
| `INPUT(s, YYMMDD10.)` | `CAST(s AS DATE)` | Portable for ISO dates |

`INPUT(s, COMMA10.)` strips `$` and `,` — use `toNumber(replace(replace(col, '$', ''), ',', ''))`.

### SAS formats → processors

| SAS | Processor |
|---|---|
| `PUT(var, DATE9.)` | `DateFormatter` |
| `PUT(var, COMMA12.2)` | `NumericalFormatConverter` |
| `INPUT(var, BEST.)` | `TypeSetter` (string → numeric) |
| `VALUE` (discrete) | `ColumnCopier` + `FindReplace` |
| `VALUE` (ranges) | `BinnerProcessor` (or formula) |
| `INFORMAT` (parse) | `DateParser` |
| `ROUND(x, .01)` | `RoundProcessor` |
| `MEAN(OF col1-col3)` | `MeanProcessor` |
| `SUM(OF col1-col3)` | `NumericalCombinator` (op: `ADD`) |
| Missing fill (numeric) | `ImputeWithValue` (method: `MEAN`/`MEDIAN`) |
| Missing fill (string) | `FillEmptyWithValue` |
| `RENAME old=new` | `ColumnRenamer` |
| `LOWCASE` / `UPCASE` | `LowerCaseTransformer` / `UpperCaseTransformer` |

### Prepare-step CLI examples

```bash
# Filter by value (SAS: WHERE status = 'A')
dku recipe add-filter-rows RECIPE --column status --values "A" --action KEEP_ROW -P PROJ

# Filter by formula (SAS: WHERE amount > 0)
dku recipe add-filter-rows RECIPE --formula "amount > 0" --action KEEP_ROW -P PROJ

# Remove empty rows (SAS: IF col=. THEN DELETE)
dku recipe add-step RECIPE -t RemoveRowsOnEmpty --params '{"columns":["col"], "keep":false, "appliesTo":"SINGLE_COLUMN"}' -P PROJ

# Formula column (SAS: LTV = MORTDUE / VALUE)
dku recipe add-formula RECIPE -c LTV -e 'MORTDUE / VALUE' -P PROJ

# Impute missing (SAS: IF var=. THEN var=mean)
dku recipe add-step RECIPE -t ImputeWithValue --params '{"appliesTo":"SINGLE_COLUMN", "columns":["MORTDUE"], "method":"MEAN"}' -P PROJ

# Fill empty string
dku recipe add-fill-empty RECIPE --column JOB --value Unknown -P PROJ

# Copy + recode (SAS: IF BAD=0 THEN OUTCOME='Paid')
dku recipe add-step RECIPE -t ColumnCopier --params '{"inputColumn":"BAD", "outputColumn":"OUTCOME"}' -P PROJ
dku recipe add-find-replace RECIPE -c OUTCOME --find "0" --replace "Paid" -P PROJ

# Rename
dku recipe add-rename RECIPE --from MORTDUE --to mortgage_due -P PROJ

# Bin numeric (SAS: PUT(x, spend_tier.) with VALUE format ranges)
dku recipe add-step RECIPE -t BinnerProcessor --params '{"column":"total_spend", "binnerMode":"CUSTOM", "customBoundaries":[500, 5000], "customBoundariesLabels":["Low","Medium","High"], "outputColumn":"spend_tier"}' -P PROJ

# Date parsing
dku recipe add-step RECIPE -t DateParser --params '{"appliesTo":"SINGLE_COLUMN", "columns":["date_col"], "formats":["M/d/yy"], "lang":"auto", "timezone_id":"UTC", "outCol":"", "outType":{"name":"out", "type":"date"}}' -P PROJ

# Date difference (input2 - input1)
dku recipe add-step RECIPE -t DateDifference --params '{"input1":"start", "compareTo":"COLUMN", "input2":"end", "output":"days_diff", "outputUnit":"DAYS", "timezone_id":"UTC"}' -P PROJ
```

### VisualIfRule operators

| Operator | Value field |
|---|---|
| `== [string]` | `string` |
| `!= [string]` | `string` |
| `>  [number]` (2 spaces) | `num` |
| `<  [number]` (2 spaces) | `num` |
| `>= [number]` | `num` |
| `<= [number]` | `num` |
| `contains` | `string` |
| `is empty` / `not empty` | — |

**Broken via API** (DSS bug): `regex`, `in [string]`, date/geo operators. Use GREL `match()` for regex, `switch()` for is-any-of.

---

## Rounding parity

SAS `ROUND(x, step)` is **half-away-from-zero** for any sign. Not every target matches, and the mismatch produces silent off-by-step parity breaks on `.5` boundaries. All four combinations (positive/negative × integer-multiple/double) matter.

| Path | Mode | Matches SAS? |
|---|---|---|
| SAS `ROUND(x, step)` | half-away-from-zero | ✓ (reference) |
| Oracle / SQL Server / Snowflake / BigQuery / Redshift `ROUND` | half-away-from-zero | ✓ |
| PostgreSQL `ROUND(numeric, int)` | half-away-from-zero | ✓ |
| PostgreSQL `ROUND(double precision)` (1-arg) | banker's (half-to-even) | ✗ |
| DuckDB `ROUND(numeric)` / `ROUND(double)` (v0.8+) | half-away-from-zero | ✓ |
| Python `round()` / `numpy.round` / `pandas.Series.round()` | banker's | ✗ |
| **Dataiku Prepare recipe `round(x)` (in-memory, Java `Math.round`)** | **round half up (toward +∞)** | ✓ for positives, ✗ for negatives |

Sample mismatches on `round(x, 1)`:

| x | SAS (half-away) | PG DOUBLE / Python (banker's) | DSS in-memory GREL `round(x*10)/10` |
|---|---|---|---|
| `1.25` | `1.3` | `1.2` | `1.3` |
| `8.25` | `8.3` | `8.2` | `8.3` |
| `-1.25` | `-1.3` | `-1.2` | **`-1.2`** |
| `-8.25` | `-8.3` | `-8.2` | **`-8.2`** |

**Key point**: the common advice "use GREL `round(x * 10) / 10` for 0.1 rounding" matches SAS only for non-negative inputs. Negative inputs diverge on every `.5` boundary. If the column can take negative values, pick one of the workarounds below.

**SQL recipe rule**: most engines match SAS for any sign — just write `ROUND(col, 1)`. On PostgreSQL with `DOUBLE PRECISION` columns, cast to `NUMERIC` first: `ROUND(val::numeric, 1)`.

**GREL workaround for any sign** (works on both in-memory and SQL push-down, verified on DSS 14.4 + PG):
```
if(x >= 0, floor(x * 10 + 0.5) / 10, 0 - floor(0 - x * 10 + 0.5) / 10)
```
The two-branch form handles the negative side correctly. The shorter `floor(x * 10 + 0.5) / 10` is only correct for non-negatives.

**Verification probe**: run `SELECT ROUND(1.25, 1), ROUND(-1.25, 1), ROUND(2.5, 0), ROUND(-8.25, 1)` on your target. SAS-compatible engines return `1.3, -1.3, 3, -8.3`. Anything else needs a cast or the two-branch workaround.

**Python (last resort)**:
```python
import numpy as np

def sas_round(x, step):
    scaled = x / step
    return np.floor(np.abs(scaled) + 0.5) * np.sign(scaled) * step

sas_round(1.25, 0.1)    # 1.3 ✓
sas_round(-1.25, 0.1)   # -1.3 ✓
```

Symptom of a rounding-mode mismatch in a parity check: off-by-step mismatches in rounded columns, always on values ending in exactly `.5`, often concentrated on rows with negative values when GREL `round(x*10)/10` was used blindly.

---

## SAS dates in Dataiku

1. **Ingest as STRING** (ISO `YYYY-MM-DD`). Setting `{"type":"date"}` on an uploaded CSV with string dates causes all values to become null without error.
2. **String-based ISO date filtering works** — lexicographic matches chronological:
   ```
   startsWith(txn_date, "2026-02")                     # "month of Feb 2026"
   txn_date >= "2026-02-01" && txn_date <= "2026-02-28" # range
   max(txn_date)                                        # latest per group
   ```
3. **`dateonly` JSON quirk** — `dku dataset head -o json` renders as `"2026-02-06 00:00:00"` (trailing midnight). Cosmetic; strip the time component in parity checks.
4. **SAS missing date (`.`) → Dataiku null.** In LEFT JOINs with no match, SAS emits `.`, Dataiku emits `null`. Normalize both to `None` in parity checks.
5. **Force `yymmdd10` display format in SAS goldens** used for string parity: change `format=date9.` to `format=yymmdd10.` on any SQL alias you'll compare.

---
