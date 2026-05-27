# Alteryx Workflow Patterns

Recurring multi-tool Alteryx patterns and their collapsed DSS equivalents.

## Workflow patterns

Patterns that span multiple tools. Recognize the pattern, collapse the group into one recipe where possible.

### Pattern: Range join (GenerateRows → Join)

**Alteryx:** `TextToColumns` (split "start-end") → `AlteryxSelect` (cast to int) → `GenerateRows` (expand start..end) → `Join` (equi-join on expanded value).

**Dataiku:** collapse the whole group into one SQL recipe:

```sql
SELECT a.*, b.*
FROM customers a
JOIN ranges b ON a.postal_area BETWEEN CAST(SPLIT_PART(b.range,'-',1) AS INT)
                                   AND CAST(SPLIT_PART(b.range,'-',2) AS INT)
```

Or (non-SQL): Prepare split + Python merge with pandas `merge_asof` / explicit `apply`.

### Pattern: Filter → Union (conditional reroute)

**Alteryx:** `Filter` → True branch processed → `Union` with False branch.

**Dataiku:** use two Prepare recipes on the same input (one filters True, one False), apply different logic to each, then `Stack`. Or — cleaner — a single Prepare with a `CreateColumnWithGREL` that branches (`if(cond, procA(x), procB(x))`).

### Pattern: Cross-tab → Dynamic Rename (pivot with renamed columns)

**Alteryx:** `CrossTab` then `DynamicRename` to clean up auto-generated column names.

**Dataiku:** Pivot recipe + a trailing Prepare with static `RenameColumns` rules. DynamicRename-from-input-table requires a Python recipe.

### Pattern: Multi-Row Formula → Summarize (de-duped running state)

**Alteryx:** MultiRowFormula marks "first in group", then Filter to first-only, then Summarize.

**Dataiku:** Window recipe with `first_value` aggregation (no Filter needed), or Group with `first` agg.
