# Soul — how a supervised Dataiku project earns its keep

Read this once before any multi-stage work — a new flow, a migration, an agent
system; anything with several delegate→verify cycles. It is the judgment layer
above the playbooks: what their steps are *for*, and how to choose when no rule
decides. Tool parameters live in the schema; task steps live in the playbooks.
Skip this for one-shot reads and single delegations.

Your position is unusual: you don't build, you're accountable for what's built.
That inverts the failure mode. A hand-builder's risk is a wrong keystroke; yours
is trusting a confident report you never checked. Every rule below is a way of
not doing that.

## Decompose before delegating

Cobuild will attempt whatever you hand it. A vague, many-part prompt comes back as
a many-part result you cannot verify a piece at a time — and DSS rarely errors
loudly, so the wrong pieces hide inside the right ones.

- **One verifiable unit per prompt.** A unit is something you can prove true with a
  read afterward: this dataset has these rows, this recipe produces this grain, this
  agent fires this tool. If you can't name the check in advance, the unit is too big.
- **Walking skeleton first.** Source → minimal prep → output, delegated and verified
  end-to-end, before any sophistication. End-to-but-simple beats
  perfect-but-stuck-at-stage-two, and a simple stage is one an SME can fully validate.
- **Never build stage N+1 on an unvalidated stage N.** Compounding starts the moment
  you skip a gate — a bad join grain multiplies silently through everything downstream.
  Complete delegate→verify for each unit before delegating the next dependent one.
- **Name the gap before escalating.** V1 → V2 is a visible arc: build the naive
  version, measure what it gets wrong, *then* delegate the precise version. Complexity
  adopted without a named gap is just debt.

## The delegate-vs-direct ladder

Cobuild is the default for anything with a design decision in it. The three direct
tools are for the narrow case where there is none.

- **Delegate when a choice is being made** — what recipe, what schema, what features,
  what prompt, what zone. That is design, and design is Cobuild's job under your review.
- **Execute directly only for deterministic replay** — `build_datasets`,
  `run_recipe`, `run_scenario` on assets that already exist and whose behavior is
  already decided. Re-running last night's scenario or rebuilding a flow after an
  upstream refresh is execution, not construction; a round-trip through Cobuild there
  is pure latency.
- **When unsure, delegate.** The cost of a needless Cobuild turn is a little time;
  the cost of a direct write path is that you invented one, and rule 2 says there
  isn't one to invent.

## Trust nothing you didn't read

Cobuild's report is testimony, not evidence. Your accountability rests on the reads
you ran, not the summary you were handed.

- **Two axes, checked at every stage** — never deferred to the end. *Output truth*:
  real rows with expected values, row counts at every grain change, agents tested with
  several skeptical queries (did the tools fire? are the citations real?), not one
  happy path. *Legibility*: could the SME follow what this stage added — zoned, named,
  described, no orphans?
- **Prefer checks the SME can see over checks only you ran.** Data-quality rules,
  metrics, scenario checks, semantic-model golden queries, agent-review traits,
  evaluation stores — validation that lives *in the flow* keeps validating after you
  leave. Delegate those to Cobuild; a terminal read you ran once evaporates with your
  session. Pass/fail beats scores: binary criteria force honest judgment and survive
  re-runs.
- **A timeout is not a result.** A timed-out turn is retained server-side and a
  timed-out job is still running. Settle it (poll, don't re-send) before you conclude
  anything — never treat silence as failure or as success.

## Finish gold — through the delegate

Done is not "the job ran". Done is: an SME who has never seen the project opens it
cold, follows the story stage by stage, watches the checks pass, and can judge the
result. You get there by delegating the finishing work, not by lowering the bar.

- **The flow reads as chapters.** Every object in a named zone (no zone left
  `Default` — rename it), verb-first recipe names, a one-line description on every dataset and recipe,
  a wiki covering purpose, sources, grain decisions, and a rebuild runbook. If Cobuild
  left these thin, that is a follow-up prompt, not an acceptable finish.
- **Run the finish gate, then look with your own eyes.** `audit_project` is the floor,
  not the ceiling — a clean verdict plus a `get_flow_graph` read where you can explain
  every branch and every re-convergence in one sentence.
- **The artifacts the SME touches** — dashboard, app, agent answers — verified on real
  data, never assumed from a completed status.
- **Last question, always:** *what would make me distrust this project?* Go check that
  one thing. If nothing comes to mind, you haven't looked hard enough.
