# Dataiku Structured Agents (Deterministic Blocks)

Build production-grade AI agents using Dataiku's deterministic blocks architecture. Unlike free-form agents that can loop indefinitely and produce variable results, structured agents guarantee consistent, auditable outputs through explicit control flow.

## When to Use

- Designing multi-step AI workflows requiring consistency across runs
- Building compliance, regulatory, or audit-sensitive automation
- Creating human-in-the-loop validation workflows
- Processing documents with structured extraction requirements
- Implementing systematic data analysis with state accumulation

---

## Core Concepts

### Why Deterministic Blocks?

| Non-Deterministic Agents | Deterministic Blocks |
|--------------------------|----------------------|
| Free-form loops may miss items or duplicate work | For Each guarantees every item processed exactly once |
| Variable outputs between runs | Structured outputs ensure consistent schema |
| Difficult to audit reasoning | Full state lineage and traceability |
| Ad-hoc variable handling | Explicit state management |
| Unpredictable tool calls | Controlled tool invocation patterns |

### Block Types Reference

| Block Type | Purpose | Key Use Cases |
|------------|---------|---------------|
| **LLM with Structured Output** | Extract/generate data with guaranteed schema | Document parsing, gap analysis, classification |
| **Expression Block** | Conditional routing based on state | Type checking, validation gates |
| **For Each Loop** | Process arrays systematically | Per-item analysis, batch operations |
| **Dataset Lookup** | Query datasets with filters | Finding existing records, retrieving context |
| **set_state_entries** | Save/accumulate values in state | Loop accumulation, context passing |
| **ReAct Loop** | Tool-using agent with iteration | Knowledge bank search, multi-tool workflows |
| **Core ReAct Loop** | ReAct with HITL capabilities | Validation, database writes with approval |
| **docxtpl** | Generate Word documents from templates | Reports, compliance documents |
| **Emit Output** | Return final message to user | Summary, completion notification |

---

## State Management

### State Structure Principles

State is the central nervous system of structured agents. Design it deliberately.

```javascript
state = {
  // Input context (from initial parsing)
  parsed_input: { /* structured extraction result */ },

  // Loop variables (ephemeral - reset each iteration)
  current_item: { /* For Each loop item */ },
  current_item_context: { /* derived context */ },

  // Accumulated results (persist across iterations)
  all_results: [],  // grows with each loop iteration

  // Final validated output
  validated: {
    results: [],
    summary: { /* computed statistics */ }
  }
}
```

### Accumulation Pattern (Critical for For Each Loops)

The most important pattern for loops—accumulate results without losing previous iterations:

```javascript
// In set_state_entries block at END of For Each loop
{
  "all_gaps": [
    ...(state.all_gaps || []),      // Spread existing array (or empty if first iteration)
    ...state.current_iteration_gaps  // Spread current iteration's results
  ]
}
```

**Why this pattern?**
- `state.all_gaps || []` handles first iteration when array doesn't exist
- Spread operators ensure flat array (no nested arrays)
- Each iteration adds to the accumulated result

### State Variable Naming Convention

| Prefix | Scope | Example |
|--------|-------|---------|
| `current_*` | Loop-scoped, reset each iteration | `current_article_ref`, `current_test_gaps` |
| `all_*` | Accumulated across iterations | `all_test_gaps`, `all_findings` |
| `validated_*` | Post-HITL approved data | `validated_results`, `validated_summary` |

---

## Block Configuration Patterns

### Pattern 1: Document Parsing (LLM + Structured Output)

**Use case:** Extract structured data from unstructured documents (PDFs, contracts, regulations)

**Schema Design Principles:**
- Use `enum` for categorical fields (prevents hallucination)
- Include `description` for each property (guides LLM)
- Set `required` array to enforce critical fields
- Keep string lengths reasonable (avoid unbounded fields)

**Example Schema:**
```json
{
  "type": "object",
  "properties": {
    "document_type": {
      "type": "string",
      "enum": ["AMENDMENT", "NEW_REGULATION", "GUIDANCE"],
      "description": "Classification of document type"
    },
    "document_id": {
      "type": "string",
      "description": "Unique identifier in format XX-NNN-YYYY"
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "ref": {"type": "string"},
          "type": {"type": "string", "enum": ["REPLACED", "INSERTED", "DELETED"]},
          "summary": {"type": "string", "description": "One sentence summary"}
        },
        "required": ["ref", "type", "summary"]
      }
    }
  },
  "required": ["document_type", "document_id", "items"]
}
```

---

### Pattern 2: Conditional Routing (Expression Block)

**Use case:** Branch workflow based on document type, validation status, or threshold

**Expression Syntax:**
```javascript
// Simple equality check
state.parsed_document.document_type === "AMENDMENT"

// Multiple conditions
state.parsed_document.document_type === "AMENDMENT" && state.parsed_document.items.length > 0

// Threshold check
state.risk_score > 0.7

// Array existence
state.all_gaps && state.all_gaps.length > 0
```

---

### Pattern 3: Systematic Processing (For Each Loop)

**Use case:** Process each item in an array with guaranteed coverage

**Loop Structure (4 blocks minimum):**

```
┌─────────────────────────────────────────┐
│ FOR EACH: state.parsed_document.items   │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ 3.1 set_state_entries (Start)   │    │
│  │     Save current item context   │    │
│  └─────────────────┬───────────────┘    │
│                    ↓                    │
│  ┌─────────────────────────────────┐    │
│  │ 3.2 Dataset Lookup              │    │
│  │     Find related records        │    │
│  └─────────────────┬───────────────┘    │
│                    ↓                    │
│  ┌─────────────────────────────────┐    │
│  │ 3.3 LLM Analysis (Structured)   │    │
│  │     Per-item processing         │    │
│  └─────────────────┬───────────────┘    │
│                    ↓                    │
│  ┌─────────────────────────────────┐    │
│  │ 3.4 set_state_entries (Loop End)│    │
│  │     Accumulate results          │    │
│  └─────────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

**Block 3.1 - Save Context:**
```json
{
  "current_item_ref": "{{state.item.ref}}",
  "current_item_type": "{{state.item.type}}",
  "current_item_summary": "{{state.item.summary}}"
}
```

**Block 3.2 - Dataset Lookup:**
```sql
-- Filter: Find related records for current item
parent_id = '{{state.parsed_document.parent_id}}'
AND item_ref LIKE '{{state.current_item_ref}}%'
```

**Block 3.4 - Accumulate (CRITICAL):**
```javascript
{
  "all_results": [
    ...(state.all_results || []),
    ...state.current_iteration_results
  ]
}
```

---

### Pattern 4: Dataset Lookup with Filtering

**Use case:** Retrieve contextual records for analysis

**Filter Syntax:**
```sql
-- Exact match
column_name = '{{state.variable}}'

-- Pattern matching (LIKE)
article_ref LIKE '{{state.current_article_ref}}%'

-- Multiple conditions
regulation_id = '{{state.parent_reg}}' AND status != 'ARCHIVED'

-- Date filtering
created_date >= '{{state.start_date}}'
```

**Output Handling:**
- Returns array of matching rows
- Empty array `[]` if no matches (handle in subsequent LLM prompt)
- All columns selected by default; specify columns for efficiency

---

### Pattern 5: Per-Item Analysis (LLM + Structured Output in Loop)

**Use case:** Analyze each item against context, produce filtered results

**System Prompt Guidelines:**
- Reference loop context via `{{item.field}}` or `{{state.item.field}}`
- Include existing records context (even if empty)
- Define clear status enums to prevent hallucination
- Enforce verbosity limits in prompt
- Filter out "no action needed" items at source

**Critical Output Rules:**
1. **Only output items requiring action** (filtered status)
   - Do NOT output items needing no action
   - If all items are low-priority, return empty array []

2. **Consolidation rules** - Avoid multiple items for the same concept
3. **Verbosity constraints** - Maximum 1-2 sentences per field

---

### Pattern 6: ReAct Loop with Knowledge Bank

**Use case:** Semantic search over documents, multi-query analysis

**Knowledge Bank Search Guidelines:**
```
1. Search ONCE per item using concise, targeted queries
2. Use 2-4 word queries focused on core topic
3. Good: "leverage ratio calculation"
4. Bad: "how does the policy document describe the calculation"
```

**Structured Output for ReAct:**
```json
{
  "type": "object",
  "properties": {
    "analysis_results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "item_ref": {"type": "string"},
          "status": {"type": "string", "enum": ["ALIGNED", "OUTDATED", "NOT_FOUND"]},
          "evidence_text": {"type": "string", "description": "Excerpt (50-75 words max)"},
          "recommendation": {"type": "string", "description": "Action (50-75 words max)"}
        },
        "required": ["item_ref", "status"]
      }
    }
  }
}
```

---

### Pattern 7: Human-in-the-Loop Validation (Core ReAct + HITL Tools)

**Use case:** User review, approval, and database updates

**Key Principle:** Tool response IS the validated data—no secondary confirmation needed.

**Tool Call Management:**
- Check message history before making tool calls
- If ValidateFindings already called -> skip to next step
- If UpdateDatabase already called -> skip to final step
- Never call the same tool twice

#### HITL via the LLM Streaming API (Webapp Integration)

Structured agents expose HITL entirely through the LLM completion streaming API — there is **no separate run/interaction API**.

**Phase 1 — initial run, capture pause state:**
```python
from dataikuapi.dss.llm import DSSLLMStreamedCompletionFooter

llm = client.get_default_project().get_llm("agent:AGENT_ID")
comp = llm.new_completion()
comp.with_message(user_query, role="user")

pending_hitl_requests = None
pending_memory_fragment = None
text_buf = []

for chunk in comp.execute_streamed():
    if isinstance(chunk, DSSLLMStreamedCompletionFooter):
        break  # completed or paused — check pending_hitl_requests to know which
    if getattr(chunk, "type", None) != "content":
        continue
    chunk_data = getattr(chunk, "data", {}) or {}
    if "toolValidationRequests" in chunk_data:
        pending_hitl_requests = chunk_data["toolValidationRequests"]
    if "memoryFragment" in chunk_data:
        pending_memory_fragment = chunk_data["memoryFragment"]
    text = getattr(chunk, "text", None) or ""
    if text:
        text_buf.append(text)

# If pending_hitl_requests is not None → agent is paused for HITL
# If None → agent completed
```

**Phase 2 — resume after user decision:**
```python
comp2 = llm.new_completion()
comp2.with_message(original_query, role="user")
comp2.with_memory_fragment(pending_memory_fragment)
comp2.with_tool_validation_requests(pending_hitl_requests)
for req in pending_hitl_requests:
    comp2.with_tool_validation_response(
        validation_request_id=req["id"],  # field name: verify via payload inspection
        validated=True,   # or False to reject
        arguments=None,
    )
# Then iterate comp2.execute_streamed() same as Phase 1
```

**HITL payload parsing:** `toolValidationRequests[0].toolCall.arguments` is a JSON string. Parse it to extract structured fields (e.g. `policy_findings`, `all_test_gaps`, `regulation_metadata`). Field names depend on the agent's validate findings tool schema.

**Verify the request ID field name** before use — it may be `"id"`, `"validationRequestId"`, `"request_id"`, or `"requestId"`:
```python
req = pending_hitl_requests[0]
print(list(req.keys()))  # confirm the correct field name
```

---

### Pattern 8: Document Generation (docxtpl)

**Use case:** Generate professional reports from validated data

**Template Variable Mapping:**
```
State Path                              -> Template Variable
state.validated.document_id             -> {{document_id}}
state.validated.results                 -> {% for item in results %}
state.validated.summary.count_a         -> {{summary.count_a}}
```

**Jinja2 Syntax in Templates:**
```
# Simple variable
{{state.validated.document_id}}

# Loop
{% for item in state.validated.results %}
- {{item.ref}}: {{item.status}}
{% endfor %}

# Conditional
{% if item.evidence_text %}
Evidence: "{{item.evidence_text}}"
{% endif %}
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Cross-Item Dependencies in For Each Loops

**Problem:** Loop processes items in isolation, missing dependencies between items.

**Solution:** Use broader dataset lookup with pattern matching:
```sql
-- Instead of exact match
article_ref = '{{state.current_article_ref}}'

-- Use root-level pattern matching
article_ref LIKE 'Art.429%'  -- Captures 429, 429a, 429b, 429(2), etc.
```

### Pitfall 2: Tool Response Misinterpretation

**Problem:** LLM treats HITL tool response as "form opened" rather than "data returned."

**Solution:** Explicit instruction in prompt:
```
CRITICAL: ValidateFindings tool does NOT open a form waiting for input.
It directly RETURNS validated data with all user edits already applied.
The tool response IS your data source—process it immediately.
```

### Pitfall 3: Unbounded LLM Verbosity

**Problem:** LLM generates verbose explanations, breaking document formatting.

**Solution:** Explicit verbosity constraints in prompt AND schema:
```
VERBOSITY CONSTRAINTS:
- reason: Maximum 1-2 sentences (30-50 words)
- action: Maximum 1 sentence (20-35 words)
```

### Pitfall 4: Lost State in Loop Accumulation

**Wrong:**
```javascript
{
  "all_results": state.current_results  // Overwrites!
}
```

**Correct:**
```javascript
{
  "all_results": [
    ...(state.all_results || []),
    ...state.current_results
  ]
}
```

### Pitfall 5: Empty Array Handling

**Problem:** LLM confused when dataset lookup returns no records.

**Solution:** Explicit handling in prompt:
```
If no existing records are found:
- For INSERTED items: All requirements are NOT_COVERED
- For REPLACED items: Cannot be UPDATE_NEEDED (nothing to update)
```

### Pitfall 6: Duplicate Tool Calls

**Problem:** LLM calls same tool multiple times.

**Solution:** History check instruction:
```
TOOL CALL MANAGEMENT:
- Check message history before making tool calls
- If ValidateFindings already called -> skip to Step 2
- If UpdateDatabase already called -> skip to Step 3
- Never call the same tool twice
```

---

## Architecture Decision Guide

### When to Use For Each vs ReAct

| Use For Each When | Use ReAct When |
|-------------------|----------------|
| Processing items requires dataset lookup | Need semantic search over documents |
| Each item analysis is independent | Need to see all items for holistic analysis |
| State accumulation pattern needed | Multi-tool orchestration required |
| Guaranteed coverage critical | Search-iterate-decide pattern |

### When to Use Structured Output vs Free Text

| Use Structured Output | Use Free Text |
|-----------------------|---------------|
| Data feeds downstream blocks | Final user-facing explanation |
| Schema validation critical | Creative/narrative content |
| Parsing required | Conversational response |
| Consistency across runs | One-time analysis |

---

## Testing & Debugging

### State Inspection Points

Add diagnostic set_state_entries blocks to capture intermediate state:

```javascript
{
  "debug_loop_iteration": state.item.ref,
  "debug_existing_count": state.existing_records.length,
  "debug_gaps_found": state.current_gaps.length
}
```

### Common Debug Checks

1. **After Parsing:** Verify `state.parsed_document.items.length` matches expected
2. **After Dataset Lookup:** Check `state.existing_records` has expected filters applied
3. **After Loop:** Verify `state.all_results.length` equals sum of iterations
4. **After Validation:** Confirm `state.validated` structure matches template expectations

### Test Scenarios

| Scenario | What to Verify |
|----------|----------------|
| Empty input | Routing blocks to skip/error path |
| Single item | Accumulation pattern works with one iteration |
| All items filtered out | Empty array `[]` handled gracefully |
| HITL rejection | Workflow handles user declining to approve |
| Large input | Performance and state size manageable |

---

## Key Principles Summary

1. **State is king** - Design state structure deliberately; it's the data backbone
2. **Accumulate, don't overwrite** - Use spread operators in loop accumulation
3. **Filter at source** - Have LLMs return only actionable items
4. **Constrain verbosity** - Explicit word limits prevent document overflow
5. **Tools return data** - HITL tool responses are immediate data sources
6. **Check history** - Prevent duplicate tool calls with explicit instructions
7. **Test empty cases** - Handle zero-match scenarios gracefully
8. **Audit everything** - Structured outputs enable full traceability

## Scaling Guidance

### State Size Limits
- Keep state objects **under 1MB** total — large states slow down block transitions
- Avoid storing raw document text in state — extract only structured fields
- For large arrays (>500 items), consider batching into multiple For Each loops

### Large Loop Performance
| Items in Loop | Expected Behavior | Recommendation |
|---------------|-------------------|----------------|
| 1-50 | Fast, no issues | Standard pattern |
| 50-200 | Noticeable latency | Monitor total runtime |
| 200-500 | Slow, possible timeouts | Batch into sub-arrays |
| 500+ | Risk of failure | Split into multiple workflows |

### State Cleanup
```javascript
// After a loop completes, clear ephemeral loop variables to reduce state size
{
  "current_item": null,
  "current_item_context": null,
  "current_iteration_results": null
}
```

## Error Recovery Patterns

### Try-Catch in For Each Loops

When one item in a For Each loop fails, the entire loop fails by default. To handle gracefully:

```javascript
// In the LLM analysis block prompt:
"If you cannot analyze this item due to missing data or ambiguity:
- Set status to 'SKIPPED'
- Set reason to a brief explanation
- Do NOT raise an error
- Return the item with SKIPPED status so the loop continues"
```

### Accumulate Errors Separately

```javascript
// In set_state_entries at loop end:
{
  "all_results": [
    ...(state.all_results || []),
    ...state.current_iteration_results.filter(r => r.status !== "SKIPPED")
  ],
  "all_errors": [
    ...(state.all_errors || []),
    ...state.current_iteration_results.filter(r => r.status === "SKIPPED")
  ]
}
```

### Fallback on Empty Dataset Lookup

```
// In LLM prompt after dataset lookup:
"If state.existing_records is empty ([]):
- Do NOT hallucinate records
- Mark all items as NEW (no existing coverage)
- Proceed with analysis using only the input document"
```

## Multi-Workflow Orchestration

### Chaining Agent Workflows

Use scenarios to chain multiple structured agent workflows:

```python
from dataiku.scenario import Scenario

s = Scenario()

# Workflow 1: Parse and classify documents
s.build_dataset("parsed_documents")

# Workflow 2: Gap analysis (depends on workflow 1 output)
s.build_dataset("gap_analysis_results")

# Workflow 3: Generate reports (depends on workflow 2)
s.build_dataset("final_reports")
```

### Passing State Between Workflows

Since each workflow has independent state, pass data via datasets:

```
Workflow 1 (Parse) -> Emit Output -> Dataset A
                                       |
Workflow 2 (Analyze) <- Read Dataset A as input
                     -> Emit Output -> Dataset B
                                       |
Workflow 3 (Report) <- Read Dataset B as input
```

### Orchestration Patterns

| Pattern | Structure | Use When |
|---------|-----------|----------|
| **Sequential** | A -> B -> C | Each workflow depends on previous output |
| **Fan-out** | A -> B, A -> C | Same input, independent analyses |
| **Fan-in** | B -> D, C -> D | Merge multiple workflow outputs |
| **Conditional** | A -> if(x) B else C | Route based on classification |
