# Dataiku Formula Language

Expression syntax used in Prepare recipes, computed columns, and formula-based processors.

## What can be done

- **Generate formulas** from natural language descriptions
- **Debug/fix** broken or erroring formulas
- **Explain** what a formula does
- **Translate** between Formula Language and Python (both directions)

## Output format

Return formulas as plain text—no markdown code fences, no extra explanation unless asked. Just the formula.

## Core syntax reference

### Column access
- `column_name` — returns the cell value directly
- `numval(column)` — forces numeric interpretation
- `strval(column)` — forces string interpretation (returns "" for empty)
- `strval(column, default)` — string value with fallback
- `val(column, [default], [offset])` — generic accessor with optional default and row offset

### Key patterns

**Conditionals:**
```
if(condition, value_if_true, value_if_false)
```

**Null handling:**
```
coalesce(val1, val2, ...)        // first non-null
isBlank(x)                       // null or empty string
isNull(x)                        // null or empty (treats whitespace as null)
isNonBlank(x)                    // opposite of isBlank
```

**String operations:**
```
concat(a, b, ...)                // join strings
contains(s, fragment)            // substring check
startsWith(s, prefix)
endsWith(s, suffix)
replace(s, pattern, replacement) // supports regex
split(s, separator)              // returns array
join(array, separator)           // array to string
trim(s), strip(s)                // whitespace removal
toLowercase(s), toUppercase(s), toTitlecase(s)
substring(s, from, to)           // extract portion
length(s)                        // character count
```

**Numeric operations:**
```
round(n), ceil(n), floor(n)
abs(n), sqrt(n), pow(a, b)
mod(a, b), quotient(a, b)
min(a, b, ...), max(a, b, ...)
sum(column), avg(column), count(column)
```

**Date operations:**
```
now()                                    // current datetime
datePart(date, "years"|"months"|...)     // extract component
diff(date1, date2, "days"|"hours"|...)   // difference
inc(date, value, "days"|"months"|...)    // add/subtract
trunc(date, "days"|"months"|...)         // truncate
asDatetimeTz(string, format)             // parse with timezone
asDateOnly(string, format)               // parse date only
```

**Array operations:**
```
forEach(array, v, expression)            // transform each element
filter(array, v, test)                   // keep elements where test is true
forEachIndex(array, i, v, expression)    // with index
arrayLen(a), arrayContains(a, item)
arraySort(a), arrayReverse(a), arrayDedup(a)
split(s, sep)                            // string to array
join(a, sep)                             // array to string
```

**Type conversion:**
```
toNumber(x), toString(x), asBool(x)
isNumeric(x)                             // can it be a number?
type(x)                                  // returns type name
```

**Regex:**
```
match(s, pattern)                        // returns array of groups
replace(s, /pattern/, replacement)       // regex replace
```

## Common gotchas

1. **Leading zeros disappear**: Wrap in `strval(column)` to preserve
2. **isNull vs isBlank**: `isNull` treats whitespace-only as null; `isBlank` does not
3. **String concat with nulls**: Use `strval(column, "")` to avoid null propagation
4. **Date parsing**: Always specify format when input isn't ISO-8601
5. **forEach returns array**: Use `join()` if you need a string result

## Examples

**User:** "Combine first and last name with a space"
**Formula:** `concat(first_name, " ", last_name)`

**User:** "If status is 'active', return 1, otherwise 0"
**Formula:** `if(status == "active", 1, 0)`

**User:** "Extract the year from a date column"
**Formula:** `datePart(date_column, "years")`

**User:** "Replace all commas with semicolons"
**Formula:** `replace(text_column, ",", ";")`

**User:** "Get the first 3 characters of a string"
**Formula:** `substring(text_column, 0, 3)`

**User:** "Sum of price times quantity"
**Formula:** `price * quantity` (for row-level) or `sum(price * quantity)` (for aggregation)

**User:** "Default to 'Unknown' if the field is empty"
**Formula:** `coalesce(field, "Unknown")` or `if(isBlank(field), "Unknown", field)`
