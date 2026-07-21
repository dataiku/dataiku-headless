# ML and GenAI objects

What an agent needs to reference ML and GenAI objects in a Cobuild prompt and
check their results. Object identity and read tools are in `object-model.md`;
recipe selection is in `recipe-families.md`.

**Discover, then deep-read, then verify against artifacts.** Use
`get_project_overview` and the applicable `list_*` tool (`list_ml_analyses`,
`list_saved_models`, `list_agents`, `list_llms`) to obtain ids. Read saved
configuration with `get_object_settings` for `ml_analysis`, `saved_model`,
`evaluation_store`, `knowledge_bank`, `retrieval_augmented_llm`, `agent`,
`agent_tool`, and `agent_review`. Omit `version_id` to discover versions of
an agent or saved model; pass it to isolate one.

Saved settings do not prove runtime behavior. When configuration cannot answer a
runtime question, execute the asset and read the resulting job or run record, or
delegate the check to Cobuild.

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

Open the matching deep reference only when its contract matters:
`objects/agents/simple-agent.md`, `objects/agents/structured-agent.md`, or
`objects/agents/code-agent.md`. Agent-tool types and result shapes are in
`objects/agents/agent-tools.md`.

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
are agent variability, not tooling error. Read the review with
`get_object_settings(object_type="agent_review")`, but do not infer a run outcome
from saved configuration — delegate an actual review run to Cobuild and read its
report.
