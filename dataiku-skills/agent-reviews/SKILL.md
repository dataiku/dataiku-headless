---
name: agent-reviews
description: Inspect Dataiku DSS Agent Reviews and their runs. Use when an agent must understand existing reviews, tests, or review outcomes before asking Cobuild to create or modify project assets.
---

# Agent Review Inspection

Use this skill to inspect Agent Reviews, tests, runs, and results.

## Workflow

1. Use `list_agent_reviews` to discover reviews.
2. Use `get_agent_review` to inspect review configuration and linked agent context.
3. Use `list_agent_review_tests` to inspect the test set.
4. Use `list_agent_review_runs` and `get_agent_review_run_results` to inspect outcomes.
5. If the task requires creating, editing, deleting, or executing Agent Reviews, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_agent_reviews`
- `get_agent_review`
- `list_agent_review_tests`
- `list_agent_review_runs`
- `get_agent_review_run_results`

## Safety Rules

- Discover review ids and run ids via tools.
- Keep this skill focused on inspection and Cobuild grounding.
