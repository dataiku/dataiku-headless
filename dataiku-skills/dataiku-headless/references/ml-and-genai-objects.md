# ML and GenAI objects

What a supervisor needs to reference ML and GenAI objects in a Cobuild prompt and
to read their results critically. Object identity and read tools are in
`object-model.md`; recipe selection is in `recipe-families.md`. This file is the
judgment: how to design the ask and what to distrust in the result.

**No object here has a direct deep-read tool.** You discover them with
`list_ml_analyses`, `list_saved_models`, `list_agents`, and `list_llms`, and you
inspect their internals — analysis settings, model details, KB config, agent
wiring, review traits — by asking Cobuild in a **read-only turn**
(`allow_edit_project=false`) or by reading the flow artifacts they produce
(evaluation stores, metrics datasets, scored outputs). "Inspect its settings"
below always means one of those two paths, never a direct settings tool.

## Machine learning

Interpret every model against its business objective, validation design, baseline,
and source-data quality — never one metric in isolation. Inspect the source dataset
before requesting or trusting ML work. Never claim causation from a prediction or
clustering model.

**Design the ask by task type, and raise the red flags:**

- **Prediction** (classify / regress a known target). Pick the target from the
  decision the model supports; reject identifiers, row numbers, target proxies, and
  features unavailable at scoring time. Validate on a split that mirrors future
  scoring. *Red flags:* high accuracy but poor minority-class recall; a feature that
  encodes the target or a post-outcome event; train ≫ validation; near-perfect
  performance on a non-trivial problem; too few rows to validate.
- **Clustering** (segment without a target). Value is stable, distinguishable,
  actionable segments — not an internal score. Scale features before distance-based
  methods. *Red flags:* a cluster that is mostly an id or location code; one cluster
  holding almost everything; segments that flip under minor preprocessing changes.
- **Causal prediction** (effect of a treatment). Name treatment, outcome, and
  pre-treatment confounders; exclude anything caused by the treatment. Needs overlap
  between treated and untreated across confounder values. *Red flags:* treatment after
  the outcome; a feature measured after treatment; little treated/untreated overlap;
  a request that reads predictive feature importance as causal evidence.
- **Time-series forecasting** (predict along a time axis). Validate chronologically —
  random splits leak the future. Name the time column, target(s), series ids,
  horizon, and cadence. *Red flags:* validation using post-cutoff information; a
  horizon longer than the history supports; unresolved gaps/duplicates/frequency
  changes; comparison only against other complex models, never a naive baseline.

## LLMs, Knowledge Banks, RAG

- An **LLM**'s available purposes (completion, embedding, rerank, image) decide
  whether it fits a task — check before naming it in a prompt.
- A **Knowledge Bank** stores indexed content; its config sets the embedding model,
  vector-store behavior, metadata schema, and filtering. Inspect its settings before
  interpreting search results or requesting a retrieval change.
- A **Retrieval-Augmented LLM** binds an LLM to a Knowledge Bank with retrieval
  settings to ground responses. Reproducible GenAI *flow steps* that create/populate
  a Knowledge Bank are recipes (`recipe-families.md`), not KB-object edits.

## Agents

Pick the simplest agent type that fits, and escalate on evidence:

- **Simple** (`TOOLS_USING_AGENT`) — a single ReAct loop; conversation history is its
  only memory, the LLM decides when to stop. Tool descriptions
  (`additionalDescriptionForLLM`) are the primary signal for correct tool selection.
- **Structured** (`STRUCTURED_AGENT`) — a block graph, for deterministic branching,
  parallelism, explicit memory, quality loops, or guaranteed pre/post-processing.
  Memory has three layers: **state** (whole conversation, persists across turns),
  **scratchpad** (current turn, isolated per FOR_EACH/PARALLEL branch), and
  **conversation history** (per LLM block). Cobuild owns the block wiring; you review
  it.
- **Code** (`PYTHON_AGENT`) — a custom Python class, only when simple and structured
  cannot meet the need (custom streaming, multimodal, external SDK, bespoke control).

**Agent tools** are project-level objects referenced by stable id. Use
`requireHumanApproval: true` for consequential external actions (messaging,
modifying production data); those tools cannot run inside FOR_EACH or PARALLEL
blocks, and parallel branches racing on the same state key is a real bug. Vague tool
descriptions, overly broad dataset access, and missing approval requirements are the
common sources of unsafe agent behavior — flag them when you review.

## Agent review — proving an agent works

An **Agent Review** evaluates one agent against test queries and named **traits**,
over repeated **runs**. Inspect the linked agent and the trait definitions before
reading a result: the same response passes or fails depending on the trait's
criteria, and a trait may require the test's reference answer or expectations.
Compare repeated runs to expose non-deterministic behavior — inconsistent outcomes
are agent variability, not tooling error. Write traits as pass/fail, and prefer an
agent review living in the project over a one-off manual test you ran once
(`../soul.md` doctrine 3).
