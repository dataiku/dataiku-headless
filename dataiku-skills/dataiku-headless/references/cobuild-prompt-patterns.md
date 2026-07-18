# Cobuild prompt patterns

How to write a Cobuild task that comes back proof-carrying — so you can verify it
against your reads instead of trusting a summary. Open this when composing a
delegation in `build-via-cobuild.md`.

## The template

Every non-trivial prompt carries four things:

- **Goal** — the outcome in one sentence, in business terms.
- **Success criteria** — the checks you will run afterward, stated up front so
  Cobuild builds toward them: expected grain, row-count relationship, required
  columns, a validation rule that should exist in the flow.
- **Scope bounds** — what to touch and what to leave alone. Name the target objects;
  forbid unrequested deletions, renames, and code recipes.
- **Named objects** — every dependency by the *exact* name you read
  (`get_project_overview` / `get_flow_graph` / a targeted read), never an assumed one.
  For existing assets, include the configuration and constraints you discovered.

## Steer the response shape

Ask for the shape you want back, and you can check it. Request that Cobuild report
the objects it created/changed, the row counts of outputs, and which validation it
added — a proof-carrying report, not "done". You still verify independently (rule
5), but a well-shaped report tells you exactly what to verify.

## Read-only plan first

For any build with a design decision, send the task once with
`allow_edit_project=false` and ask for the plan — which recipes, which schema, which
zone, which connection. Review it against intent, then re-send with
`allow_edit_project=true` on the same conversation to execute. Cheap insurance
against a confident wrong build.

## Good vs bad prompts

**Bad — vague, unverifiable, unbounded:**
> "Clean up the customer data and build a dashboard."

Cobuild picks the datasets, invents the grain, may drop rows, may add a code
recipe, may delete something — and "done" tells you nothing to check.

**Good — grounded, bounded, proof-shaped:**
> "In project `RETAIL`, build a flow from datasets `orders_raw` and `customers_raw`
> (both read via overview). Goal: one row per customer with lifetime order count and
> total spend. Use visual recipes only. Success: output `customer_ltv` has one row
> per `customer_id` in `customers_raw` (no fan-out), columns `order_count` and
> `total_spend`, and a not-empty DQ rule on `customer_id`. Don't modify or delete
> `orders_raw`/`customers_raw`. Report the recipes created and the output row count."

The difference is not politeness — it's that the good prompt names the checks you'll
run, so the result is falsifiable.

## Grounding rules

- Prefer explicit object names over descriptions Cobuild has to resolve.
- For a change to an existing asset, inspect it first and carry its real config into
  the prompt (see `../playbooks/inspect-and-explain.md`).
- For greenfield work, tell Cobuild which project context to inspect rather than
  assuming it will find the right objects.
- One verifiable unit per prompt; don't batch dependent stages (`../soul.md`
  doctrine 1).
