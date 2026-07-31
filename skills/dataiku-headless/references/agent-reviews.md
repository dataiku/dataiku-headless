---
name: agent-reviews
description: Understand and inspect Dataiku Agent Reviews. Use when an agent needs to interpret existing reviews or gather grounded context before asking Cobuild to create or modify project assets.
---

# Agent Reviews

Use this guide to understand and inspect Agent Reviews, including their traits, tests, runs, and results.

## Agent Review Concepts

An Agent Review evaluates one Dataiku agent against a set of test queries and named evaluation traits. It provides a repeatable way to assess the agent's behavior, identify weak cases, and compare outcomes across runs.

### Object Model

```text
Agent Review
|- Traits: evaluation criteria, such as factual accuracy or tone
|- Tests: input queries, optionally with reference answers and expectations
`- Runs: executions of the test set, producing per-test, per-trait results
```

### Core Concepts

- **Traits** define how an agent response is evaluated. A trait can require a test's reference answer or free-text expectations.
- **Tests** are the user queries sent to the linked agent. Supply reference answers and expectations when the configured traits require them.
- **Runs** execute the review's tests. A test may be executed multiple times to expose non-deterministic agent behavior.
- **Results** record outcomes for each test and trait, including the evaluator's status and justification. A final result may reflect a human override where one exists.

### Interpretation Notes

- Inspect the linked agent and trait definitions before interpreting a result: the same response can pass or fail depending on the trait's criteria.
- Check that each test provides the inputs required by its traits, especially reference answers and expectations.
- Compare repeated executions of a test when assessing reliability; inconsistent outcomes are evidence of agent variability, not necessarily a tooling error.

## Workflow

1. Use `list_agent_reviews` to discover reviews.
2. Use `get_agent_review` to inspect the review configuration and discover its linked agent. When agent behavior or configuration matters, use `./agents.md` to inspect that agent.
3. Use `list_agent_review_tests` to inspect the test set.
4. Use `list_agent_review_runs` and `get_agent_review_run_results` to inspect outcomes.
5. If the task requires creating, editing, deleting, or executing Agent Reviews, route that work through `./cobuild.md`.

## Preferred Tools

- `list_agent_reviews`
- `get_agent_review`
- `list_agent_review_tests`
- `list_agent_review_runs`
- `get_agent_review_run_results`

## Safety Rules
