# Scenario Authoring Reference

## Domain Conventions

Scenarios are organized into 11 domains under `benchmark/scenarios/<domain>/`:

| Domain | Focus | Typical difficulty |
|--------|-------|-------------------|
| `data_prep` | Visual recipes (filter, join, group, sort, pivot, formula) | easy–medium |
| `dashboard` | Chart insights, tile management, dashboard composition | medium |
| `automation` | Scenarios, triggers, reporters, recipe execution | easy–medium |
| `genai` | Knowledge banks, LLM recipes, RAG pipelines, prompt recipes | medium |
| `data_quality` | DQ rules, failed-row extraction, schema guards | medium |
| `visual_ml` | Train/predict, clustering, deploy-to-flow | medium–hard |
| `structured_agent` | Agent versioning, tool-calling, routing, state management | medium |
| `semantic_layer` | Metrics, entities, relationships, golden queries | medium |
| `migration` | SAS, Alteryx, Excel → DSS rewrite | medium |
| `end_to_end` | Multi-step pipelines combining 2+ domains | hard |
| `cross_project` | Dataset sharing across DSS projects | medium |

When choosing a domain:

- If the task fits one domain cleanly, put it there. `data_prep` is the default for single-recipe visual transformations.
- If the task spans multiple areas (build a pipeline AND schedule it), use `end_to_end`.
- If the task is migrating a specific source tool's workflow, use `migration`.

## Fixture Conventions

Fixtures live in `benchmark/fixtures/`. The `world/` directory contains
deterministically generated datasets (seeded random — see `ground_truth.yaml`).

| Fixture ID | File | Rows | Description |
|------------|------|------|-------------|
| `world/orders` | `orders.csv` | 500 | Order transactions with customer_id, product_id, region, amount, date |
| `world/customers` | `customers.csv` | 100 | Customer master: name, tier, country |
| `world/products` | `products.csv` | 50 | Product catalog: category, unit_price |
| `world/events` | `events.csv` | 1000 | Event log with timestamps, types, user_ids |
| `world/users` | `users.csv` | 200 | User accounts with signup dates, plan types |
| `world/stores` | `stores.csv` | 10 | Store locations with lat/lng, region |
| `world/vendors` | `vendors.csv` | 12 | Vendor records for fuzzy-join scenarios |
| `world/warehouses` | `warehouses.csv` | 3 | Warehouse locations for geo-spatial scenarios |
| `world/room_bookings` | `room_bookings.csv` | 18 | Booking intervals for overlap detection |
| `world/user_sessions` | `user_sessions.csv` | 61 | Session timestamps for gap analysis |

Reference in `task.yaml`:

```yaml
fixtures:
  - world/orders
  - world/customers
```

The runner copies fixture files to `{fixture_dir}/` before setup runs.

### Adding a new fixture

- Add the CSV to `benchmark/fixtures/world/` and update `generate_world.py` (preferred) or commit a static file.
- Add the row count and any known ground-truth aggregations to `benchmark/fixtures/world/ground_truth.yaml`.

## Check Design Patterns

### Schema verification (`has_columns`, `column_is_numeric`)

Check that expected columns exist rather than comparing the full schema — this lets agents add intermediate columns without failing.

### Row count (`min_rows`, `output_rows`)

- `min_rows` — approximate count, good when the agent may compute a slightly different grouping.
- `output_rows` — exact row count + data value verification. Requires `expected_outputs` block and a DSS client connection.

### Flow topology (`flow_shape`)

Validates the recipe graph by matching schema signatures. Use when the prompt constrains the flow structure.

```yaml
expected_flow:
  nodes:
    orders:
      type: source
      schema:
        - {name: order_id, type: string}
    orders_with_customers:
      type: output
      schema:
        - {name: order_id, type: string}
  recipes:
    - type: Join
      inputs: [orders]
      outputs: [orders_with_customers]
  exact_recipe_count: false
```

Key considerations:

- `exact_recipe_count: true` is strict — the agent must produce exactly N recipes. Use when the prompt forbids extra intermediate datasets.
- `exact_recipe_count: false` allows intermediate steps (filter-before-join, etc.). Preferred unless the prompt specifically constrains the flow shape.
- Schema-signature matching is fuzzy: matched by column names and types, not by the agent's names. Keep schema signatures unique enough for the backtracking matcher.

### Data values (`output_rows` with keyed matching)

```yaml
expected_outputs:
  revenue_by_region:
    schema:
      - {name: region, type: string}
      - {name: total_revenue, type: double}
    row_count: 4
    data:
      - {region: East, total_revenue: 11262.18}

checks:
  - run: "dku dataset head revenue_by_region -P {project} -o json"
    assert: output_rows
    columns: [revenue_by_region, region]  # dataset name + key columns
```

Key columns in `check.columns[1:]` control matching:
- No key columns → unordered set matching.
- Key columns → keyed matching (match by keys, compare other fields).
- `ordered: true` in context → positional matching.

Use keyed matching when the agent might produce rows in any order (e.g. Group recipe with unspecified sort order).

### No-code constraint (`no_python_recipes`)

Checks that no Python, R, Shell, PySpark, SparkR, or Spark Scala recipes exist. Use when the prompt asks to stay in the visual flow.

## Testing Scenarios Locally

1. **Validate the solution path** — `uv run python -m benchmark.runner --scenario <id> --validate`
2. **Run the agent** — `uv run python -m benchmark.runner --profile claude_dku_skills --scenario <id> --parallel 1 --verbose`
3. **Inspect the trace** — `cat benchmark/reports/$(ls -t benchmark/reports | head -1)/traces/*.json | python -m json.tool`
4. **Iterate on checks** based on what the agent produced.
5. **Re-validate** after changing checks.
6. **Run with `--no-cleanup`** to inspect the project state in DSS.

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| `exit_code_zero` on a `list` command | Throwaway check dilutes real ones | Remove or fold into a specific assertion |
| Prompt names specific recipe types | Biases toward implementation-shaped solutions | Describe the business outcome, not the recipe type |
| `validation_gaps` for vague wording | Misleads about what the benchmark proves | Fix wording or checks |
| `expected_flow` without `exact_recipe_count: false` | Brittle — filter-before-join fails even with correct result | Set `exact_recipe_count: false` unless prompt constrains intermediate steps |
| Checks only verify existence, not content | Pass with wrong values | Add `output_rows` or `output_schema` + `expected_outputs` |
| Setup uses `dku` commands that don't exist | Scenario can never run | `dku --version` first, or use `dataikuapi` setup commands |
| Dataset name mismatch between prompt and checks | Agent names it one way, checks look for another | Use the same name; harness does not fuzzy-match dataset names |
| Missing `initial_checks` | Harness can't distinguish "never ran" from "couldn't start" | Add `exit_code_nonzero` on expected output dataset |
