---
name: agent-reviews
description: Create, configure, and run Dataiku DSS Agent Reviews — objects that evaluate an agent's behaviour across a set of test queries using named evaluation traits.
---

# Agent Review Operations

Use Dataiku MCP tools to manage DSS Agent Reviews. An agent review links a DSS agent to a set of **traits** (evaluation criteria) and **tests** (input queries), then executes **runs** that drive each test through the agent and score the responses against each trait.

## Object Hierarchy

```
Agent Review
├── Traits   — named evaluation dimensions (e.g. "Factual accuracy", "Tone")
├── Tests    — input queries with optional reference answers and expectations
└── Runs     — executions of tests; each run → Results → per-test, per-trait outcomes
```

## Execution Pattern

For inspection, use the tool table below — list first, then get. Always call `get_agent_review` before mutating (traits, linked agent, name).

**Creating a review:**
1. `list_agents` to find the agent ID.
2. `create_agent_review` with a name and optional `agent_id` and `traits`.
3. `create_agent_review_test` — one call per test query.
4. `perform_agent_review_run` with `wait_for_completion=true` for interactive feedback.

**Updating traits:**
1. `get_agent_review` — read the current traits list.
2. `update_agent_review` with the complete new traits list. Traits are **full-replace**; include unchanged traits or they will be dropped.

## Tool Reference

| Goal | Tool |
| --- | --- |
| List all reviews in a project | `list_agent_reviews` |
| Read review config (traits, linked agent) | `get_agent_review` |
| Create a new review | `create_agent_review` |
| Update name, linked agent, or traits | `update_agent_review` |
| Delete a review | `delete_agent_review` |
| List tests in a review | `list_agent_review_tests` |
| Add a test query | `create_agent_review_test` |
| Edit a test's query, reference answer, or expectations | `update_agent_review_test` |
| Delete a test | `delete_agent_review_test` |
| Execute a run (all or a subset of tests) | `perform_agent_review_run` |
| List past runs | `list_agent_review_runs` |
| Read per-test, per-trait outcomes for a run | `get_agent_review_run_results` |

## Key Concepts

**Traits** are LLM-as-judge evaluators — each one computes a PASS/FAIL outcome for a test result. Each trait has:
- `name` — label shown in results
- `description` — what the trait means
- `criteria` — the prompt/instructions the evaluator LLM uses to score the response
- `enabled` — disabled traits are ignored during runs
- `needsReference` — set `true` when the trait compares the response against a reference answer
- `needsExpectations` — set `true` when the trait checks against free-text expectations per test
- `llmId` — LLM for this trait's evaluator. Always set explicitly; if omitted and the instance has no default GenAI Evaluation LLM, runs will fail. Use `list_llms` to discover valid IDs.

When creating or updating traits, pass a full list to `update_agent_review`. Each trait dict: `{name, description, criteria, enabled, needsReference, needsExpectations, llmId}`. For existing traits, include their DSS-assigned `id` so DSS preserves them; new traits omit `id` and DSS assigns one on save. Do not invent IDs.

**Tests** are the inputs the agent receives. Each test has:
- `query` — the user message sent to the agent (required)
- `referenceAnswer` — expected answer, required when any trait has `needsReference=true`
- `expectations` — free-text behavioral expectations, required when any trait has `needsExpectations=true`

**Runs** execute the test set. Each test is executed `nb_executions` times per run (configured on the review) to account for agent non-determinism; a single test can produce multiple execution results. `perform_agent_review_run` blocks until completion when `wait_for_completion=true`. For large test sets, consider `wait_for_completion=false` and poll via `list_agent_review_runs`.

**Results** are per-test, per-trait. `get_agent_review_run_results` returns a summary (PASS/FAIL/total counts) plus each result's `status` and `justification`. `trait_status_per_trait_id` reflects the **final** status — human overrides always win over AI evaluation. Human reviews and trait overrides are not covered by the current MCP tools; use the DSS UI for HITL review.

## Key Behaviors

- **Agent ID format**: Pass the bare `list_agents` ID as-is (e.g. `jdcefvxV`); DSS expects it bare in `agentSmartId`, no project-key prefix.
- **Traits are full-replace**: `update_agent_review` replaces the entire traits list — always include unchanged traits or they will be dropped.
- **Run subset**: Pass `test_ids` to `perform_agent_review_run` to run only specific tests; omit to run all.
- **`nb_executions`**: Each test runs this many times per run (configured on the review). Multiple execution results per test is expected, not an error.

## Safety Rules

- Delete a review or test only after the user explicitly confirms.
- Always discover review IDs, test IDs, and agent smart IDs via tools.
- `perform_agent_review_run` invokes the linked agent against real LLM calls; confirm with the user before running large test sets.
