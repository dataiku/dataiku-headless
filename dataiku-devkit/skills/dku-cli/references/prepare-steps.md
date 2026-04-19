# Prepare Recipe Guide

Step management, processor examples, and complete prepare workflows. For the full processor decision table, see the `dataiku` skill's `references/prepare-processors.md`.

## Step Management Commands

| Command | Purpose |
|---------|---------|
| `list-steps RECIPE -P PROJ` | Show all steps (index, type, disabled, target) |
| `add-step RECIPE --type TYPE --params JSON -P PROJ` | Add any processor from the catalog (append) |
| `add-step RECIPE --type TYPE --params JSON --at N -P PROJ` | Insert step at index N (0-based) |
| `get-step RECIPE --index N -P PROJ` | Get full step JSON |
| `remove-step RECIPE --index N -P PROJ` | Remove step(s) by index |
| `disable-step RECIPE --index N -P PROJ` | Skip step during execution |
| `enable-step RECIPE --index N -P PROJ` | Re-enable a disabled step |

## Processor Selection: Deep Table

Before reaching for `add-formula` (GREL), check if a purpose-built processor exists:

| Need to... | Use this instead of GREL |
|------------|--------------------------|
| Rename columns | `add-rename` (not GREL concat workarounds) |
| Uppercase/lowercase | `add-step --type StringTransformer` (not GREL `toUppercase()`) |
| Concatenate columns | `add-step --type ColumnsConcat` (not GREL `col1 + " " + col2`) |
| If/then/else logic | `add-step --type VisualIfRule` (not GREL `if()` chains) |
| Parse dates | `add-step --type DateParser` (not GREL `toDate()`) |
| Extract year/month/day | `add-step --type DateComponentsExtractor` (not GREL `year()`) |
| Date differences | `add-step --type DateDifference` (not GREL `dateDiff()`) |
| Fill empty values | `add-fill-empty` (not GREL `if(isBlank())`) |
| Bin numbers | `add-step --type BinnerProcessor` (not GREL `if` chains) |
| Split column | `add-step --type ColumnSplitter` (not GREL `split()`) |
| Flatten JSON | `add-step --type JSONFlattener` (not Python json.loads) |
| Remove empty rows | `add-step --type RemoveRowsOnEmpty` (not GREL filter) |
| Filter invalid types | `add-step --type FilterOnBadType` (not GREL type checks) |

## add-step JSON Examples

**Before writing any `add-step` command, READ the `dataiku` skill's `references/prepare-processors.md`** to get the exact params and canonical JSON for the processor you need. Each processor has required fields that vary — guessing params will fail silently or produce broken steps.

### DateParser — Parse date strings to ISO 8601

```bash
dku recipe add-step prep --type DateParser \
  --params '{"appliesTo":"SINGLE_COLUMN","columns":["order_date"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outType":{"name":"out","type":"date"}}' -P PROJ
```

### DateComponentsExtractor — Extract year and month

```bash
dku recipe add-step prep --type DateComponentsExtractor \
  --params '{"column":"order_date","timezone_id":"UTC","outYearColumn":"order_year","outMonthColumn":"order_month"}' -P PROJ
```

### StringTransformer — Uppercase a text column

```bash
dku recipe add-step prep --type StringTransformer \
  --params '{"mode":"TO_UPPER","appliesTo":"SINGLE_COLUMN","columns":["city"]}' -P PROJ
```

> **Mode names:** use `TO_UPPER`, `TO_LOWER`, `TRIM`, `NORMALIZE`, `TRUNCATE`. `UPPERCASE`/`LOWERCASE`/`TITLECASE` are **not valid** — they produce a runtime NullPointerException on build. For title case, there is no built-in mode — use GREL `add-formula --expr "toTitlecase(city)" --column city_title -P PROJ` instead.

### ColumnsConcat — Concatenate first + last name

```bash
dku recipe add-step prep --type ColumnsConcat \
  --params '{"columns":["first_name","last_name"],"join":" ","outputColumn":"full_name"}' -P PROJ
```

### JSONFlattener — Flatten a JSON metadata column

```bash
dku recipe add-step prep --type JSONFlattener \
  --params '{"inCol":"metadata","flattenArrays":false,"maxDepth":10,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}' -P PROJ
```

### FilterOnBadType — Remove rows with non-numeric values

```bash
dku recipe add-step prep --type FilterOnBadType \
  --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"DoubleMeaning","action":"REMOVE_ROW","considerEmptyAsInvalid":false,"booleanMode":"AND"}' -P PROJ
```

### RemoveRowsOnEmpty — Remove all empty rows

```bash
dku recipe add-step prep --type RemoveRowsOnEmpty \
  --params '{"appliesTo":"ALL","columns":[],"keep":false}' -P PROJ
```

## Complete Prepare Workflow (chaining multiple processors)

```bash
# Pre-create output (required for prepare — unlike create-join/create-group, prepare does NOT auto-create).
# Distinct names for dataset vs recipe keeps the flow graph readable; using the same name works but hides the recipe behind its output.
dku dataset create clean_orders --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create prep_clean --type prepare -i raw_data --output-ds clean_orders -P PROJ && \
dku recipe add-rename prep_clean --from "CustomerName" --to "customer_name" -P PROJ && \
dku recipe add-rename prep_clean --from "OrderDate" --to "order_date" -P PROJ && \
dku recipe add-step prep_clean --type RemoveRowsOnEmpty --params '{"appliesTo":"ALL","columns":[],"keep":false}' -P PROJ && \
dku recipe add-step prep_clean --type StringTransformer --params '{"mode":"TO_LOWER","appliesTo":"SINGLE_COLUMN","columns":["customer_name"]}' -P PROJ && \
dku recipe add-fill-empty prep_clean --column price --value "0" -P PROJ && \
dku recipe add-step prep_clean --type FilterOnBadType --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"DoubleMeaning","action":"REMOVE_ROW","considerEmptyAsInvalid":false,"booleanMode":"AND"}' -P PROJ && \
dku recipe add-delete-columns prep_clean --columns "debug_col,temp_id" -P PROJ && \
dku job run --target clean_orders --auto-update-schema --wait -P PROJ
```
