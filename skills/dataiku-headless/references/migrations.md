---
name: migrations
description: Translate third-party workflow logic into runnable Dataiku flows. Shared migration workflow and validation contract for source guides.
---

# Migrations

Follow Plan → Build → Validate → Document and Cleanup. Read [SKILL.md](../SKILL.md)
for permissions and [Cobuild](cobuild.md) before delegation. Source guides add
parsing, semantics and deliverables; a caller may add operator gates and run
records. Load shared guidance once and source details only when relevant.

## Source and workspace

Use a caller-supplied source guide when present; otherwise load
[Excel](migrations/sources/excel/excel.md) for Excel. Keep the active guide's
deliverables, including the Excel guide's per-sheet datasets and overview webapp.
For other sources without a guide, inspect the supplied logic best-effort and
report gaps; never invent a source-guide path.

Use the caller's workspace convention or, by default,
`<bundle_dir>/migration_v<n>/`, with the first unused number. Resolve this once
and use that run directory for every plan and evidence file below. Resume in the
existing run directory; a new attempt gets a new number.

## Migration invariants

- **Visual only unless explicitly authorized.** Code recipes require user approval
  for that transformation. Difficulty, speed or a Cobuild refusal is not an
  exception. Use [native recipe capabilities](recipes.md) and applicable
  source-guide compositions first; medians, quantiles and modes can compose from
  Window ranking and TopN. Correct unrequested code as a failed unit.
- **Original logical inputs, equivalent grain.** Upload original source inputs,
  never locally cleaned, filtered, joined, aggregated, ranked or final substitutes.
  Implement derived logic inside Dataiku. Cached outputs are parity references,
  never inputs to delivered transformations. Preserve the supported input domain;
  sample values, sizes and iteration counts are not implementation bounds.
- **Resolve source authority.** Classify non-obvious constructs as `derivable`
  (implement the rule), `hand-authored` (preserve values and document), or
  `needs-human-input` (ask, never guess). Approximations or reduced domains require
  explicit approval even when fixtures match. Missing source-engine access or
  reference values limits parity evidence, not the ability to implement logic.
- **Keep the processing engine.** Choose a writable target connection; Sync source
  landings onto it before processing and keep intermediates there. Include the
  connection in briefs. Where push-down matters, verify recipe engines and correct
  demotions, including those caused by one non-translatable Prepare step.
- **Consolidate equivalent operations.** Preserve semantics and required/reused
  outputs, not source step boundaries. Fold compatible filters, computed columns,
  core actions and output controls into native recipes. Keep a split for an actual
  correctness, output, engine or performance constraint. Recipe counts describe
  the design; no compression ratio is an acceptance threshold.
- **Preserve source names and time semantics.** Keep dataset names/case and ordered
  columns. A collapsed chain takes its last source output's name; a necessary
  new intermediate uses the nearest source name plus a suffix. Recipe names state
  the transformation in the delivery language. Document engine-required renames.
  Source now-functions stay live: restore temporary historical as-of pins and
  re-verify live behavior.
- **Protect valid work.** Clean up migration-created failed, superseded, orphaned
  and temporary parity assets after verifying replacement and deletion impacts.
  Preserve valid inputs and completed units of blocked branches. Pre-existing
  assets and approved deliverables need explicit deletion approval. Follow
  Cobuild's exact-turn confirmation protocol; never expand cleanup scope.

## Plan

Inspect the selected instance, target project if existing, candidate connections
and source bundle before writes. Resolve the requested project key; for a new
project without a specified key, choose a sensible unused key. Do not create a
project for a planning check.
Use `test_connection` only to diagnose connectivity. Source helpers are optional:
inspect purpose/dependencies, select only those needed and adapt them to the bundle.

Inventory the active source steps, inputs, outputs and business intent before
designing. Read notes, comments, annotations and descriptions. Identify physical
input leaves, shared intermediates and terminal outputs. Select the canonical
production implementation when alternatives exist, record the others as skipped
and present that choice before building. Keep the inventory in the migration plan
unless another consumer needs a separate `inventory.md`.

| Working file | Required content |
|---|---|
| `migration_plan.md` | Business purpose; source inventory; input/output contracts; source steps → units/recipe families; target engine, grain, ordered schemas, native methods, decisions, open questions and required surfaces |
| `validation_plan.md` | Input lineage; business logic; every output's ordered schema/types, cardinality and boundary checks; reference provenance/scope, parity method/tolerances; parameter/time probes and restoration |
| `documentation_and_cleanup_plan.md` | Migration-owned versus pre-existing assets; project/object descriptions, stage zones, wiki and column dictionary; cleanup impacts; required orchestration and delivery evidence |

Link shared contracts instead of copying them. Read a source's relevant construct
guide before planning it. Record distinguishing checks and applicable native
methods, not routine payload internals. Consult Cobuild read-only during Plan only
for an unresolved capability question that could materially change scope, engine
or recipe choice; a suggested answer is not execution evidence.

Inventory reference outputs during Plan, with generating source version, inputs,
parameters and completeness. Keep expected values inline when small, otherwise in
a local file per output with row count. Resolve conflicts with source configuration
explicitly; do not tune logic to fit an inapplicable snapshot. When input rows are
absent, a planned synthetic substitute stays at the logical leaves, is labeled in
the wiki and supports only the stated structural/behavioral checks, never production
parity. Never synthesize intermediates or precomputed answers.

Create a scenario when source orchestration requires it or the operator requests
a reusable rebuild; otherwise build outputs directly. Zones or an export alone do
not require a scenario. Record required variables, ordering, build modes, partitions,
history/existence rules, exports and schedule (delivered inactive).

Present inventory, plan, descriptive recipe counts and open questions once.
Interactive runs obtain plan confirmation at the caller's gate; an inventory above
20 steps alone does not add a checkpoint. Existing scoped authorization applies.
Unattended runs record the plan and continue authorized work without a routine
approval pause, but unresolved `needs-human-input` dependencies remain blocked.
Do not build dependent units until required decisions are resolved.

## Build

Create or reuse only the authorized project; read `get_project_overview`. Reuse a
matching Cobuild conversation or open one when needed. Bootstrap true source inputs
through documented tools, then verify schema and raw cells. Delegate retyping and
format changes. Preserve formatted identifiers and intentional strings; genuinely
numeric sequence keys may stay numeric.

Delegate one independently verifiable functional unit, possibly several related
recipes, per turn. Include source step IDs, transformation, exact inputs/outputs,
connection, grain, ordered columns/types, row-count or duplicate rules, applicable
native method, distinguishing values/invariants and earlier objects out of scope.
Request short replies naming changed objects, claimed counts and incomplete work.
Native DSS read-back is evidence, not automatically accepted Cobuild edit grammar;
follow the active guide's documented payload exceptions.

Settle through [Cobuild](cobuild.md) and independently verify before dependent work.
Retain exact conversation/turn IDs; recover status after interruption and never
resend a pending write. When a host yields a running exec cell, wait on it first,
then poll any returned `queued`/`in_progress` turn. Prefer supported waits up to
60 seconds, with independent work between waits. A local timeout is not failure;
continue until an outcome or actual blocker, not a promise to check later. Follow
[jobs](jobs.md) and run IDs for pending builds/scenarios.

Select evidence for the contract, batch independent reads, and reuse it while unchanged:

- `get_dataset_sample`: ordered schema and actual values, not full-table parity.
- `get_dataset_info`: additional metadata/connection only when needed.
- `get_dataset_profile`: count/null/distribution checks; exact counts require a
  sufficient bound and `truncated: false`. Cached `get_dataset_metrics` is not
  fresh count proof.
- `get_flow_graph`: changed dependencies; `get_recipe_settings` or a read-only
  Cobuild turn for relevant engine/settings checks.
- Failed build: `list_jobs` then `get_job_log`. SUCCESS can hide discarded bad
  rows (`failedRows`) or skipped recipes; read affected outputs and generated files.

A saved surface is not proof it works: apply the active source/feature guide's
checks to dashboards, charts, apps and exports, including after later changes.
Keep unit/object/count/turn/retry evidence in `build_log.md` or the plan, give
concise progress and continue the next authorized unit in the same turn.

On failure, distinguish source-contract mistakes, ingestion, edit rejection,
engine failure and refusal using actual errors, logs and retained objects.
Try a materially different applicable documented alternative on the same
conversation. If none remains, report expected/actual, operation/error, retained
work, alternatives and the needed decision. No unlimited retries, repeated rejected
payloads, unrequested code, sample-sized unrolling or destructive restart.
Attribute a limitation to DSS/version only with evidence.

Inspect the changed graph for redundancy or superseded nodes. Rewrite only actual
candidates or requested optimization; record the decision and prove replacements
before deletion. With no candidate, proceed without an additional exhaustive pass.

## Validate

Reconcile inventory, recipe read-back, lineage and every required output with the
approved validation plan. Outputs must derive from original logical inputs through
Dataiku recipes, without unrequested code or cached-answer dependencies. Record
genuine corrections to source authority; do not rewrite the contract to fit the
build. Empty output is valid only when the source permits it; unreadable data is
not a pass.

Default to a local full export comparison for applicable references. Compare ordered
names/types and every row/column at output entity/period grain, including duplicates
and extra rows. Verify key uniqueness before keyed comparison; otherwise compare
row multisets. Use contract-derived numeric/date normalization. Totals can hide
offsetting errors: inspect per-entity signed differences. Partial references support
only documented checks. Samples and self-written source reimplementations do not
prove parity. Without a reference, check schemas, source invariants, boundaries and
target execution and state that scope.

Use in-Dataiku parity when requested as a deliverable, local disk/memory limits
require it, or export loses a required distinction such as null versus empty string.
Keep references separate from delivered logic; delete temporary parity assets after
recording evidence. Synthetic runs need real-input revalidation before production
parity claims. Record results/deviations in `validation_report.md`.

Correct failures and recheck affected descendants while evidence supports a next
action. Reuse unaffected evidence only while relevant inputs/settings are unchanged.
Unresolved required checks mean partial/blocked, never accepted or completed.

## Document and Cleanup

Prepare required documentation and authorized cleanup before final acceptance.
Do not repeat work merely to enter a phase. After any required scenario or final
rebuild, settle jobs and re-read affected required outputs with applicable parity.

- Describe business purpose in project short/long descriptions and wiki home.
  Describe every migration-owned source, intermediate, recipe, zone and required
  surface: grain, rule and use. Dataset field: `description`; recipe/zone field:
  `shortDesc` (read responses: `short_description`). Project content describes
  objects in the delivery language, without implementation-agent terminology.
- Zone every migration-created Flow asset by stage/function. Reuse the undeletable
  Default as the first stage with distinct zone colors; preserve existing project
  organization. Default membership is implicit, so empty `items` proves nothing.
  Enable zone descriptions through [project settings](projects/settings.md) and
  verify the read-back.
- Wiki: plans, source→recipe→output mapping, validation results, deviations,
  final-output column dictionary and applicable rebuild runbook. Keep column
  documentation here, not in propagated dataset schemas. Use native object links
  such as `[clean_customers](recipe:clean_customers)`.
- Perform cleanup under the invariants and Cobuild confirmation protocol. Prove
  replacement schema/values and check impacts before deleting originals; record
  deleted assets and keep the ownership inventory current.

Save `documentation_evidence.md` with enumerated ownership, displayed descriptions,
zone placement, wiki and required surfaces. Completion requires that inventory,
validation evidence and final execution evidence (including jobs for required
scenarios), never the Cobuild report alone. Run any source-required finish check
once for this state; do not precede it with a duplicate audit. Fix required failures;
warnings warrant changes only for unmet contract obligations. Report inherited
findings separately without claiming a clean project or expanding scope.

A prose edit needs documentation read-back; a data/schema/storage change invalidates
affected output/parity evidence; deletion needs dependency/surface checks. Use
targeted checks after local fixes, not another full build by default. Follow any
caller acceptance/closing gates; hand off project URL, evidence, delivered surfaces,
deviations and unresolved limits.
