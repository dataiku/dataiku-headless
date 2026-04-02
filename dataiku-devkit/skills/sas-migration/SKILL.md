---
name: sas-migration
description: Migrate SAS programs (EGP projects and .sas files) to Dataiku DSS flows. Use when the user provides SAS code, an EGP file, or asks to convert/migrate/translate SAS to Dataiku. Covers extraction, analysis, flow planning, and execution via the dku CLI.
triggers:
  - sas
  - sas migration
  - migrate sas
  - egp
  - enterprise guide
  - sas to dataiku
  - convert sas
  - translate sas
  - sas program
  - sas code
  - proc sql migration
  - data step migration
globs:
  - "**/*.egp"
  - "**/*.sas"
metadata:
  author: dataiku
  version: "1.0.0"
  tags: migration, sas, egp, enterprise-guide
---

> **Migration Cheat Sheet (read this first)**
>
> 1. **ALWAYS run the analyzer tool first.** `python sas_analyzer.py extract <file> -o ./sas_out/` — read `manifest.json` before doing anything else.
> 2. **STOP — DO NOT use Python recipes for filters, date parsing, string extraction, formulas, lookups, or aggregations.** Use Prepare recipes (filter rows, date parser, regex extract, formula, find-and-replace), Group recipes, Join recipes, Sort recipes. **Python is ONLY for logic that has no visual equivalent** (hash lookups, DO loops over arrays, PROC IML). If you reach for Python, you are probably wrong — check `references/sas-to-dataiku.md` first.
> 3. **Maximize Dataiku stickiness.** The goal is NOT a 1:1 SAS translation. The goal is a Dataiku-native flow that uses visual recipes, so users learn Dataiku's way of working. Every Python recipe is a missed opportunity for stickiness.
> 4. **Decompose SAS steps into visual chains.** One PROC SQL with computed columns, filters, and aggregation should become: Prepare (filter + compute) → Group (aggregate). Don't collapse everything into one Python recipe just because the SAS was one PROC SQL.
> 5. **Map LIBNAME to connections, %LET to project variables.** `LIBNAME` → `dku connection list`, `%LET var=val` → `dku project set-variable var val -P PROJ`.
> 6. **Macros → project Python library.** Put shared logic in `lib/python/` and import from Python recipes. Simple parameter macros → project variables.
> 7. **Verify after every step.** `dku dataset head OUTPUT -P PROJ` + `dku dataset schema OUTPUT -P PROJ` — compare row counts and column types with the SAS output.
> 8. **Plan before building.** For complex programs (10+ steps), write out the full Dataiku flow plan first. For each SAS step, explicitly name which visual recipe type you will use. If you write "Python recipe", justify why no visual recipe works.
> 9. **Use companion skills.** Always use with `dku-cli` (execution) and `dataiku` (platform knowledge). **READ `dataiku` skill's `references/prepare-processors.md`** before writing any Prepare recipe — it has the exact processor types and parameters.

# SAS Migration

Migrate SAS Enterprise Guide projects (.egp) and SAS programs (.sas) to Dataiku DSS flows.

## Companion Skills

**This skill, `dku-cli`, and `dataiku` work together.**

- **This skill** tells you *how to migrate* — extraction tool, SAS→Dataiku mapping, migration workflow
- **`dku-cli`** tells you *how to execute* — CLI commands, flags, chaining
- **`dataiku`** tells you *what to build* — recipe types, platform patterns, visual recipes

## The Stickiness Principle

**The migration is not just about reproducing SAS output. It is about onboarding users to Dataiku.**

Every visual recipe in the flow is a touchpoint where the user sees Dataiku's value:
- Prepare recipes → users learn processors, can modify steps without coding
- Group/Join/Sort recipes → users see visual configuration, can adjust without SQL
- Python recipes → users see a black box, learn nothing about Dataiku

**Decision tree for each SAS construct:**
```
Can this be a Prepare recipe? (filter, rename, compute, parse, recode)
  → YES → Use Prepare recipe
  → NO →
    Can this be a Group/Join/Sort/Stack/Pivot/Split recipe?
      → YES → Use that visual recipe
      → NO →
        Can this be an SQL recipe? (standard SQL, no SAS-specific functions)
          → YES → Use SQL recipe
          → NO → Use Python recipe (document WHY)
```

## SAS Construct → Visual Recipe Translation

### Gotchas (read before writing any Prepare recipe)

- **No `create-prepare` shortcut.** Use `dku recipe create RECIPE -t prepare -i INPUT --output-ds OUTPUT -P PROJ`. Output dataset must exist first: `dku dataset create OUTPUT --type Filesystem -c filesystem_managed -P PROJ`.
- **`apply-schema` required.** After adding steps, run `dku recipe apply-schema RECIPE -P PROJ` before the first build — otherwise computed columns are silently missing.
- **`FilterOnFormula` requires a plugin.** Do NOT use `add-filter-rows --formula`. Use `FilterOnValue` with `matchingMode: PATTERN` (regex) or `SUBSTRING` instead.
- **DateDifference computes `input2 - input1`**, not `input1 - input2`. Set `input1` to the earlier date.
- **DateParser requires full params.** Must include `appliesTo`, `columns` (array), `formats`, `lang`, `timezone_id`, `outCol`, `outType`. See examples below.

### Filters and WHERE clauses → Prepare recipe
```bash
# Remove empty rows (native processor, no plugin needed)
dku recipe add-step RECIPE -t RemoveRowsOnEmpty --params '{"columns": ["col"], "keep": false, "appliesTo": "SINGLE_COLUMN"}' -P PROJ

# Filter by pattern (e.g. SAS: WHERE title NOT LIKE 'Disc %')
dku recipe add-step RECIPE -t FilterOnValue --params '{"appliesTo": "SINGLE_COLUMN", "columns": ["DVD Title"], "values": ["Disc .*"], "matchingMode": "PATTERN", "action": "REMOVE_ROW", "normalizationMode": "EXACT"}' -P PROJ

# Filter by substring (e.g. SAS: WHERE title NOT CONTAINS 'Shipment')
dku recipe add-step RECIPE -t FilterOnValue --params '{"appliesTo": "SINGLE_COLUMN", "columns": ["DVD Title"], "values": ["Shipment"], "matchingMode": "SUBSTRING", "action": "REMOVE_ROW", "normalizationMode": "EXACT"}' -P PROJ
```

### Date parsing → DateParser processor
```bash
# Parse date strings in-place (correct canonical params)
dku recipe add-step RECIPE -t DateParser --params '{"appliesTo": "SINGLE_COLUMN", "columns": ["Shipped"], "formats": ["M/d/yy", "MM/dd/yy"], "lang": "auto", "timezone_id": "UTC", "outCol": "", "outType": {"name": "out", "type": "date"}}' -P PROJ
```

### Date calculations → DateDifference processor (NOT GREL)
```bash
# SAS DATDIF → DateDifference processor (input2 - input1 = Returned - Shipped)
dku recipe add-step RECIPE -t DateDifference --params '{"input1": "Shipped", "compareTo": "COLUMN", "input2": "Returned", "output": "DaysOut", "outputUnit": "DAYS", "timezone_id": "UTC"}' -P PROJ

# Computed columns via GREL formula
dku recipe add-formula RECIPE -c CostPerMovie -e 'round(DaysOut * 10.0 / 30.0 * 100) / 100' -P PROJ
```

### String extraction → GREL formula (preferred) or RegexpExtractor
```bash
# SAS SUBSTR + PRXMATCH → GREL substring with indexOf
dku recipe add-formula RECIPE -c ActualRating -e 'substring(Rating, indexOf(Rating, ".0") - 1, indexOf(Rating, ".0"))' -P PROJ

# SAS SCAN(Title, 1, ':') → GREL split
dku recipe add-formula RECIPE -c SeriesTitle -e 'if(indexOf(Title, ":") > 0, substring(Title, 0, indexOf(Title, ":")), Title)' -P PROJ
```

### Value lookups / PROC FORMAT → copy + find-and-replace
```bash
# Copy column then replace values
dku recipe add-step RECIPE -t ColumnCopier --params '{"inputColumn": "ActualRating", "outputColumn": "RatingPhrase"}' -P PROJ
dku recipe add-find-replace RECIPE -c RatingPhrase --find "1" --replace "Hated it" -P PROJ
dku recipe add-find-replace RECIPE -c RatingPhrase --find "5" --replace "Loved it" -P PROJ
```

### Aggregations (PROC MEANS/FREQ/SQL GROUP BY) → Group recipe
```bash
dku recipe create-group summary -i clean_data --output-ds summary -k Date --agg 'amount:sum' -P PROJ
```

### Date reformatting for grouping → Prepare (trunc) + Group
```bash
# GREL trunc() to get first day of month — NOT firstDayOfMonth() (doesn't exist)
dku recipe add-formula RECIPE -c month_date -e 'trunc(Date, "months")' -P PROJ
# Then group by month
dku recipe create-group monthly_summary -i daily_with_month --output-ds monthly -k month_date --agg 'minutes:sum' -P PROJ
```

### Merges → Join recipe
```bash
dku recipe create-join enriched -i left_ds -i right_ds --output-ds enriched --join-type left -k join_key -P PROJ
```

### Reference data (SAS inline DATA steps) → Upload CSV
```bash
dku dataset create months_calendar --type UploadedFiles -P PROJ
dku dataset upload months_calendar months.csv -P PROJ
```

## Workflow

### Step 1: Extract and Analyze

Run the analyzer tool on the SAS input file:

```bash
python <path-to-skill>/tools/sas_analyzer.py extract project.egp -o ./sas_out/
```

This produces:
- `manifest.json` — project structure, data lineage, macro catalog, construct inventory
- Individual `.sas` files — one per code task/block, clean and readable

Read `manifest.json` to understand the program structure before proceeding.

### Step 2: Plan the Dataiku Flow (CRITICAL)

For each step in the manifest, write out the planned Dataiku recipe **before building anything**:

```
Step 1: netflix_history → [Prepare: RemoveRowsOnEmpty, FilterOnValue (Disc/Shipment),
        DateParser (Shipped, Returned), DateDifference (DaysOut),
        formula (CostPerMovie), formula (ActualRating from substring),
        ColumnCopier + FindReplace (RatingPhrase)] → titles_days_ratings

Step 2: instant_titles → [Group: key=Date, agg=MinutesViewed:sum] → daily_summary
```

**Rules for the plan:**
1. Every step must name a specific recipe type (Prepare, Group, Join, Sort, Split, SQL, Python)
2. For Prepare recipes, list each processor (filter, formula, regex extract, etc.)
3. If you write "Python", you MUST explain why no visual recipe works
4. Count your Python recipes — if more than 20% of the flow is Python, re-examine your plan
5. Read the `.sas` file for each step to understand the exact logic before choosing a recipe type

### Step 3: Execute via dku CLI

Build the flow using `dku-cli` commands. Always chain related commands with `&&`.

Prefer this pattern for Prepare recipes:
```bash
# 1. Create output dataset first (no create-prepare shortcut exists)
dku dataset create clean_data --type Filesystem -c filesystem_managed -P PROJ &&
# 2. Create prepare recipe
dku recipe create prepare_clean_data -t prepare -i raw_data --output-ds clean_data -P PROJ &&
# 3. Add steps one by one
dku recipe add-step prepare_clean_data -t RemoveRowsOnEmpty --params '{"columns": ["col1"], "keep": false, "appliesTo": "SINGLE_COLUMN"}' -P PROJ &&
dku recipe add-formula prepare_clean_data -c new_col -e 'expression_here' -P PROJ &&
# 4. Apply schema (CRITICAL — computed columns won't appear without this)
dku recipe apply-schema prepare_clean_data -P PROJ &&
# 5. Build
dku recipe run prepare_clean_data -P PROJ --wait
```

### Step 4: Verify

After each migration step, compare with original SAS output:

```bash
dku dataset head OUTPUT -P PROJ -n 10    # Spot check values
dku dataset schema OUTPUT -P PROJ         # Verify columns and types
```

## Reference

| Document | When to read |
|----------|-------------|
| `references/sas-to-dataiku.md` | Before translating any SAS construct — mapping table + migration patterns |

## Tool

| Tool | Purpose | Usage |
|------|---------|-------|
| `tools/sas_analyzer.py` | Extract EGP/SAS files, analyze constructs, produce manifest | `python sas_analyzer.py extract <file> -o <dir>` |
