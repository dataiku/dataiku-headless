# Prepare Recipe Deep Dive — dataikuapi Audit & CLI Design

## Executive Summary

The Prepare recipe is Dataiku's most powerful visual recipe (~95 processor types), but **the CLI has zero support for managing steps**. Currently `dku recipe create --type prepare` creates an empty prepare recipe, and agents must use `set-definition` with raw JSON to add steps — a huge friction point.

The `dataikuapi` library provides two key classes:
- **`PrepareRecipeSettings`** — `raw_steps` property + `add_processor_step(type, params)` method
- **`PrepareRecipeCreator`** — standard `SingleOutputRecipeCreator` with type `'shaker'`

This audit covers the full API surface, all ~95 processor types, their internal identifiers and param structures, and proposes CLI commands to make agents excellent at prepare recipes.

---

## 1. dataikuapi API Surface

### PrepareRecipeSettings (recipe.py:1681)

```python
class PrepareRecipeSettings(DSSRecipeSettings):
    @property
    def raw_steps(self):
        """Returns MUTABLE reference to steps list. Modify + save() to commit."""
        return self.obj_payload["steps"]

    def add_processor_step(self, type, params):
        """Append a step to the script."""
        step = {
            "metaType": "PROCESSOR",
            "type": type,
            "params": params
        }
        self.raw_steps.append(step)
```

### PrepareRecipeCreator (recipe.py:1727)

```python
class PrepareRecipeCreator(SingleOutputRecipeCreator):
    def __init__(self, name, project):
        SingleOutputRecipeCreator.__init__(self, 'shaker', name, project)
```

### Step JSON Structure

Every step follows this schema:

```json
{
  "metaType": "PROCESSOR",       // or "GROUP" for step groups
  "type": "CreateColumnWithGREL", // internal processor type ID
  "name": "My step label",       // optional display name
  "disabled": false,              // optional, skip this step
  "params": {                     // processor-specific parameters
    "expression": "upper(city)",
    "column": "city_upper"
  }
}
```

For `GROUP` metaType (step folders in UI):
```json
{
  "metaType": "GROUP",
  "name": "Cleaning steps",
  "steps": [
    { "metaType": "PROCESSOR", "type": "...", "params": {...} },
    { "metaType": "PROCESSOR", "type": "...", "params": {...} }
  ]
}
```

### Payload Structure

The prepare recipe payload (accessed via `obj_payload`) is:

```json
{
  "steps": [...],              // the processor steps array
  "maxProcessedMemTableBytes": -1,
  "engineParams": {
    "hive": {...},
    "spark": {...},
    "impala": {...}
  },
  "exploreUIParams": {...},
  "explorationSampling": {...},
  "analysisColumnData": {...}
}
```

### Key API Operations

| Operation | Method | Notes |
|-----------|--------|-------|
| Create prepare recipe | `project.new_recipe('prepare', name)` | Returns `PrepareRecipeCreator` |
| Get settings | `recipe.get_settings()` | Returns `PrepareRecipeSettings` |
| List steps | `settings.raw_steps` | Mutable list reference |
| Add step | `settings.add_processor_step(type, params)` | Appends to end |
| Insert step at position | `settings.raw_steps.insert(index, step_dict)` | Direct list manipulation |
| Remove step | `settings.raw_steps.pop(index)` or `del` | Direct list manipulation |
| Replace step | `settings.raw_steps[index] = new_step` | Direct list manipulation |
| Disable/enable step | `settings.raw_steps[i]["disabled"] = True/False` | Direct dict mutation |
| Reorder steps | Manipulate the list directly | Sort, reverse, etc. |
| Save changes | `settings.save()` | PUT to DSS API |
| Run recipe | `recipe.run()` → `DSSRecipeStatus` | Standard recipe run |
| Compute schema updates | `recipe.get_status()` | Check output schema changes |

### HTTP Endpoints (Internal)

| Operation | HTTP | Endpoint |
|-----------|------|----------|
| Create | POST | `/projects/{key}/recipes/` |
| Get settings | GET | `/projects/{key}/recipes/{name}` |
| Update | PUT | `/projects/{key}/recipes/{name}` |
| Delete | DELETE | `/projects/{key}/recipes/{name}` |
| Schema update | GET | `/projects/{key}/recipes/{name}/schema-update` |
| Status | GET | `/projects/{key}/recipes/{name}/status` |

### Critical Gotcha: Payload Initialization on Create

When creating a new prepare recipe via `PrepareRecipeCreator`, the payload may not contain a `steps` array. The CLI must initialize it before adding steps:

```python
settings = recipe.get_settings()
payload = settings.obj_payload
if payload is None or "steps" not in payload:
    # Initialize empty steps array
    if payload is None:
        payload = {"steps": []}
    else:
        payload["steps"] = []
    settings._obj_payload = payload
settings.add_processor_step("ColumnRenamer", {"renamings": [...]})
settings.save()
```

This means the `add-step` command must defensively ensure `steps` exists before appending.

### Step Builder Classes (analysis.py — also work for prepare recipes)

The `dataikuapi` also provides builder classes in `analysis.py` that construct step dicts:

| Builder Class | Processor Type | Key Methods |
|---------------|---------------|-------------|
| `DSSFormulaStepBuilder` | `CreateColumnWithGREL` | `with_output_column()`, `with_expression()`, `with_error_column()` |
| `FilterOnValueStepBuilder` | `FlagOnValue` | `with_values()`, `with_matching_mode()`, `with_normalization_mode()` |
| `FilterOnBadTypeStepBuilder` | `FilterOnBadType` | `with_meaning()` |
| `RemoveRowsStepBuilder` | `RemoveRowsOnEmpty` | `with_meaning()` (keep=True/False) |
| `AppliesToStepBuilder` | (base class) | `with_single_column_selection()`, `with_multiple_column_selection()`, `with_regex_column_selection()`, `with_all_column_selection()` |
| `FilterAndFlagStepBuilder` | (base class) | `with_action()` (KEEP_ROW/REMOVE_ROW/CLEAR_CELL/FLAG), `with_boolean_mode()`, `with_flag_column()` |

These can be used with `PrepareRecipeSettings` by calling `.build()` and appending to `raw_steps`.

### Common Parameter Patterns

Many processors share these parameter patterns:

**Column selection (`appliesTo`):**
```json
{
  "appliesTo": "SINGLE_COLUMN",   // or "COLUMNS", "PATTERN", "ALL"
  "columns": ["col1"],             // for SINGLE_COLUMN or COLUMNS
  "appliesToPattern": "^prefix_",  // for PATTERN mode
}
```

**Filter/Flag actions:**
```json
{
  "action": "REMOVE_ROW",  // or "KEEP_ROW", "CLEAR_CELL", "DONTCLEAR_CELL", "FLAG"
  "booleanMode": "AND",    // or "OR" — how to combine multi-column matches
  "flagColumn": "is_valid"  // only when action=FLAG
}
```

---

## 2. Complete Processor Type Catalog

### Mapping: Doc URL → Internal Type ID

Based on analysis of the doc URLs, .shaker files, community examples, and dataikuapi source, here is the catalog of all ~95 processors organized by category. Internal type IDs marked with ✅ are confirmed from source code/examples; those marked with 🔍 are inferred from naming patterns.

#### Column Operations

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Copy column | `ColumnCopier` | `inputColumn`, `outputColumn` | ✅ |
| Rename columns | `ColumnRenamer` | `renamings: [{from, to}]` | ✅ |
| Concatenate columns | `ColumnConcatenator` | `columns`, `outputColumn`, `separator` | 🔍 |
| Delete/keep columns | `ColumnsSelector` | `columns`, `keep: true/false`, `appliesTo` | ✅ |
| Move columns | `ColumnReorder` | `columns`, `referenceColumn`, `reorderAction`, `appliesTo` | ✅ |
| Column pseudonymization | `ColumnPseudonymization` | `column`, `algorithm` | 🔍 |
| Fill column | `FillColumn` | `column`, `value` | 🔍 |
| Fill empty with value | `FillEmptyWithValue` | `column`, `value` | ✅ |
| Fill empty with computed | `FillEmptyWithComputedValue` | `column`, `mode` | 🔍 |
| Fill empty with prev/next | `UpDownFiller` | `column`, `direction` | 🔍 |

#### Formula & Logic

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Formula (GREL) | `CreateColumnWithGREL` | `expression`, `column` (output col name) | ✅ |
| If/Then/Else | `IfThenElse` | `conditions: [{expression, output}]`, `elseOutput` | 🔍 |
| Switch/Case | `SwitchCase` | `column`, `cases: [{value, output}]`, `default` | 🔍 |
| Negate boolean | `NegateBoolean` | `column` | 🔍 |
| Python function | `PythonUDF` | `mode`, `pythonSourceCode`, `column`, `stopOnError` | ✅ |

#### String/Text

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Transform string | `StringTransformer` | `mode` (UPPERCASE, LOWERCASE, TRUNCATE...), `columns`, `appliesTo` | ✅ |
| Simplify text | `TextSimplifier` | `column`, `normalize`, `stem`, `clearStopWords` | 🔍 |
| Tokenize text | `Tokenizer` | `column`, `outputColumn`, `operation` | 🔍 |
| Extract ngrams | `NgramExtractor` | `column`, `ngramLength` | 🔍 |
| Extract numbers | `NumberExtractor` | `column`, `outputColumn` | 🔍 |
| Find and replace | `FindReplace` | `output`, `mapping: [{from, to}]`, `columns`, `appliesTo`, `matching`, `normalization` | ✅ |
| Extract with regex | `RegexpExtractor` | `column`, `pattern`, `extractAllOccurrences` | 🔍 |
| Extract with grok | `GrokExtractor` | `column`, `pattern` | 🔍 |
| Count occurrences | `CountOccurrences` | `column`, `value`, `outputColumn` | 🔍 |

#### Filtering & Flagging

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Filter on value | `FilterOnValue` / `FlagOnValue` | `values`, `action`, `matchingMode`, `normalizationMode`, `appliesTo`, `columns` | ✅ |
| Filter on formula | `FilterOnFormula` | `expression`, `action` | 🔍 |
| Filter invalid rows | `FilterOnBadType` | `type` (meaning), `action`, `appliesTo`, `columns` | ✅ |
| Filter on range | `FilterOnNumericalRange` | `min`, `max`, `action`, `column` | 🔍 |
| Filter on date | `FilterOnDate` | `column`, `dateMode`, `action` | 🔍 |
| Flag on value | `FlagOnValue` | Same as FilterOnValue with `action: "FLAG"` | ✅ |
| Flag on formula | `FlagOnFormula` | `expression`, `flagColumn` | 🔍 |
| Flag on range | `FlagOnNumericalRange` | `min`, `max`, `flagColumn`, `column` | 🔍 |
| Flag on date | `FlagOnDate` | `column`, `dateMode`, `flagColumn` | 🔍 |
| Flag invalid rows | `FlagOnBadType` | `type`, `flagColumn`, `column` | 🔍 |
| Remove empty rows | `RemoveRowsOnEmpty` | `appliesTo`, `columns`, `keep` | ✅ |
| Flag holidays | `HolidaysComputer` | `column`, `outputColumn`, `country` | 🔍 |

#### Date & Time

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Parse date | `DateParser` | `column`, `formats: [...]`, `outCol`, `timezone` | 🔍 |
| Format date | `DateFormatter` | `column`, `outputColumn`, `format` | 🔍 |
| Extract date components | `DateComponentsExtractor` | `column`, `timezone`, `outYearColumn`, `outMonthColumn`, etc. | 🔍 |
| Date difference | `DateDifference` | `input1`, `input2`, `outputColumn`, `outputUnit` | 🔍 |
| Unix timestamp to date | `UnixTimestampParser` | `column`, `unit`, `outputColumn` | 🔍 |

#### Numeric

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Round numbers | `RoundProcessor` | `column`, `precision`, `mode` | 🔍 |
| Discretize (bin) | `BinnerProcessor` | `column`, `mode`, `nbBins` | 🔍 |
| Force numerical range | `NumericalRangeClipper` | `column`, `min`, `max` | 🔍 |
| Convert number formats | `NumericalFormatConverter` | `column`, `fromFormat`, `toFormat` | 🔍 |
| Numerical combinations | `NumericalCombinations` | `columns`, `operations` | 🔍 |
| Compute average | `MeanProcessor` | `columns`, `outputColumn` | 🔍 |

#### Split & Reshape

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Split column | `SplitColumn` / `ColumnSplitter` | `column`, `separator`, `limit` | 🔍 |
| Split into chunks | `SplitIntoChunks` | `column`, `chunkSize` | 🔍 |
| Split and fold | `SplitAndFold` | `column`, `separator` | 🔍 |
| Split and unfold | `SplitAndUnfold` | `column`, `separator` | 🔍 |
| Fold multiple columns (name) | `FoldColumnsByName` | `columns`, `valueColumn`, `keyColumn` | 🔍 |
| Fold multiple columns (pattern) | `FoldColumnsByPattern` | `pattern`, `valueColumn`, `keyColumn` | 🔍 |
| Unfold | `Unfold` | `column` | 🔍 |
| Unfold array | `UnfoldArray` | `column` | 🔍 |
| Triggered unfold | `TriggeredUnfold` | `column`, `triggerColumn` | 🔍 |
| Pivot | `Pivot` | `indexColumn`, `labelsColumn`, `valuesColumn` | 🔍 |
| Transpose | `Transpose` | | 🔍 |
| Split invalid cells | `InvalidCellSplitter` | `column`, `outputColumn`, `type` | 🔍 |

#### JSON & Array

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Extract from array | `ArrayExtractor` | `column`, `index` | 🔍 |
| Fold array | `ArrayFold` | `column` | 🔍 |
| Sort array | `ArraySort` | `column` | 🔍 |
| Concatenate JSON arrays | `ArraysConcat` | `columns`, `outputColumn` | 🔍 |
| Zip JSON arrays | `ZipArrays` | `columns`, `outputColumn` | 🔍 |
| Fold object keys | `FoldObject` | `column` | 🔍 |
| Nest columns | `NestColumns` | `columns`, `outputColumn`, `outputType` | 🔍 |
| Unnest object (flatten JSON) | `UnnestObject` | `column`, `prefix` | 🔍 |
| Extract with JSONPath | `JSONPathExtractor` | `column`, `expression`, `outputColumn` | 🔍 |

#### Joins & Enrichment

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Join with dataset (memory) | `MemoryEquiJoiner` | `leftCol`, `rightCol`, `rightInput`, `copyColumns`, `copyPrefix`, `fuzzy`, `maxLevenshtein` | ✅ |
| Fuzzy join | `FuzzyJoiner` | `leftCol`, `rightCol`, `rightInput`, `normalize`, `stem`, `maxLevenshtein` | 🔍 |
| Coalesce | `Coalescer` | `columns`, `outputColumn` | 🔍 |
| Merge long-tail values | `MergeLongTail` | `column`, `threshold`, `replaceValue` | 🔍 |
| Translate values by meaning | `MeaningTranslator` | `column`, `meaning` | 🔍 |

#### Geographic

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Create GeoPoint from lat/lon | `GeoPointCreator` | `latColumn`, `lonColumn`, `outputColumn` | 🔍 |
| Extract lat/lon from GeoPoint | `GeoPointExtractor` | `column`, `outLatColumn`, `outLonColumn` | 🔍 |
| Geo distance | `GeoDistanceProcessor` | `input1`, `input2`, `outputColumn`, `unit` | 🔍 |
| Geo join | `GeoJoiner` | `geoColumn`, `rightInput`, `rightGeoColumn` | 🔍 |
| Change CRS | `ChangeCRSProcessor` | `column`, `fromCRS`, `toCRS` | 🔍 |
| GeoIP resolve | `GeoIPResolver` | `column`, `outputColumn` | 🔍 |
| Create area (buffer) | `GeoPointBuffer` | `column`, `radius`, `outputColumn` | 🔍 |
| Extract geo info | `GeoInfoExtractor` | `column`, `extractType` | 🔍 |
| Enrich from French dept | `FrenchDepartementEnricher` | `column` | 🔍 |
| Enrich from French postcode | `FrenchPostcodeEnricher` | `column` | 🔍 |

#### Web & Email

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Split URL | `URLSplitter` | `column` | 🔍 |
| Split HTTP query string | `QueryStringSplitter` | `column` | 🔍 |
| Split email | `EmailSplitter` | `column` | 🔍 |
| Visitor ID generator | `VisitorIdGenerator` | `columns` | 🔍 |
| User agent parser | `UserAgentParser` | `column` | 🔍 |

#### Misc

| Processor | Internal Type ID | Key Params | Status |
|-----------|-----------------|------------|--------|
| Normalize measure | `MeasureNormalizer` | `column`, `inputUnit`, `outputUnit` | 🔍 |
| Convert currencies | `CurrencyConverter` | `column`, `fromCurrency`, `toCurrency` | 🔍 |
| Split currencies | `CurrencySplitter` | `column` | 🔍 |
| Generate big data | `BigDataGenerator` | `multiplier` | 🔍 |
| Enrich with build context | `BuildContextEnricher` | `outputColumn` | 🔍 |
| Enrich with record context | `RecordContextEnricher` | `outputColumn` | 🔍 |

---

## 3. Current CLI Gaps

### What exists today:

| Command | What it does | Prepare support |
|---------|-------------|----------------|
| `dku recipe create --type prepare` | Creates empty prepare recipe | ✅ Works |
| `dku recipe get <name>` | Shows recipe metadata | ✅ Works |
| `dku recipe get-definition <name>` | Gets full JSON definition | ✅ Works (but raw JSON is hard to use) |
| `dku recipe set-definition <name>` | Sets full JSON definition | ✅ Works (but must construct entire payload) |
| `dku recipe run <name>` | Runs the recipe | ✅ Works |

### What's completely missing:

| Missing capability | Impact |
|-------------------|--------|
| **List steps** in a prepare recipe | Agent can't see what steps exist |
| **Add a step** by type + params | Agent must build raw JSON |
| **Remove a step** by index/name | No way to remove individual steps |
| **Reorder steps** | No way to move steps |
| **Enable/disable steps** | No way to toggle steps |
| **Get step details** | Can't inspect a single step |
| **Create prepare with initial steps** | Must create empty, then add steps separately |
| **Common processor shortcuts** | No `create-formula`, `create-filter`, `create-rename` etc. |

---

## 4. Proposed CLI Commands

### Tier 1: Core Step Management (highest impact)

These are the foundational commands that make agents able to work with prepare recipes at all:

```bash
# List all steps in a prepare recipe
dku recipe list-steps <recipe> -P PROJ
dku recipe list-steps <recipe> -P PROJ -o json   # Full step detail

# Add a step to a prepare recipe (append by default)
dku recipe add-step <recipe> --type <ProcessorType> --params '{"column":"city","expression":"upper(city)"}' -P PROJ
dku recipe add-step <recipe> --type CreateColumnWithGREL --params '{"expression":"upper(city)","column":"city_upper"}' -P PROJ
dku recipe add-step <recipe> --type CreateColumnWithGREL --params @step.json -P PROJ
dku recipe add-step <recipe> --type ColumnRenamer --params '{"renamings":[{"from":"old","to":"new"}]}' -P PROJ
dku recipe add-step <recipe> --at 0 ...  # Insert at specific position

# Remove a step by index
dku recipe remove-step <recipe> --index 3 -P PROJ
dku recipe remove-step <recipe> --index 3 --index 5 -P PROJ  # Multiple

# Enable/disable a step
dku recipe disable-step <recipe> --index 2 -P PROJ
dku recipe enable-step <recipe> --index 2 -P PROJ

# Get details of a specific step
dku recipe get-step <recipe> --index 2 -P PROJ -o json
```

### Tier 2: Common Processor Shortcuts (agent productivity)

These wrap the most common prepare operations with named flags instead of raw JSON:

```bash
# Formula (GREL expression → new column)
dku recipe add-formula <recipe> --expr "upper(city)" --column city_upper -P PROJ

# Rename columns
dku recipe add-rename <recipe> --from old_name --to new_name -P PROJ
dku recipe add-rename <recipe> --mappings '{"old1":"new1","old2":"new2"}' -P PROJ

# Filter rows
dku recipe add-filter <recipe> --column status --values "active,pending" --action KEEP_ROW -P PROJ
dku recipe add-filter <recipe> --formula "price > 100" --action REMOVE_ROW -P PROJ

# Fill empty
dku recipe add-fill-empty <recipe> --column age --value "0" -P PROJ

# Delete columns
dku recipe add-delete-columns <recipe> --columns "tmp1,tmp2,debug_col" -P PROJ

# Find and replace
dku recipe add-find-replace <recipe> --column category --from "Electronics" --to "Tech" -P PROJ

# Split column
dku recipe add-split <recipe> --column full_name --separator " " -P PROJ

# Type casting / filter invalid
dku recipe add-type-filter <recipe> --column price --type Double --action REMOVE_ROW -P PROJ
```

### Tier 3: Advanced Operations

```bash
# Reorder steps
dku recipe move-step <recipe> --from-index 5 --to-index 1 -P PROJ

# Group steps (create a step folder)
dku recipe group-steps <recipe> --name "Cleaning" --indices 0,1,2 -P PROJ

# Duplicate a step
dku recipe copy-step <recipe> --index 3 -P PROJ

# Memory join with dataset
dku recipe add-join-step <recipe> --left-col id --right-dataset ref_data --right-col ref_id --copy-cols "name,desc" -P PROJ

# Python custom step
dku recipe add-python-step <recipe> --code @transform.py --column output_col -P PROJ
dku recipe add-python-step <recipe> --code "return row['price'] * 1.1" --column adjusted_price -P PROJ
```

---

## 5. Implementation Plan

### Phase 1: Core Infrastructure

**File changes:** `src/dku_cli/commands/recipe.py`, `src/dku_cli/errors.py`

1. **Helper: `_get_prepare_settings()`** — Gets recipe settings, validates it's a prepare/shaker type, returns `PrepareRecipeSettings`.

2. **`list-steps` command** — Table view: index | type | name | disabled | target columns. JSON view: full step dicts.

3. **`add-step` command** — Generic step addition. Takes `--type` and `--params` (JSON string, @file, or stdin). Optional `--at` for insertion index. Validates type is non-empty.

4. **`remove-step` command** — Removes by index. Supports multiple `--index` flags. Validates indices in range.

5. **`get-step` command** — Returns single step detail by index.

6. **`enable-step` / `disable-step`** — Toggle `disabled` flag.

### Phase 2: Smart Shortcuts

7. **`add-formula`** — Wraps `CreateColumnWithGREL` with `--expr` and `--column` flags.

8. **`add-rename`** — Wraps `ColumnRenamer` with `--from`/`--to` or `--mappings`.

9. **`add-filter`** — Wraps `FilterOnValue`/`FilterOnFormula` with `--column`/`--values`/`--formula`/`--action`.

10. **`add-fill-empty`** — Wraps `FillEmptyWithValue` with `--column`/`--value`.

11. **`add-delete-columns`** — Wraps `ColumnsSelector` with `--columns`.

12. **`add-find-replace`** — Wraps `FindReplace` with `--column`/`--from`/`--to`.

### Phase 3: Error Handling & Agent Guidance

13. **Recipe type validation** — All step commands must check that the recipe is actually a prepare recipe. Error: "Recipe 'X' is type 'python', not 'prepare'. Step commands only work on prepare recipes."

14. **Processor type suggestions** — When `--type` doesn't match known types, suggest closest match. "Unknown processor type 'rename'. Did you mean 'ColumnRenamer'?"

15. **`--help` text** — Every command must list common processor types and link to the full catalog.

16. **Schema propagation** — After adding steps, remind agent: "Run the recipe or check schema: `dku recipe check-schema <name> -P PROJ`"

### Phase 4: Skill & Reference Docs

17. **Update `skills/dku-cli/SKILL.md`** — Add prepare recipe section with step management examples.

18. **Create `skills/dataiku/references/prepare-processors.md`** — Full processor catalog with type IDs, params, and examples.

19. **Update cheat sheet** — Add rule: "Use `dku recipe add-step` for prepare recipe steps, NOT raw JSON."

---

## 6. Key Design Decisions

### Decision 1: Subcommands under `recipe` vs new `prepare` group

**Recommendation: Subcommands under `recipe`** — like `dku recipe add-step`, `dku recipe list-steps`.

Rationale: Prepare steps are recipe operations. A separate `dku prepare` group would break the `<noun> <verb>` pattern and confuse agents about when to use `recipe` vs `prepare`. The step commands naturally scope to prepare recipes and can validate the recipe type.

### Decision 2: Generic `add-step` vs only named shortcuts

**Recommendation: Both.** Generic `add-step --type X --params '{}'` for power users + named shortcuts like `add-formula`, `add-rename` for the top ~10 most common operations.

Rationale: The generic command is essential for agents to use ANY processor type (there are 95+). Named shortcuts are higher-level conveniences that prevent JSON errors for the most common cases. An agent can always fall back to `add-step` for unusual processors.

### Decision 3: How to identify the 🔍 processor type IDs

The internal type IDs for many processors are unconfirmed (marked 🔍). Strategy:

1. **Confirmed IDs** (from source code, .shaker files, community posts): Use directly.
2. **Inferred IDs**: Create a test recipe in DSS, add each processor type via UI, then export the definition to get the exact type string.
3. **CLI `--help` text**: List only confirmed IDs. For unconfirmed, tell agent to use `dku recipe get-definition` on an existing recipe to discover the type.

### Decision 4: Step identification — index vs name

**Recommendation: Index-based** for remove/disable/enable/move. Steps can share names (or have no name), but indices are always unique. Show indices in `list-steps` output.

---

## 7. Confirmed Processor Type IDs (from source)

These are confirmed from dataikuapi source, .shaker files, and community examples:

| Internal Type ID | UI Name | Source |
|-----------------|---------|--------|
| `CreateColumnWithGREL` | Formula | dataikuapi analysis.py |
| `FillEmptyWithValue` | Fill empty with value | dataikuapi recipe.py docstring |
| `ColumnRenamer` | Rename columns | dataikuapi recipe.py docstring |
| `ColumnCopier` | Copy column | .shaker file |
| `ColumnReorder` | Move columns | .shaker file |
| `ColumnsSelector` | Delete/keep columns | .shaker file |
| `StringTransformer` | Transform string | .shaker file |
| `FindReplace` | Find and replace | .shaker file |
| `PythonUDF` | Python function | .shaker file |
| `MemoryEquiJoiner` | Join with dataset (memory) | .shaker file |
| `FlagOnValue` | Flag/filter on value | dataikuapi analysis.py |
| `FilterOnBadType` | Filter invalid rows | dataikuapi analysis.py |
| `RemoveRowsOnEmpty` | Remove empty rows | dataikuapi analysis.py |
| `FilterOnBadType` | Filter on bad type | dataikuapi analysis.py |

### Discovery Method for Remaining IDs

To confirm the remaining ~80 processor type IDs:

```python
# In a DSS notebook or recipe:
import dataikuapi

client = dataikuapi.DSSClient("http://localhost:11200", api_key="...")
project = client.get_project("MYPROJ")

# Create a prepare recipe via UI with each step type, then:
recipe = project.get_recipe("my_prepare_recipe")
settings = recipe.get_settings()
for i, step in enumerate(settings.raw_steps):
    print(f"{i}: type={step['type']}, params={step['params'].keys()}")
```

---

## 8. Example: Full Agent Workflow (Proposed)

```bash
# 1. Create prepare recipe
dku recipe create clean_data --type prepare --input raw_data --output-ds clean_data -P PROJ

# 2. Add steps
dku recipe add-step clean_data --type RemoveRowsOnEmpty --params '{"appliesTo":"ALL","keep":false}' -P PROJ
dku recipe add-step clean_data --type ColumnRenamer --params '{"renamings":[{"from":"CustomerName","to":"customer_name"},{"from":"OrderDate","to":"order_date"}]}' -P PROJ
dku recipe add-step clean_data --type CreateColumnWithGREL --params '{"expression":"upper(customer_name)","column":"customer_name_upper"}' -P PROJ
dku recipe add-step clean_data --type FillEmptyWithValue --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"value":"0"}' -P PROJ
dku recipe add-step clean_data --type FilterOnBadType --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"Double","action":"REMOVE_ROW","booleanMode":"AND"}' -P PROJ

# 3. Review steps
dku recipe list-steps clean_data -P PROJ

# 4. Disable a step temporarily
dku recipe disable-step clean_data --index 2 -P PROJ

# 5. Run the recipe
dku recipe run clean_data -P PROJ --wait

# 6. Check output
dku dataset head clean_data -P PROJ
```

---

## Appendix: Related dataikuapi Methods

| Method | On Class | Returns | Notes |
|--------|----------|---------|-------|
| `get_settings()` | `DSSRecipe` | `PrepareRecipeSettings` | When type is `prepare`/`shaker` |
| `get_definition_and_payload()` | `DSSRecipe` | `DSSRecipeDefinitionAndPayload` | Deprecated, use `get_settings()` |
| `raw_steps` | `PrepareRecipeSettings` | `list[dict]` | Mutable reference |
| `add_processor_step(type, params)` | `PrepareRecipeSettings` | `None` | Appends step |
| `obj_payload` | `DSSRecipeSettings` | `dict` | Parsed JSON payload |
| `str_payload` | `DSSRecipeSettings` | `str` | Raw JSON string |
| `save()` | `DSSRecipeSettings` | `dict` | PUT to API |
| `get_status()` | `DSSRecipe` | `DSSRecipeStatus` | Schema update messages |
| `compute_schema_updates()` | `DSSRecipe` | (via `get_status()`) | Check schema impacts |
| `run()` | `DSSRecipe` | varies | Standard recipe execution |

## Appendix: Full Doc URL → Processor Page Map

95 processor pages at `https://doc.dataiku.com/dss/latest/preparation/processors/`:

```
array-extract, array-fold, array-sort, arrays-concat, binner, change-crs,
coalesce, column-copy, column-rename, columns-concat, columns-select,
column-pseudonymization, count-matches, currency-converter, currency-splitter,
create-if-then-else, date-components-extract, date-difference, date-formatter,
date-parser, email-split, enrich-french-departement, enrich-french-postcode,
enrich-with-build-context, enrich-with-record-context, extract-ngrams,
extract-numbers, fill-column, fill-empty, fill-empty-with-computed-value,
filter-on-date, filter-on-formula, filter-on-meaning, filter-on-range,
filter-on-value, find-replace, flag-on-date, flag-on-formula, flag-on-meaning,
flag-on-range, flag-on-value, fold-columns-by-name, fold-columns-by-pattern,
fold-object, formula, fuzzy-join, generate-big-data, geo-distance,
geo-info-extractor, geo-join, geoip, geopoint-buffer, geopoint-create,
geopoint-extract, grok, holidays-computer, invalid-split, join, jsonpath,
long-tail, mean, meaning-translate, measure-normalize, merge-long-tail-values,
move-columns, negate, number-clipping, numerical-combinations,
numerical-format-convert, object-nest, object-unnest-json, pattern-extract,
pivot, python-custom, querystring-split, remove-empty, round, simplify-text,
split-fold, split-into-chunks, split-unfold, split, switch-case,
string-transform, tokenizer, transpose, triggered-unfold, unfold, unfold-array,
unixtimestamp-parser, up-down-fill, url-split, user-agent, visitor-id,
zip-arrays
```
