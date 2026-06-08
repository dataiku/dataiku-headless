# GREL formula reference

Expression language for Prepare recipes, computed columns, formula processors,
and CUSTOM-mode filters. Return formulas as plain text, no fences.

## Function names are case-sensitive — one wrong letter = `Unknown function`

| Correct | WRONG |
|---|---|
| `toLowercase(s)` | `lower`, `toLowerCase` |
| `toUppercase(s)` | `upper`, `toUpperCase` |
| `toTitlecase(s)` | `toTitleCase` (capital C fails) |
| `toString(o)` | `str`, `string` |
| `toNumber(o)` | `int`, `float` |
| `isNonBlank()` | `isNotBlank` |
| `isNotNull()` | `isNonNull` |
| `diff(d1,d2,unit)` | `dateDiff`, `daysBetween`, `monthsBetween` (none exist) |
| `asDateOnly("2024-01-01","yyyy-MM-dd")` | `date(...)` (no bare constructor) |

## Column access — `val`/`numval`/`strval` need a QUOTED name

- `column_name` — bareword, returns the cell value (GREL auto-coerces in arithmetic).
- `numval("col")` — numeric; `strval("col")` — string (`""` for empty);
  `strval("col", default)`; `val("col", default, offset)`.

**The bareword form `numval(col)` silently returns empty** — DSS parses `col` as
an undefined variable. Same for any non-literal first arg:
`numval(split(s,"-")[0])` is silently empty — use `toNumber(split(s,"-")[0])`
for expression→number. Columns with spaces: `numval("Sales Rep")` — NOT
backticks (`` `Sales Rep` `` raises `ParsingException at offset 0`).

Type pitfalls:
- `numval(int_col)` returns a **double** → `"X" + numval("rank")` yields
  `"X1.0"`. Strip with `replace(... + "", /\.0$/, "")` (regex form).
- `strval(numeric_col)` returns `""` (string accessor on non-string). To cast a
  number to string use `concat("", numval("col"))` — and this is what survives
  SQL push-down (`toString`/`"" + col` do not; see below).

## Conditionals, null & logic

```
if(cond, t, f)                switch(expr, m1, r1, m2, r2, ..., default)
and(a,b) / a && b   or(a,b) / a || b   not(b)   with(expr, name, body)
coalesce(v1, v2, ...)         // first non-null
isBlank(x)                    // null or empty string
isNull(x)                     // null/empty, treats whitespace as null
isNonBlank(x)  isNotNull(x)  isError(expr)
```

**`col == null` does NOT detect missing values** — silently falsy, so
`if(col == null, fallback, col)` always takes the else branch and propagates the
null. Always use `isBlank(col)` (or `isNull(col)` if whitespace must NOT count).

## Strings

```
concat(a,b,...) / a + b   contains(s,frag)   startsWith / endsWith
replace(s, "sub", r)              // LITERAL substring
replace(s, /pat/, r)              // REGEX (must be /.../-delimited)
replaceChars(s, from, to)   split(s, sep) -> array   join(arr, sep)
trim(s) / strip(s)   toLowercase / toUppercase / toTitlecase
substring(s, from, to)            // 0-based, `to` is EXCLUSIVE index (not length)
length(s)   indexOf(s,sub)   lastIndexOf(s,sub)   chomp(s,tail)
match(s, /pat/)                   // capture groups; WHOLE-STRING match (Java matches())
char(code)   ord(s)   format('%05d', n)   // Java String.format
```

**`match()` matches the WHOLE string** (not `re.search`). To extract from
mid-string, consume the surroundings: `match("...334-288-3900", /.*?(\d{3}-\d{3}-\d{4}).*/)`.
`replace(s, /pat/, ...)` has no such restriction.

## Numbers

```
round(n)            // nearest int — 1 ARG ONLY; round(n,2) silently empty -> use round(n*100)/100
ceil(n) floor(n) abs(n) sqrt(n) pow(a,b) mod(a,b) quotient(a,b)
min/max/sum/avg(a,b,...)   // VARARGS, not sum(column)
ln(n)               // natural log
log(n)              // BASE-10 (not natural!)   exp(n) // base-e
even(n) odd(n) rand() PI()
```

**No trig** (`sin`/`cos`/`atan2`/`radians` don't exist) → haversine can't be
done in GREL. For distance use the visual path (`add-geopoint` → `create-geojoin`
→ `add-geodistance`), or SQL/Python. Avoid GREL `geoDistance()` for accumulated
trip distance — it rounds to 2 decimals and uses a different spheroid than the
`add-geodistance` Prepare processor (full-precision doubles).

## Dates

```
now()   datePart(d, "years"|"months"|"days"|...)   diff(d1, d2, "days")  // NOT dateDiff
inc(d, n, "days"|"months"|...)   trunc(d, "months")
asDateOnly(s, fmt)   asDatetimeNoTz(s, fmt)   asDatetimeTz(s, fmt)
```

Parts: `years months days weeks hours minutes seconds dayOfWeek weekDay weekOfYear`.

**Date columns carry `00:00:00` time suffix** — `asDateOnly()` vs a date column
crashes (`malformed at "T00:00:00.000Z"`). Cast both to `yyyy-MM-dd` strings:
`substring(strval(col), 0, 10)`. Same-month: `substring(strval(d),0,7) == ...`.

## Arrays / type / JSON / hash / HTML

```
forEach(a,v,expr)  filter(a,v,test)  forEachIndex(a,i,v,expr)  forRange(from,to,step,v,expr)
arrayLen(a) arrayContains(a,x) arraySort arrayReverse arrayDedup arrayIndexOf get(a,i)
toNumber(x) toString(x) asBool(x) isNumeric(x) type(x)
parseJson(s) jsonize(v) objectNew(k,v,...) objectKeys/Values hasField(o,n) get(o,f) getPath(o,"a.b.c")
md5 sha1 sha256 sha512 hash hex2dec dec2hex uuid()
parseHtml(s) htmlText(e) ownText(e) innerHtml(e) htmlAttr(e,"href")
geoContains(outer,inner) geoBuffer(g,d) geoEnvelope(g) geoSimplify(g,tol) geoMakeValid(g)
```

Broken/missing: `select(el, sel)` → `StackOverflowError` (use `htmlText()`);
`ngram()` does not exist.

## GREL → SQL push-down (when Prepare input AND output are on one SQL connection)

| GREL | breaks because | use instead |
|---|---|---|
| `toString(col)` | wrapper stripped, type unchanged | `concat("", col)` |
| `"" + col` (numeric) | SQL `+` is numeric addition | `concat("", col)` |
| `strval(col)` no default | version-inconsistent | `concat("", col)` or `strval(col, "")` |
| `round(x*10)/10` on DOUBLE | engine-dependent rounding | `floor(x*10 + 0.5)/10` |
| `concat(num1, num2)` | may compile to addition | wrap one in `""`: `concat("", a, b)` |

Rule: for int→string casts that must push down, always `concat("", col)`.

## Output-type inference (computedColumns / formula steps)

`apply-schema` infers the column type from the expression. **Formula columns
default to STRING** when branches disagree or the result is empty —
`toNumber(...)` is inferred `bigint`/`double`; `split(...)[i]` stays string.
Two silent-STRING traps: (1) an always-empty expression (`numval` given an
expression); (2) editing the formula after the output schema is already locked
(`apply-schema` reports "no updates needed"). Fix either with
`dku dataset set-schema OUT -P PROJ -d '[...]'` to lock the type, then re-run.
Reverse trap: a string expression auto-cast to bigint because all sampled values
are digit-only — wrap with `concat("", ...)` or set-schema to STRING.

Always run `apply-schema` after adding formula steps (and again after adding
rename/select steps to an existing Prepare recipe).

## Quick gotchas

- `round()` 1-arg only; `log()` base-10, `ln()` natural, `exp()` base-e.
- `substring(s,from,to)` — `to` exclusive index, NOT length.
- `count()` doesn't exist in formulas (only Group aggregation); use `arrayLen()`.
- Leading zeros: wrap in `strval(column)` to preserve.
- `forEach` returns an array — `join()` for a string.

## Date-overlap formula

```
if(end1 >= start2 && end2 >= start1, diff(min(end1, end2), max(start1, start2), "days") + 1, 0)
```

Work in days only (`asDateOnly` inputs or trimmed datetimes).

## Examples

| Want | Formula |
|---|---|
| First + last name | `concat(first_name, " ", last_name)` |
| Flag active | `if(status == "active", 1, 0)` |
| Map codes | `switch(cat, "A", "Premium", "B", "Standard", "Unknown")` |
| Year from date | `datePart(date_column, "years")` |
| First 3 chars | `substring(text, 0, 3)` |
| Round 2dp | `round(value * 100) / 100` |
| Days between | `diff(start, end, "days")` |
| Leading zeros | `format('%05d', id)` |
| Default if empty | `coalesce(field, "Unknown")` |
| Safe divide | `if(b == 0, 0, a / b)` |
| Date overlap (days) | `if(end1 > start2 && end2 > start1, diff(min(end1, end2), max(start1, start2), "days") + 1, 0)` |
