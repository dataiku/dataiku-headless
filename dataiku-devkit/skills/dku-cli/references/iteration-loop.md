# Agent Iteration Loop (baseline → prompt iter → architectural fix → re-eval)

The canonical 4-stage workflow for shipping a quality-assured DSS agent. This is
what Roland-class customer demos rely on — every step happens through `dku`
verbs, with per-trait diagnostics on each iteration.

## TL;DR

```bash
# 1. Baseline run
dku agent-review run REV --no-wait --name "run-1-baseline" -P PROJ

# 2. Iterate the prompt
dku agent set-prompt AGENT --prompt @v2_prompt.txt --new-version --activate -P PROJ
dku agent-review run REV --no-wait --name "run-2-prompt-v2" -P PROJ

# 3. Architectural fix (e.g. add a tool, swap LLM)
dku agent-tool create new_tool --type Custom_agent_tool_X_Y --params @config.json -P PROJ
dku agent add-tool AGENT --tool new_tool --new-version --activate -P PROJ
dku agent-review run REV --no-wait --name "run-3-with-tool" -P PROJ

# 4. Final re-eval (often a tightened prompt on top of the fix)
dku agent set-prompt AGENT --prompt @v3_prompt.txt --new-version --activate -P PROJ
dku agent-review run REV --no-wait --name "run-4-final" -P PROJ

# Compare across runs
dku agent-review list-runs REV -P PROJ          # capture the 4 run IDs
dku agent-review compare REV --runs RUN_1,RUN_2,RUN_3,RUN_4 -P PROJ
```

The `compare` command produces a trait×run pass-rate matrix — the
demo-ready output that proves the iteration story.

## Per-stage detail

### Stage 1 — Baseline

Establish the starting trait pass-rates. **Don't tune anything yet.** This run
sets the bar everything else is measured against.

```bash
dku agent-review run REV --no-wait --name "run-1-baseline" -P PROJ
# Wait until the run completes:
dku agent-review list-runs REV -P PROJ
# Then pull the per-trait grid:
dku agent-review results REV --run "$RUN_1" --by-trait -P PROJ
```

Inspect `--by-trait` carefully: which traits are already passing? Which are
failing? **Read the justifications** with `--show-justifications -o json` —
those tell you whether the failure is a prompt issue, a missing tool, or a
flat-out wrong agent architecture.

### Stage 2 — Prompt iteration

Cheapest, highest-yield lever. Most "obviously dumb" failures come from a
prompt that under-specifies the output format, tone, or process. Use
`--new-version --activate` so you can roll back if the new prompt regresses:

```bash
dku agent set-prompt AGENT --prompt @v2_prompt.txt --new-version --activate -P PROJ
# Sanity-check before re-running the review (saves 10–30 min):
dku agent test AGENT --query "the toughest failing test query" -P PROJ

dku agent-review run REV --no-wait --name "run-2-prompt-v2" -P PROJ
```

If a trait gets *worse* after prompt iteration (real risk on multi-trait
reviews — fixing tone can degrade accuracy and vice versa), roll back to v1:

```bash
dku agent set-active-version AGENT v1 -P PROJ
```

### Stage 3 — Architectural fix

When prompt iteration plateaus, the agent is missing a capability — typically a
tool. Common moves:

- Add a `VectorStoreSearch` tool when the agent needs domain knowledge.
- Add a `DatasetRowLookup` when the agent needs structured data.
- Add a semantic-model-query plugin tool when the agent needs free-form
  business questions answered. (NB: semantic models REQUIRE SQL-backed entities
  — Filesystem datasets silently fail.)
- Swap the LLM for a stronger one (`set-llm openai:gpt-5o` etc.) if reasoning
  is the bottleneck.

Tools must be wired *and* the agent version must be re-activated:

```bash
dku agent-tool create sm_query \
  --type Custom_agent_tool_semantic-models-lab_semantic-model-query \
  --params '{"semanticModelId":"sm_contracts","activeVersionOnly":true}' -P PROJ

dku agent add-tool AGENT --tool sm_query --new-version --activate -P PROJ

dku agent-review run REV --no-wait --name "run-3-with-tool" -P PROJ
```

### Stage 4 — Re-eval and compare

Often the last stage is a tightened prompt on top of the architectural fix.
Once you've got 3–4 runs, build the comparison matrix:

```bash
dku agent-review compare REV --runs "$RUN_1,$RUN_2,$RUN_3,$RUN_4" -P PROJ
```

Sample output:

```
Trait pass-rate comparison (review_id=contract_intel)
TRAIT              RUN_1_BASELINE     RUN_2_PROMPT_V2    RUN_3_WITH_TOOL    RUN_4_FINAL
Accuracy           6/20 (30%)         11/20 (55%)        17/20 (85%)        19/20 (95%)
Tone               14/20 (70%)        17/20 (85%)        17/20 (85%)        19/20 (95%)
Action_Specified   3/20 (15%)         8/20 (40%)         16/20 (80%)        18/20 (90%)
Citations          0/20 (0%)          0/20 (0%)          18/20 (90%)        19/20 (95%)
```

This is the demo-ready output. Pair with `--show-justifications -o json` from
`results` for the qualitative talking points.

## Gotchas

- **Review runs re-execute the agent fresh per test.** They don't re-score a
  cached `agent_answers` dataset. A slow agent makes the review slow — budget
  10–30 minutes per run for a 20-test review against a semantic-model-query
  agent.
- **Pass-rates can swing on small test sets.** With 20 tests, a single flipped
  test is ±5%. Don't over-interpret a single run; look at the trajectory.
- **Trait justifications can lie.** The LLM judge sometimes invents reasons
  for a FAIL when the rubric is ambiguous. Read 2–3 justifications per failing
  trait per run and refine the criteria if the judge is being inconsistent.
- **`--by-trait` headers come from the review's trait definition.** If the
  review has unnamed traits (e.g. just `traitId` with no `name`), the column
  headers fall back to the trait IDs.

## Why the CLI matters here

The whole point of `dku agent-review compare` is that the iteration story is
*reproducible and demo-able*. Custom Python scripts (`compare_review_runs.py`,
`review_diagnostics.py`) work, but they live in someone's `/tmp` directory and
nobody else can run them. The CLI verbs are the contract.

## Related reading

- `references/agent-patterns.md` — building agents, SVA block graphs, tool
  config
- `references/genai-recipes.md` — `nlp_agent_evaluation` quirks (custom-metric
  JSON envelope, `"""` JSON-escape trap)
- `dataiku` skill's `references/semantic-models.md` — semantic-model SQL-backed
  requirement, splice verbs
