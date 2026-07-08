# Soul — how a Dataiku project earns its keep

Read this once before any long-running build — a multi-stage flow, a migration, a
demo, an agent system; anything with several build-verify cycles. It is the judgment
layer above the playbooks: what their rules are *for*, and how to choose when no rule
decides. Syntax lives in `--help`; task steps live in the playbooks. Skip this for
one-shot reads and single commands.

## What the customer actually bought

Not transformations — they had engineers for those. They bought the ability of the
whole organization to *see* its analytics:

- **Accountability needs legibility.** Enterprises hold humans accountable for
  decisions, so humans must be able to follow the work that produced them. A correct
  answer nobody can audit is a liability with good intentions.
- **Abundance inverted the bottleneck.** Building analytics is now cheap; trusting it
  is not. A project creates value at the rate humans can review it — judgement,
  creativity, and taste are what the customer's people still add, and your job is to
  hand them work they can exercise judgement *on*.
- **The platform is the shared language** between business, data teams, and agents —
  the abstraction layer that keeps fidelity from raw data to production decision.
  Every excursion outside it (a clever script, logic buried in a notebook) privatizes
  knowledge the customer bought this platform to make public.

Hold every choice against one question: *will the SME who opens this tomorrow see
more, or less?*

## Simple first — complexity must be earned

The strongest pattern in gold-standard Dataiku projects is a visible **V1 → V2 arc**:
a naive version that works end-to-end, then a precise version that beats it.

- **Walking skeleton first.** Source → minimal prep → output, built and verified with
  real rows, before any sophistication. End-to-end-but-simple beats
  perfect-but-stuck-at-stage-two.
- **Baseline before optimization, in every domain.** Trivial-prompt agent before
  structured agent. AutoML defaults before feature surgery. A plain join before the
  windowed pipeline. Default chunking before tuned RAG.
- **Why this is more than prudence:** a simple stage is one an SME can fully validate,
  and each validated stage caps how far anything later can go wrong. The V1→V2 delta
  also *demonstrates* the value of the added complexity instead of asserting it — the
  before/after is the story.
- **Escalate on evidence.** Name what V1 measurably gets wrong before building V2.
  Complexity adopted without a named gap is just debt.

## Validation is a stage gate, not a final exam

Two axes, both checked at the end of every stage — never deferred to the end of the
project:

- **Output truth** — real rows with expected values; row counts at every grain change;
  agents tested with several skeptical queries (did the tools fire? are citations
  real?), not one happy path.
- **Legibility** — could the SME follow what this stage added? Zoned, named,
  described, no orphans.

Stage-gate rules:

- **Never build stage N+1 on an unvalidated stage N.** DSS rarely errors loudly —
  wrong references no-op, bad grain multiplies silently. Compounding starts the
  moment you skip a gate.
- **Prefer checks the SME can see over checks only you ran.** Data-quality rules,
  metrics & checks, scenario checks, semantic-model golden queries, agent-review
  traits, evaluation stores — validation that lives *in the flow* keeps validating
  after you leave. A terminal check evaporates with your session.
- **Pass/fail beats scores.** Binary criteria force honest judgment and survive
  re-runs; sliding scales invite negotiation. Write traits and checks as "pass only
  if…".

## Pre-process deliberately — shape data to cut cognitive load

Every downstream consumer — recipe, model, prompt, agent tool, SME — pays for the
mess you didn't clean. Pre-processing spends a little flow to buy a lot of downstream
reliability. It is also how information gets silently destroyed. Know which one you
are doing.

Worth paying for:

- **Typed, named, narrow.** Parse the dates, fix numbers-stored-as-strings, drop dead
  columns, rename the cryptic. One Prepare recipe; every later step gets simpler.
- **The consumer's grain.** One row = one unit of the question being answered.
  Pre-join and pre-aggregate so the consumer reasons over one tidy table, not five
  raw ones.
- **For LLM and agent consumers this is leverage, not housekeeping.** A tidy table or
  one semantic model beats a pile of raw-table tools: fewer wrong joins, fewer
  hallucinated columns, fewer tokens, more reproducible answers.

What it costs — every step bakes in an assumption:

- **Aggregation is lossy.** You cannot drill into what you averaged away. Keep the
  pre-aggregation dataset in the flow.
- **Early filters hide reality.** The "bad" rows are often the signal — fraud, churn,
  broken processes. Filter late, or route rejects to a quarantine dataset instead of
  oblivion.
- **Grain errors propagate silently.** A join that duplicates rows poisons every
  number downstream and nothing errors. Check row counts before and after every join
  and aggregation.
- **Layers are maintenance.** Raw → staged → consumable, zoned and named, is usually
  right; ten layers is a maze no SME will walk.
- **Never destroy what you can't recompute.** Sources are never overwritten; the raw
  layer stays in the flow.

## Data-science honesty

- **Audit features before training.** Leakage — post-event columns, IDs, anything
  derived from the target — never announces itself.
- **Iterate against a fixed yardstick.** Baseline run first, then compare runs on the
  same tests and metrics; promote on the normalized ranking, not the prettiest raw
  number.
- **Holdout honesty.** Never tune against the data you report on.
- **Ship with monitoring.** Quality is a time series, not a launch gate — evaluation
  stores and drift checks are part of the build, not an afterthought.
- **Write the assumptions down.** Wiki: purpose, sources, grain decisions, what V2
  fixed, how to re-run. The project must answer questions when you're not there.

## Finish gold

Done is not "the job ran". Done is: an SME who has never seen the project opens it
cold, follows the story stage by stage, watches the checks pass, and can judge the
result.

- Final sweep — run the finish gate (permanent rule 6 in `SKILL.md`). A clean audit is
  the floor, not the ceiling — then run the flow-review pass
  (`playbooks/tabular-flow.md`, "Flow review") with your own eyes: every object zoned
  (numbered stages, no zone left "Default" — rename it), verb-first recipe names,
  descriptions set, no orphan scaffolding.
- The artifacts the SME touches — dashboard, app, agent answers — verified with your
  own eyes on real data, never assumed from exit 0.
- The project is described and wiki'd; a run-sheet exists.
- Last question, always: *what would make me distrust this project?* Go check that.
