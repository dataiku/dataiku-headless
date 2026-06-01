# CLAUDE.md — Benchmark Authoring

This file governs work inside `benchmark/`.

## Mission

The benchmark measures whether an AI assistant can successfully build in
Dataiku DSS. It does **not** measure whether the assistant guessed the
maintainer's preferred CLI command sequence.

When editing scenarios, optimize for one question:

**Would this still be a fair benchmark if the assistant used a different tool
surface or methodology?**

If the answer is no, the scenario is too implementation-shaped.

## Scenario Contract

Each scenario has three separate layers:

1. `task.yaml` `prompt`
2. `task.yaml` `checks`
3. `solution.md`

- `prompt` is the user request shown to the agent.
- `checks` are the machine-checked outcomes that determine the score.
- `solution.md` is a maintainer witness for `--validate`, not the benchmark's
  canonical workflow.

Never let `solution.md` leak into the prompt.

## Scoring & Checks

`checks` is a flat list. The score is the fraction that pass:
`score = checks_passed / total_checks`. A single-check scenario is therefore
0.0 or 1.0; a multi-stage scenario earns partial credit per stage. Strict
success (`passed`) means `score == 1.0`.

This puts the weight on check authoring:

- Each check is one meaningful, roughly equal-weight outcome. For pipeline
  scenarios, that means one check per stage so partial progress shows up.
- Do not pad the denominator with trivial checks (e.g. `exit_code_zero` on a
  `list` command). A throwaway check dilutes every real one.
- Checks are unweighted. If stages are genuinely unequal, raise it rather than
  faking weight by duplicating checks.

## Prompt Rubric

- Write in plausible user voice. It should sound like a real request from a
  Dataiku builder.
- Describe the business outcome and required artifact names, not the exact
  command path.
- Keep the prompt tool-surface agnostic. Do not tell the agent to use `dku`,
  Python API, UI clicks, or a specific internal interface.
- Do not mention verifier commands or harness mechanics in the prompt.
- Do not mention serialized DSS enum names or internal graph tokens such as
  `LLM_REQUEST`, `ROUTING`, `CORE_LOOP`, `STANDARD_REACT`, `ds_modified`, or
  similar implementation details.
- Avoid naming exact recipe types unless that is part of the real user intent.
  Prefer "keep this in the visual flow" over "use a Group recipe then a Pivot
  recipe".
- Keep prompts short. Put benchmark setup in `setup`, not in the prompt, unless
  the user would naturally mention it.
- If a scenario is a migration task, describe the source workflow and target
  business output, not a step-by-step rewrite plan.
- If a scenario is a structured-agent task, describe behavior and branching, not
  block enum trivia.

## Honesty Rules

- If checks only prove object creation, the prompt must not claim runtime
  behavior has been proven.
- If checks only prove existence plus wiring, the prompt must not claim the
  system is production-ready, retrieval-ready, or behaviorally validated.
- If the intended capability is broader than current enforcement, either:
  - narrow the prompt, or
  - keep the broader prompt and record the gap explicitly in `validation_gaps`
    without overstating what a pass means.

Use `validation_gaps` for missing proof, not for sloppy wording.

## Editing Checklist

Before shipping a benchmark scenario change, verify:

1. The prompt sounds like a real builder request.
2. The prompt does not leak tool or verifier details.
3. The checks honestly enforce the acceptance criteria.
4. `validation_gaps` explains any remaining mismatch explicitly.
5. `solution.md` still proves at least one executable path on the live system.
6. The scenario passes `--validate` against a live DSS instance.
7. Always include at least one `initial_checks` entry asserting
   `exit_code_nonzero` on the expected output dataset — without it the harness
   cannot distinguish "agent never ran" from "agent couldn't start".
8. Set `expected_flow.exact_recipe_count: false` unless the prompt explicitly
   constrains intermediate recipe steps.

## References

- [Scenario Authoring](references/scenario-authoring.md) — domains, fixtures,
  check design patterns, testing workflow, common mistakes
