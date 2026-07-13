---
name: prepare-shared-formula-language
description: "Conceptual reference for Dataiku's formula language (GREL), for reading or describing formulas used by formula-based prepare/shaker processors."
---

# Shared Formula Language

Use this reference to understand the Dataiku formula language (GREL) as it appears in formula-based prepare processors (for example `CreateColumnWithGREL`, `FlagOnCustomFormula` / docs label "Flag rows with formula", `FilterOnCustomFormula` / docs label "Filter rows/cells with formula", `FormulaToNumber`, `FormulaToString`, `FormulaToDate`, and related formula operators). It supports two uses: reading an existing formula from `get_recipe_settings` output and accurately explaining what it does, and describing a desired formula precisely in a Cobuild prompt. It does not document direct recipe mutation mechanics.

## Typing Notation

- `string<formula_expression>`: any valid Dataiku formula expression.
- `string<column_name>`: any valid column name from schema.
- `""`: explicit empty string.

## Expression Mechanics

| Topic | Guidance |
| --- | --- |
| Column references | Use a simple column name directly — it starts with a letter and contains only letters, numbers, and underscores (e.g. `applicant_age + 1`). For names with spaces or special characters, to control how a value is read, or to apply a row offset, use `val`, `strval`, or `numval` with the name double-quoted, e.g. `val("applicant age")`. See **Value Access Functions** for read semantics. |
| Function calls | Use `function(arg1, arg2, ...)` syntax. |
| Row offsets | `val`, `strval`, and `numval` support row offsets (for example `numval("event_count", 1)` for previous row). Offset arguments are only available in Prepare recipes with the Dataiku engine. |
| Null/blank handling | Guard with checks like `isBlank(...)` before expensive parsing or casting chains. |

## Valid Functions — Complete Reference

**Only use functions listed here.** Never invent or guess a function name. If a needed function is not listed, tell the user rather than trying an unlisted name.

### String Functions

- `char(number value)` → string — `char(65)` = "A"
- `chomp(string s, string tail)` → string — `chomp("foobar", "bar")` = "foo"
- `coalesce(value1, value2, …)` → varies — returns first non-empty value; `coalesce("", "foo")` = "foo"
- `concat(a1, [a2, …])` → string — `concat("Birds", " ", "fly")` = "Birds fly"
- `contains(string s, string frag)` → boolean — `contains("hello world", "llo")` = true
- `endsWith(string s, string tail)` → boolean — `endsWith("hello world", "rld")` = true
- `escape(string s, string mode)` → string — modes: `'html'`, `'xml'`, `'csv'`, `'url'`, `'javascript'`
- `format(string format, object… args)` → string — `format('%4d-%02d', 2004, 2)` = "2004-02"
- `fromBase64(string s, [string charset])` → string — `fromBase64('SA==')` = "H"
- `get(string s, from, [to])` → string — `get('Oh no, kittens!', 0, 5)` = "Oh no"
- `indexOf(string s, string sub)` → number — `indexOf("hello world", "world")` = 6
- `lastIndexOf(string s, string sub)` → number — `lastIndexOf("hello world", "o")` = 7
- `length(string or array o)` → number — `length("hello world")` = 11
- `match(string s, string or regex)` → array — returns capture groups; `match('hello world', 'he(.*)wo(rl)d')` = ["llo ", "rl"]
- `md5(string s)` → string
- `ord(string s)` → number — `ord('A')` = 65
- `partition(string s, string or regex frag, [boolean omitFragment])` → array
- `replace(string s, string or regex f, string replacement)` → string — `replace('hello world', 'hel', 'a')` = "alo world"
- `replaceChars(string s, string f, string r)` → string — `replaceChars('abcba', 'bc', 'BC')` = "aBCBa"
- `rpartition(string s, string or regex frag, [boolean omitFragment])` → array
- `sha1(string s)` → string
- `sha256(string s)` → string
- `sha512(string s)` → string
- `split(string s, string or regex sep, [boolean preserveAllTokens])` → array
- `splitByCharType(string s)` → array — `splitByCharType("Hello_world 101!?!")` = ["H","ello","_","world"," ","101","!?!"]
- `splitByLengths(string s, number length1, […])` → array
- `startsWith(string s, string sub)` → boolean — `startsWith("Hello world", "He")` = true
- `strip(string s)` → string — removes leading/trailing whitespace; `strip(" Hello World ")` = "Hello World"
- `toBase64(string s, [string charset])` → string
- `toLowercase(string s)` → string — `toLowercase("HELLO")` = "hello"
- `toString(o, [string format])` → string — `toString(5)` = "5"
- `toTitlecase(string s)` → string — `toTitlecase("hello world")` = "Hello World"
- `toUppercase(string s)` → string — `toUppercase("hello")` = "HELLO"
- `trim(string s)` → string — `trim(" Hello World ")` = "Hello World"
- `unescape(string s, string mode)` → string
- `unicode(string s)` → string — `unicode("Hi!")` = [72,105,33]
- `unicodeType(string s)` → string
- `uuid()` → string — generates type-4 UUID

### Math / Numeric Functions

- `abs(number d)` → number — `abs(-7)` = 7.0
- `acos(number d)` → number
- `asin(number d)` → number
- `atan(number d)` → number
- `atan2(number x, number y)` → number
- `avg(number n1, n2, …)` → number — `avg(1, "2", 3, "")` = 2.0
- `ceil(number n)` → number — `ceil(4.67)` = 5
- `combin(number n, number k)` → number — `combin(6, 2)` = 15
- `cos(number d)` → number — `cos(0)` = 1.0
- `cosh(number d)` → number
- `dec2hex(long)` → string — `dec2hex(10)` = "a"
- `degrees(number d)` → number — `degrees(PI())` = 180.0
- `even(number n)` → number — rounds up to nearest even; `even(3)` = 4.0
- `exp(number n)` → number — `exp(2)` = 7.389…
- `fact(number i)` → number — `fact(4)` = 24
- `factn(number i, number d)` → number
- `floor(number d)` → number — `floor(4.7)` = 4
- `gcd(number d, number e)` → number — `gcd(21, 28)` = 7.0
- `hash(string)` → long — 64-bit numerical hash
- `hex2dec(string)` → long — `hex2dec("a")` = 10
- `lcm(number d, number e)` → number — `lcm(20, 42)` = 420.0
- `ln(number n)` → number — natural log; `ln(exp(1))` = 1.0
- `log(number n)` → number — base-10 log; `log(100)` = 2.0
- `max(a, b, …)` → varies — `max(-1, 3)` = 3
- `min(a, b, …)` → varies — `min(-1, 3)` = -1.0
- `mod(number a, number b)` → number — `mod(5, 3)` = 2
- `multinomial(number d1, d2, …)` → number
- `odd(number d)` → number — rounds up to nearest odd; `odd(5.3)` = 7.0
- `PI()` → number — π constant
- `pow(number a, number b)` → number — `pow(2, -1)` = 0.5
- `quotient(numerator, denominator)` → number — integer division; `quotient(7, 2)` = 3.0
- `radians(number d)` → number — `radians(180)` = 3.14159…
- `rand([long min], [long max])` → number — 0–1 float, or integer in [min, max)
- `round(number n)` → number — `round(3.5)` = 4.0
- `sin(number d)` → number
- `sinh(number d)` → number
- `sqrt(number n)` → number — `sqrt(81)` = 9.0
- `sum(array a)` → number — `sum([1, 2, "string", 3])` = 6.0
- `tan(number d)` → number
- `tanh(number d)` → number
- `toNumber(o)` → number — **only numeric conversion function**; `toNumber("5")` = 5

### Date / Time Functions

- `asDatetimeTz(o, [format1, …])` → datetime with timezone
- `asDatetimeNoTz(o, [format1, …])` → datetime without timezone
- `asDateOnly(o, [format1, …])` → date only
- `datePart(date d, string part, [timezone])` → varies — parts: `'years'`, `'months'`, `'days'`, `'weekday'`, `'hours'`, `'minutes'`, `'seconds'`
- `diff(date d1, date d2, [string unit])` → number — `diff('2019-03-15T00:00:00.000Z', '2020-04-15T00:00:00.000Z', 'month')` = -13
- `inc(date d, number value, string unit)` → date — `inc('2020-04-15T00:00:00.000Z', -3, 'week')` = 2020-03-25T00:00:00.000Z
- `now()` → datetime with timezone
- `trunc(date d, string unit)` → date — `trunc('2020-04-03T07:47:45.245Z', 'month')` = 2020-04-01T00:00:00.000Z

### Boolean / Logic Functions

- `and(boolean a, boolean b)` → boolean
- `asBool(o)` → boolean
- `isFalse(boolean b)` → boolean
- `isTrue(boolean b)` → boolean
- `not(boolean b)` → boolean
- `or(boolean a, boolean b)` → boolean

### Null / Type Test Functions

- `isBlank(o)` → boolean — true if null or empty string
- `isError(o)` → boolean
- `isNonBlank(o)` → boolean — true if not null/empty (whitespace-only counts as non-blank)
- `isNotNull(o)` → boolean — true if not null (ignores empty strings)
- `isNull(o)` → boolean — true if null or empty
- `isNumeric(o)` → boolean — true if value can represent a number
- `type(o)` → string — `type(3.126)` = "number"

### Array Functions

- `arrayContains(array a, item)` → boolean
- `arrayDedup(array a)` → array
- `arrayIndexOf(array a, item)` → int
- `arrayLen(array a)` → int
- `arrayReverse(array a)` → array
- `arraySort(array a)` → array
- `get(array a, from, [to])` → varies — `get([1,2,3], 0)` = 1
- `join(array a, string sep)` → string — `join([2007, 7, 15], '-')` = "2007-7-15"
- `objectKeys(object o)` → array
- `objectValues(object o)` → array
- `slice(o, from, [to])` → varies
- `substring(o, from, [to])` → varies

### Object / JSON Functions

- `get(object o, string field, [string defaultValue])` → varies
- `hasField(object o, string name)` → boolean
- `htmlAttr(Element e, string s)` → string
- `htmlText(Element e)` → string
- `innerHtml(Element e)` → string
- `jsonize(value)` → JSON literal string
- `objectDel(object o, key, [key…])` → object
- `objectNew(k1, v1, k2, v2, …)` → object — `objectNew("firstName", "birdie", "company", "Dataiku")`
- `objectPut(object o, key, value)` → object
- `ownText(Element e)` → string
- `parseHtml(string s)` → HTML object
- `parseJson(string s)` → object or array
- `select(Element e, string s)` → HTML elements

### Value Access Functions
Use a simple column name directly (`col_1 + 4`). Reach for these when the name has spaces or special characters, when you want to fix how the value is read, or when you need a row offset:
- `val(o, [string defaultValue], [number offset])` → varies — auto-typed read
- `strval(o, [string defaultValue], [number offset])` → string — forces string read (skips numeric auto-typing)
- `numval(o, [number offset])` → number — forces decimal read; offset = rows back (Prepare/Dataiku engine only)

### Control Structures (cannot use object notation)

- `filter(array a, variable v, expression e)` → array — keeps elements where `e` is truthy
- `forEach(array a, variable v, expression e)` → array — maps `e` over elements
- `forEachIndex(array a, variable i, variable v, expression e)` → array — includes index `i`
- `forRange(from, to, step, variable v, expression e)` → array
- `if(boolean, expr_true, expr_false)` → varies — `if(3>2, "yes", "no")` = "yes"
- `objectFilter(expr a, variable k, variable v, expr test)` → object
- `switch(expr_to_match, match_1, return_1, …, [default])` → varies — `switch("Paris", "Paris", 1, "New York", 2, 0)` = 1
- `with(expression o, variable v, expression e)` → varies — binds result of `o` to `v` for reuse in `e`

### Geometry Functions

- `geoBuffer(geometry geom, double distance, [int quadrantSegment])` → string
- `geoContains(geometry geomA, geometry geomB)` → boolean — `geoContains("POLYGON((0 0,3 0,0 3,0 0))", "POINT(1 1)")` = true
- `geoDistance(geopoint a, geopoint b, string unit)` → number — units: `KILOMETERS`, `MILES`
- `geoEnvelope(geometry geom)` → string — minimum bounding box
- `geoMakeValid(geometry geom)` → string
- `geoSimplify(geometry geom, double toleranceDistance)` → string

## Common Patterns

| Intent | Expression | Notes |
| --- | --- | --- |
| Add constant to numeric column | `age + 3` | Works when `age` is numeric. |
| Safe numeric conversion | `numval("event count") * 10` | Good for names with spaces and string-typed numbers. |
| Simple boolean label | `if(age < 35, "true", "false")` | Returns text labels. |
| Conditional text mapping | `if(is_active=="yes","it's active","nope")` | Simple identifiers can be compared directly. |
| Concatenate two columns | `concat(id, full_name)` | For key/label generation. |
| Null/blank fallback | `if(isBlank(email), "unknown", email)` | Avoids null-driven failures downstream without unnecessary wrapping. |
| Two-column fallback chain | `if(isBlank(email), if(isBlank(fake_email), "unknown", fake_email), email)` | Explicit fallback without extra helper functions. |
| Numeric clipping logic | `if(score > 100, 100, score)` | Soft cap example using a direct column reference. |
| Bucketize into ranges | `if(age < 18, "minor", if(age < 65, "adult", "senior"))` | Nested `if` bins values. |
| Parse date with fallback formats | `asDatetimeTz(signup_date_string, "MM/dd/yyyy", "dd-MM-yyyy", "yyyy-MM-dd")` | Tries formats in order. |
| Date increment | `inc(asDateOnly(signup_date), 7, "days")` | Adds/subtracts date units. |
| Date difference | `diff(last_login, signup_date, "days")` | Returns delta in requested unit. |
| Date component extraction | `datePart(last_login, "weekday")` | Extracts weekday/year/etc. |
| Regex group extraction | `get(match(email, ".*@(.*)"), 0)` | Returns first capture group match. |
| Split and pick token | `get(split(full_name, " "), 0)` | Useful for first-name extraction. |
| JSON field access | `get(parseJson(metadata), "country", "unknown")` | Parse object/array from JSON string first. |
| Array membership | `arrayContains(parseJson(tags), "vip")` | For JSON-array-like string columns. |
| Variable-driven threshold | `if(height < variables["max_height"], "OK", variables["warning_msg"])` | Uses Dataiku variables as JSON values. |
| Categorical mapping with default | `switch(country, "US", "North America", "FR", "Europe", "Other")` | Compact multi-branch mapping. |
| Previous-row comparison | `if(numval("event count") > numval("event count", 1), "up", "flat_or_down")` | Uses row offset (`1` = previous row). |
| Reuse intermediate expression | `with(split(full_name, " "), p, concat(get(p, 0), "_", get(p, 1)))` | Improves readability for complex formulas. |

## Authoring and Validation Guidance

1. Keep formula expressions deterministic and side-effect free.
2. Prefer simple, readable formulas that match the requested transformation.

## References

- Dataiku: Formula language reference
  https://doc.dataiku.com/dss/latest/formula/index.html
