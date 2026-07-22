---
name: data-quality
description: Understand and inspect Dataiku Data Quality rules and results. Use when an agent must discover existing rules, interpret quality outcomes, or gather grounded context before asking Cobuild to modify or create a rule.
---

# Data Quality

Use this guide to understand and inspect Data Quality rules, status, and outcomes for a dataset.

## Data Quality Concepts

Data Quality rules are dataset-level checks. They are distinct from legacy metrics/checks and local dataset profiling. A rule can evaluate completeness, validity, uniqueness, distribution, schema, drift, or a custom condition.

Rule configuration, the dataset's overall quality status, a rule's latest result, and rule-result history are distinct. A configured rule may have no result when it has not been computed for the relevant partition. A disabled rule remains configured but is ignored during computation and status evaluation.

Rule outcomes can include `OK`, `WARNING`, `ERROR`, and `EMPTY`. A warning generally represents a soft-threshold signal, while an error represents a hard-threshold failure and can affect builds when the rule runs automatically after a dataset build.

Drift rules compare current results with a historical baseline. A new drift rule may not have enough history to produce a meaningful result.

Read [Rule Types](./data-quality/rule-types.md) when interpreting an existing rule type or preparing a Data Quality request for Cobuild.

## Workflow

1. Use `./datasets.md` to inspect the dataset's schema, partitions, and relevant context when rule interpretation depends on them.
2. Use `list_data_quality_rules` to discover the dataset's configured rules.
3. Use `get_data_quality_status` to inspect the current overall quality status.
4. Use `get_data_quality_rule`, `get_data_quality_rule_results`, and `get_data_quality_rule_history` for rule-specific configuration, latest outcomes, and trends.
5. Route Data Quality rule creation, edits, computation, and deletion through `./cobuild.md`.

## Preferred Tools

- `list_data_quality_rules`
- `get_data_quality_status`
- `get_data_quality_rule`
- `get_data_quality_rule_results`
- `get_data_quality_rule_history`

## Safety Rules

- Interpret results in the relevant partition and dataset context; an absent result is not a passing result.
- Prefer built-in rule types over custom Python checks when preparing a Cobuild request.
