# Dataiku Formula Language (GREL)

Expression syntax used in Prepare recipes, computed columns, and formula-based processors.

## What can be done

- **Generate formulas** from natural language descriptions
- **Debug/fix** broken or erroring formulas
- **Explain** what a formula does
- **Translate** between Formula Language and Python (both directions)

## Output format

Return formulas as plain text—no markdown code fences, no extra explanation unless asked. Just the formula.

## CRITICAL: Function names are case-sensitive

GREL function names use inconsistent casing. Getting one letter wrong produces `Unknown function` errors:

| Correct | WRONG (common mistakes) |
|---|---|
| `toLowercase(s)` | ~~`lower(s)`~~, ~~`toLowerCase(s)`~~ |
| `toUppercase(s)` | ~~`upper(s)`~~, ~~`toUpperCase(s)`~~ |
| `toTitlecase(s)` | ~~`toTitleCase(s)`~~ (capital C fails!) |
| `toString(o)` | ~~`str(o)`~~, ~~`string(o)`~~ |
| `toNumber(o)` | ~~`int(o)`~~, ~~`float(o)`~~ |
| `isNonBlank()` | ~~`isNotBlank()`~~ |
| `isNotNull()` | ~~`isNonNull()`~~ |
| `diff(d1, d2, unit)` | ~~`dateDiff()`~~, ~~`monthsBetween(d1, d2)`~~, ~~`daysBetween(d1, d2)`~~ (none exist — `diff` with unit string is the only form) |
| `asDateOnly("YYYY-MM-DD", "yyyy-MM-dd")` to construct a date constant | ~~`date("YYYY-MM-DD")`~~ (no bare `date()` constructor in GREL — parse the literal with `asDateOnly`) |

## Core syntax reference

### Column access
- `column_name` — returns the cell value directly (bareword identifier)
- `numval("column")` — forces numeric interpretation (column name MUST be quoted string)
- `strval("column")` — forces string interpretation (returns "" for empty)
- `strval("column", default)` — string value with fallback
- `val("column", [default], [offset])` — generic accessor with optional default and row offset

**CRITICAL:** `val`/`numval`/`strval` require a **quoted** column name. The bareword form `numval(column)` silently returns empty string — DSS parses `column` as an undefined variable instead of a column reference. Use `numval("column")` or drop the wrapper and rely on bareword `column` + arithmetic (GREL auto-coerces). Same rule applies when the first argument is any non-literal expression: `numval(split(s,"-")[0], 0)` is silently empty. Use `toNumber(split(s,"-")[0])` for string→number conversion of an expression.

**Column names with spaces:** bareword access only works when the name is a valid identifier. For `Sales Rep`, `Postal Area`, etc., use `numval("Sales Rep")` / `strval("Postal Area")` — DO NOT use `` `Sales Rep` `` (backtick). The GREL parser in prepare filter/formula rejects backticked identifiers with `ParsingException at offset 0`.

**`CreateColumnWithGREL` output type inference:** `apply-schema` infers the output type from the expression. `toNumber(…)` is inferred as `bigint`/`double`; `split(…)[i]` stays `string`; conditional expressions fall back to `string` when the branches disagree. Two pitfalls that make the inferred type *silently* `string`:
1. An expression that evaluates to empty (e.g. `numval(split(Range,"-")[0], 0)` — `numval` expects a column NAME as its first arg, not an expression, so every row is empty). Fix: use `toNumber()` for expression-based conversions.
2. Changing the formula after the output dataset schema is already locked in. `apply-schema` reports "no updates needed" because the output dataset already has the column as `string`. Fix: re-run `dku dataset set-schema OUT -P PROJ -d '[…]'` or delete + recreate the output dataset.

**Reverse pitfall: string-typed expression auto-cast to `bigint` because all sampled values are digit-only.** `replace(strval(col), /^0+/, "")` strips leading zeros and returns a string from GREL's perspective, but if every sample value is digit-only (e.g. `"1234"`, `"123456"`), `apply-schema` infers `bigint` for the output column. Symptom: downstream reads come back as integers (`1234` not `"1234"`), key-exact comparison against an expected-string dataset fails. Fix: either (a) wrap with `concat("", replace(...))` to defeat the digit-only sample, or (b) `dku dataset set-schema OUT -P PROJ -d '[…,{"name":"Trimmed","type":"string"}]'` after `apply-schema` to lock the column as STRING and re-run.

**`numval(int_col)` returns a `double`, not a `bigint` — string concatenation produces `"X.0"`.** GREL has no separate integer accessor; `numval("rank")` on a `bigint` column returns the value as a Java `Double`, so `"Author" + numval("rank")` produces `"Author1.0"`, `"Author2.0"`, etc. — useless as a column-key for downstream Pivot/Group recipes. Fix: strip the trailing `.0` with `replace("Author" + numval("rank"), /\.0$/, "")` (regex form, NOT `replace(s, ".0", "")` — that would also strip a literal `.0` in the middle of a value). For arbitrary numeric → integer-string cast, use the same pattern: `replace(strval_or_numval_expr + "", /\.0$/, "")`. Verified on Challenge_036 (PubMed authors pivot, 264 modalities of `Author{N}` keys). The bareword `concat("Author", rank)` form has the same problem and is generally less reliable.

### Conditionals & logic

```
if(condition, value_if_true, value_if_false)
switch(expr, match1, return1, match2, return2, ..., default)
and(a, b)                        // logical AND (also: a && b)
or(a, b)                         // logical OR (also: a || b)
not(b)                           // logical NOT
with(expr, varname, body)        // bind expr to variable, evaluate body
```

### Null & error handling

```
coalesce(val1, val2, ...)        // first non-null
isBlank(x)                       // null or empty string
isNull(x)                        // null or empty (treats whitespace as null)
isNonBlank(x)                    // opposite of isBlank
isNotNull(x)                     // opposite of isNull
isError(expr)                    // true if expr throws (e.g., division by zero)
```

> **GREL null testing trap.** `col == null` does NOT detect missing values reliably — the comparison silently evaluates to a falsy non-true result, so `if(col == null, fallback, col)` unconditionally takes the *else* branch and propagates the null/empty value downstream (`null * 1.07 → null`, then arithmetic collapses to 0). Always use `isBlank(col)` (or `isNull(col)` if whitespace must NOT count as missing). Worked example:
>
> ```
> // WRONG — silently returns the original null and downstream FCF goes to 0
> if(prev_nwc == null, 8980, prev_nwc)
>
> // RIGHT
> if(isBlank(prev_nwc), 8980, prev_nwc)
> ```

### String operations

```
concat(a, b, ...)                // join strings (also: a + b)
contains(s, fragment)            // substring check
startsWith(s, prefix)
endsWith(s, suffix)
replace(s, "substring", replacement) // literal substring replacement
replace(s, /pattern/, replacement)    // regex replacement (pattern must be /.../-delimited literal)
replaceChars(s, from, to)        // per-character replacement
split(s, separator)              // returns array
join(array, separator)           // array to string
trim(s), strip(s)                // whitespace removal (aliases)
toLowercase(s)                   // NOT lower(s)
toUppercase(s)                   // NOT upper(s)
toTitlecase(s)                   // NOT toTitleCase(s) — lowercase 'c'!
substring(s, from, to)           // extract portion (0-based, 'to' is exclusive — NOT length)
length(s)                        // character count
indexOf(s, sub)                  // first occurrence, 0-based, -1 if not found
lastIndexOf(s, sub)              // last occurrence
chomp(s, tail)                   // remove tail from end if present
match(s, regex)                  // returns array of capture groups
char(code)                       // unicode code → character
ord(s)                           // character → unicode code
```

### Number formatting & conversion

```
toString(n)                      // number to string — NOT str()
toString(n, '0.00')              // formatted: Java DecimalFormat patterns
format('%05d', n)                // Java String.format syntax
toNumber(s)                      // string to number — NOT int() or float()
```

### Numeric operations

```
round(n)                         // nearest integer — 1 ARG ONLY, round(n, 2) does NOT work
ceil(n), floor(n)                // ceiling / floor
abs(n), sqrt(n), pow(a, b)
mod(a, b), quotient(a, b)       // modulo / integer division
min(a, b, ...), max(a, b, ...)  // works on numbers, strings, and dates
sum(a, b, ...), avg(a, b, ...)  // varargs — NOT sum(column)
ln(n)                            // natural log (base e)
log(n)                           // base-10 log (NOT natural log!)
exp(n)                           // e^n
even(n), odd(n)                  // round up to nearest even/odd integer
rand()                           // random double [0,1) or long
PI()                             // π constant
```

**No trigonometric functions.** GREL has no `sin`, `cos`, `tan`, `asin`, `atan2`, or `radians`. Haversine / great-circle distance therefore cannot be expressed in a Prepare formula. Three options when an Alteryx `Distance` or `FindNearest` migration needs trig:
1. **Visual path:** `add-geopoint` (Prepare) on both inputs → `create-geojoin` recipe with `WITHIN_DISTANCE` → **`add-geodistance --from pt1 --to pt2 --output-column dist --unit MILES`** in a downstream Prepare. **Avoid the GREL `geoDistance(pt1, pt2, "MILES")` function for any trip-distance/accumulation pattern** — GREL `geoDistance` rounds its output to 2 decimal places (silent precision loss) AND uses a different spheroid model than the `add-geodistance` Prepare processor. The Prepare processor returns full-precision doubles. Verified on Challenge_032 (5-point route): GREL gave per-leg `36.45, 3.55, 12.67, 29.02` (sum 81.69, +0.06% vs Alteryx); Prepare gave `36.375807100548414, 3.5480203538343713, 12.643350855533372, 28.94970912502732` (sum 81.52, -0.15% vs Alteryx). For a single ad-hoc per-row distance with 2-decimal precision tolerance, GREL is fine.
2. **SQL path:** when the data is (or can be synced to) a SQL connection, write the haversine inline in a `sql_query` recipe (`radians`, `sin`, `cos`, `asin` are standard in PostgreSQL, DuckDB, Snowflake).
3. **Python path:** last resort; only when the spatial calculation is impossible to express via the visual or SQL paths.

### Date operations

```
now()                                    // current datetime
datePart(date, "years"|"months"|...)     // extract component
diff(date1, date2, "days"|"hours"|...)   // difference — NOT dateDiff()
inc(date, value, "days"|"months"|...)    // add/subtract
trunc(date, "days"|"months"|...)         // truncate
asDateOnly(string, format)               // parse date only
asDatetimeNoTz(string, format)           // parse without timezone
asDatetimeTz(string, format)             // parse with timezone
```

Date part values: `years`, `months`, `days`, `weeks`, `hours`, `minutes`, `seconds`, `dayOfWeek`, `weekDay`, `weekOfYear`.

### Array operations

```
forEach(array, v, expression)            // transform each element
filter(array, v, test)                   // keep elements where test is true
forEachIndex(array, i, v, expression)    // with index
forRange(from, to, step, v, expression)  // iterate range
arrayLen(a), arrayContains(a, item)
arraySort(a), arrayReverse(a), arrayDedup(a)
arrayIndexOf(a, item)                    // find index, -1 if not found
get(array, index)                        // access by index
split(s, sep)                            // string to array
join(a, sep)                             // array to string
```

### Type checking & conversion

```
toNumber(x), toString(x), asBool(x)
isNumeric(x)                             // can it be a number?
type(x)                                  // returns type name string
```

### Regex

Regex patterns are `/.../`-delimited literals — NOT strings. `replace(s, "abc", "x")` treats `"abc"` as a literal substring; `replace(s, /a.c/, "x")` treats it as a regex.

```
match(s, /pattern/)                      // returns array of capture groups (pattern is regex literal)
replace(s, /pattern/, replacement)       // regex replace
```

**`match()` requires the regex to match the WHOLE string** — Java `Matcher.matches()` semantics, NOT `find()` / `re.search()`. Agents trained on Python/JavaScript regex reach for `match(s, /(\d{3}-\d{3}-\d{4})/)` to find a phone embedded in `"P.O. Box ... 334-288-3900"`, get null, and silently produce empty extractions.

To extract a pattern from anywhere in the string, anchor with prefix/suffix consumption:

```
// WRONG — returns null because regex doesn't span the whole string
match("P.O. Box ... 334-288-3900", /(\d{3}-\d{3}-\d{4})/)

// RIGHT — non-greedy prefix consumes "P.O. Box ... " before the capture
match("P.O. Box ... 334-288-3900", /.*?(\d{3}-\d{3}-\d{4}).*/)
// → ["334-288-3900"]
```

`replace(s, /pat/, ...)` does NOT have this restriction — it substitutes every match. Only `match()` requires whole-string coverage.

### JSON & object operations

```
parseJson(s)                             // string → object/array
jsonize(val)                             // value → JSON string
objectNew(k1, v1, k2, v2, ...)          // create object
objectKeys(o), objectValues(o)           // list keys/values
objectPut(o, key, value)                 // add key-value pair
objectDel(o, key)                        // remove key
hasField(o, name)                        // check if key exists
get(o, fieldname)                        // access field value
getPath(o, "a.b.c")                      // deep access via JsonPath
```

### Hash & crypto

```
md5(s), sha1(s), sha256(s), sha512(s)   // cryptographic hashes
hash(s)                                  // 64-bit non-crypto hash
hex2dec(s), dec2hex(n)                   // hex conversion
uuid()                                   // random UUID string
```

### Geo functions

```
geoDistance(pt1, pt2, "KILOMETERS"|"MILES")  // distance — ROUNDED TO 2 DECIMALS
geoContains(outer, inner)                // containment test
geoBuffer(geometry, distance)            // buffer zone
geoEnvelope(geometry)                    // bounding box
geoSimplify(geometry, tolerance)         // reduce coordinates
geoMakeValid(geometry)                   // fix invalid polygons
```

### HTML parsing

```
parseHtml(s)                             // string → HTML element
htmlText(e)                              // all text content
ownText(e)                               // direct text only (no children)
innerHtml(e)                             // inner HTML string
htmlAttr(e, "href")                      // attribute value
```

**Broken:** `select(element, selector)` causes `StackOverflowError` in apply-schema. Use `htmlText()` directly instead.

**Does NOT exist:** `ngram()` — listed in some docs but returns `Unknown function` on DSS.

## Common gotchas

1. **Case sensitivity kills:** `toTitlecase` works, `toTitleCase` fails. Always use exact names from this reference.
2. **`round()` takes 1 arg only:** `round(n, 2)` silently produces empty. For 2 decimals: `round(n * 100) / 100`. Or use `RoundProcessor`.
3. **`log()` is base-10, not natural:** Use `ln()` for natural log. `exp()` IS base-e. (Inconsistent.)
4. **`substring(s, from, to)` — `to` is exclusive index, NOT length:** `substring("hello", 1, 3)` → `"el"`. Unlike SAS `SUBSTR(s, start, length)`.
5. **`diff()` not `dateDiff()`:** The date difference function is `diff(d1, d2, unit)`.
6. **`count()` doesn't exist in Prepare formulas:** Only works in Group recipe aggregation. Use `arrayLen()` for arrays.
7. **Leading zeros disappear:** Wrap in `strval(column)` to preserve.
8. **isNull vs isBlank:** `isNull` treats whitespace-only as null; `isBlank` does not.
9. **String concat with nulls:** Use `strval(column, "")` to avoid null propagation.
10. **Date parsing:** Always specify format when input isn't ISO-8601.
11. **forEach returns array:** Use `join()` if you need a string result.

## Examples

**User:** "Combine first and last name with a space"
**Formula:** `concat(first_name, " ", last_name)`

**User:** "If status is 'active', return 1, otherwise 0"
**Formula:** `if(status == "active", 1, 0)`

**User:** "Map category codes to labels"
**Formula:** `switch(category, "A", "Premium", "B", "Standard", "C", "Basic", "Unknown")`

**User:** "Extract the year from a date column"
**Formula:** `datePart(date_column, "years")`

**User:** "Replace all commas with semicolons"
**Formula:** `replace(text_column, ",", ";")`

**User:** "Get the first 3 characters of a string"
**Formula:** `substring(text_column, 0, 3)`

**User:** "Sum of price times quantity"
**Formula:** `price * quantity`

**User:** "Default to 'Unknown' if the field is empty"
**Formula:** `coalesce(field, "Unknown")` or `if(isBlank(field), "Unknown", field)`

**User:** "Title case a city name"
**Formula:** `toTitlecase(city)` — note lowercase 'c'

**User:** "Round to 2 decimal places"
**Formula:** `round(value * 100) / 100` — NOT `round(value, 2)`

**User:** "Calculate days between two dates"
**Formula:** `diff(start_date, end_date, "days")` — NOT `dateDiff()`

**User:** "Format a number with leading zeros"
**Formula:** `format('%05d', id)` — Java String.format syntax

**User:** "Handle division by zero gracefully"
**Formula:** `if(isError(a / b), 0, a / b)` or `if(b == 0, 0, a / b)`

---

## Critical gotcha

### GREL formula quirks
`log()` is base-10, `ln()` is natural log (despite `exp()` being base-e). `numval()` / `strval()` / `val()` require QUOTED column names — `numval("col")` works, bareword `numval(col)` silently returns empty. `replace(s, "pat", ...)` is literal substring; regex needs `/pat/` delimiters. Formula columns default to STRING — always run `apply-schema` after adding formula steps.
