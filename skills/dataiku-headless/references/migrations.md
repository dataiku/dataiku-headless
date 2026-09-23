---
name: migrations
description: Translate business logic from third-party tools (e.g. Alteryx, Tableau Prep, SAS, Excel) into runnable Dataiku flows. Use when user supplies a source bundle and asks to migrate, rebuild, port, or recreate its logic in Dataiku.
---

# Migrations

Follow Plan → Build → Validate → Document and Cleanup; Build and Validate may loop. Read [SKILL.md](../SKILL.md) for permissions and [Cobuild](cobuild.md) before delegation. The source guide adds parsing, semantics, deliverables and phase steps of its own; they are binding. A caller may add operator gates and run records. Load shared guidance once, and source details when relevant.

## Source and workspace

Determine the source platform from the request and bundle. Load the caller's source guide when one is supplied; otherwise load `./migrations/sources/<platform>/<platform>.md` in full when it exists (for example [Excel](migrations/sources/excel/excel.md)), then its routed guides when relevant. Without a source guide, proceed best-effort from the supplied logic and report gaps.

Use the caller's workspace convention or, by default, `<bundle_dir>/migration_v<n>/`, with the first unused number. Resolve this once and use that run directory for every plan and evidence file below. Resume in the existing run directory; a new attempt gets a new number.

## Migration invariants

- **Visual only unless explicitly authorized.** Code recipes require user approval for that transformation. Difficulty, speed or a Cobuild refusal is not an exception. Use [native recipe capabilities](recipes.md) and applicable source-guide compositions first; medians, quantiles and modes can compose from Window ranking and TopN. Correct unrequested code as a failed unit.
- **Original logical inputs, equivalent grain.** Upload original source inputs, never locally cleaned, filtered, joined, aggregated, ranked or final substitutes. Implement derived logic inside Dataiku. Cached outputs are parity references, never inputs to delivered transformations. Preserve the source's behavior across its supported input domain, not just the supplied snapshot. Do not turn observed sample sizes, values, or iteration counts into implementation limits.
- **Resolve source authority.** Classify non-obvious constructs as `derivable` (implement the rule), `hand-authored` (preserve values and document), or `needs-human-input` (ask, never guess). Approximations or reduced domains require explicit approval even when fixtures match. Missing source-engine access or reference values limits parity evidence, not the ability to implement logic.
- **Keep the processing engine.** Choose one writable target connection and keep intermediates there. When a source lands on another connection (for example an upload on filesystem storage while the flow runs on a SQL connection), make the first delegated unit a Sync onto the target before any processing. Include the connection in briefs. Where push-down matters, verify recipe engines and correct demotions, including those caused by one non-translatable Prepare step.
- **Consolidate equivalent operations.** Preserve semantics and required/reused outputs, not source step boundaries. Fold compatible filters, computed columns, core actions and output controls into native recipes. Keep a split for an actual correctness, output, engine or performance constraint. Recipe counts describe the design; no compression ratio is an acceptance threshold.
- **Preserve source names and time semantics.** Keep dataset names/case and ordered columns. A collapsed chain takes its last source output's name; a necessary new intermediate uses the nearest source name plus a suffix. Name each recipe with a verb in the delivery language plus the dataset it produces (`filter_Base_F`, `filtrer_Base_F`), renaming generated `compute_<output>` names. A name with no source counterpart marks a step the plan invented; treat it as a finding. Document engine-required renames. Source now-functions stay live: restore temporary historical as-of pins and re-verify live behavior.
- **Protect valid work.** Clean up migration-created failed, superseded, orphaned and temporary parity assets after verifying replacement and deletion impacts. Preserve valid inputs and completed units of blocked branches. Pre-existing assets and approved deliverables need explicit deletion approval. Follow Cobuild's exact-turn confirmation protocol; never expand cleanup scope.

## Plan

Inspect the selected instance, candidate connections and source bundle before writes; when the target project exists, read `get_project_metadata` and `get_flow_graph`. Resolve the requested project key; for a new project without a specified key, choose a sensible unused key. Do not create a project for a planning check. Use `test_connection` only to diagnose connectivity. Source helpers sit in `migrations/sources/<platform>/helpers/*.py`; discover them with `ls`, and read each first docstring line for purpose, inputs → outputs and dependencies. They are optional: select only those needed and adapt them to the bundle.

Inventory the active source steps, inputs, outputs and business intent before designing, including the role each input plays in that intent. Read notes, comments, annotations and descriptions. Identify physical input leaves, shared intermediates and terminal outputs. Select the canonical production implementation when alternatives exist, record the others as skipped and present that choice before building. Keep the inventory in the migration plan unless another consumer needs a separate `inventory.md`.

| Working file | Required content |
|---|---|
| `migration_plan.md` | Business purpose; source inventory with each input's role; input/output contracts; source steps → units/recipe families; target engine, grain, ordered schemas, native methods, decisions, open questions, required surfaces and the rebuild scenario |
| `validation_plan.md` | Input lineage; business logic; every output's ordered schema/types, cardinality and boundary checks; reference provenance/scope, parity method/tolerances; any temporary time pin and its restoration |
| `documentation_and_cleanup_plan.md` | Migration-owned versus pre-existing assets; project/object descriptions, stage zones, wiki and column dictionary; cleanup impacts; the rebuild scenario run and delivery evidence |

Link shared contracts instead of copying them. Read a source's relevant construct guide before planning it. Record distinguishing checks and applicable native methods, not routine payload internals. Consult Cobuild read-only during Plan only for an unresolved capability question that could materially change scope, engine or recipe choice; a suggested answer is not execution evidence. If the question cannot be resolved within Plan's permissions, record the uncertainty and its impact at the plan gate.

Inventory reference outputs during Plan, with generating source version, inputs, parameters and completeness, and store one local reference file per terminal output. In the validation plan, keep expected values inline when small, otherwise link the file with its row count. When configuration and expected values conflict, resolve which source or version is authoritative; do not tune the workflow to fit cached answers. When input rows are absent, a planned synthetic substitute stays at the logical leaves, is labeled in the wiki and supports only the stated structural/behavioral checks, never production parity. Never synthesize intermediates or precomputed answers.

Every migration delivers a rebuild scenario covering every required output. A single chain built once needs one build step. A program with run parameters, derived variables, loops, history or existence guards gets its driver in source order: variables and their setters, build steps with their modes (non-recursive forced when a variable changes between builds), partitions, history/existence rules and exports. Deliver the source schedule as an inactive trigger.

Present inventory, plan, descriptive recipe counts and open questions once, before creating or changing the project. When someone can answer, wait for their confirmation and ask the open questions there; existing scoped authorization applies. A caller may replace this gate with its own. When no one can respond (an unattended or scheduled run), print the plan and continue to Build without ending the turn on a question. For each open `needs-human-input` item, build what the source does as written, and record the question, that choice and the affected outputs in the plan, the wiki deviations and the final report. Only units that cannot be built as written, and their dependents, stay blocked.

## Build

Create or reuse only the authorized project and read `get_project_metadata`. Reuse a matching Cobuild conversation or open one when needed. Bootstrap true source inputs through documented tools, then verify schema and raw cells. Delegate retyping and format changes. Preserve formatted identifiers and intentional strings; genuinely numeric sequence keys may stay numeric. Place migrated Python or R source per `./project-libraries.md`, and give Cobuild prompts that same destination path.

Delegate one independently verifiable functional unit, possibly several related recipes, per turn. Include source step IDs, transformation, exact inputs/outputs, connection, grain, ordered columns/types, expected row count or duplicate rule, applicable native method, distinguishing values/invariants and earlier objects out of scope. Request short replies naming changed objects, claimed counts and incomplete work. Native DSS read-back is evidence, not automatically accepted Cobuild edit grammar; follow the active guide's documented payload exceptions.

Cardinality is part of the contract. Reproduce the source's duplicate semantics exactly: a lookup or registry that the source writes with duplicates must not be deduplicated, and vice versa. State the expected output row count or the rule ("one row per source row, duplicates preserved") in the brief, and fail the unit on an unexplained count difference.

Settle through [Cobuild](cobuild.md) and independently verify before dependent work. Retain exact conversation/turn IDs. A local timeout or interruption is not a failure: recover the turn's status and never resend a pending write. Follow [jobs](jobs.md) for builds and [scenarios](scenarios.md) for scenario runs. Continue until an outcome or an actual blocker, never ending on a promise to check later.

Select evidence for the contract, batch independent reads, and reuse it while unchanged:

- `get_dataset_sample`: ordered schema and actual values, not full-table parity.
- `get_dataset_info`: additional metadata/connection only when needed.
- `get_dataset_profile`: count/null/distribution checks; exact counts require a sufficient bound and `truncated: false`. Cached `get_dataset_metrics` is not fresh count proof.
- `get_flow_graph`: changed dependencies; `get_recipe_settings` or a read-only Cobuild turn for relevant engine/settings checks.
- Failed build: `list_jobs` then `get_job_log`.

A green status is not row evidence: a job can report SUCCESS after discarding rows that fail a cast (check the log's `failedRows`), and a scenario can succeed after skipping recipes. After every build, obtain fresh row evidence for affected required outputs, with exact counts when the contract requires them, and read generated files back.

A saved surface is not proof it works: apply the active source/feature guide's checks to dashboards, charts, apps and exports, including after later changes. Keep unit/object/count/turn/retry evidence in `build_log.md` or the plan, give concise progress and continue the next authorized unit in the same turn.

On failure, distinguish source-contract mistakes, ingestion, edit rejection, engine failure and refusal using actual errors, logs and retained objects. Try a materially different applicable documented alternative on the same conversation. If none remains, report expected/actual, operation/error, retained work, alternatives and the needed decision. No unlimited retries, repeated rejected payloads, unrequested code, sample-sized unrolling or destructive restart. Attribute a limitation to DSS/version only with evidence.

After the last build unit, read the flow graph once for collapse candidates: an intermediate whose only consumer is the next recipe of the same kind; empty, superseded or scratch nodes; and any optimization the operator requested. Record each candidate's decision, or "no collapse candidates". Prove a replacement's schema, counts and values before deleting what it replaces.

## Validate

Reconcile inventory, recipe read-back, lineage and every required output with the approved validation plan. Outputs must derive from original logical inputs through Dataiku recipes, without unrequested code or cached-answer dependencies. Record genuine corrections to source authority; do not rewrite the contract to fit the build. Empty output is valid only when the source permits it; unreadable data is not a pass.

Default to a local full export comparison for applicable references. Compare ordered names/types and every row/column at output entity/period grain, including duplicates and extra rows. Verify key uniqueness before keyed comparison; otherwise compare row multisets. Use contract-derived numeric/date normalization. Totals can hide offsetting errors: inspect per-entity signed differences. Partial references support only documented checks. Samples and self-written source reimplementations do not prove parity. Without a reference, check schemas, source invariants, boundaries and target execution and state that scope.

Build a parity check inside Dataiku only when the operator or the active source guide requires one. Keep references separate from delivered logic; delete temporary parity assets after recording evidence. Synthetic runs need real-input revalidation before production parity claims. Record results/deviations in `validation_report.md`.

Correct failures and recheck affected descendants while evidence supports a next action. Reuse unaffected evidence only while relevant inputs/settings are unchanged. Unresolved required checks mean partial/blocked, never accepted or completed.

## Document and Cleanup

Prepare required documentation and authorized cleanup before final acceptance, reusing completed work. Then run the rebuild scenario once as the final build proof and settle its jobs. After that run, re-read every required output's ordered schema, row evidence and contract values and repeat applicable parity; a pre-rebuild sample is not final evidence.

- Describe business purpose in project short/long descriptions and wiki home. Describe every migration-owned source, intermediate, recipe, zone and required surface: grain, rule and use. Dataset field: `description`; recipe/zone field: `shortDesc` (read responses: `short_description`); their long description is not rendered. Project content describes objects in the delivery language, without implementation-agent terminology.
- Zone every migration-created Flow asset by stage/function. In a new Flow, rename the undeletable Default zone and use it as the first stage, with distinct zone colors; every migration-created or renamed zone holds assets at the end. In an existing project, preserve its organization. Default membership is implicit, so empty `items` proves nothing. Enable zone descriptions through [project settings](projects/settings.md) and verify the read-back.
- Wiki: plans, source→recipe→output mapping, validation results, deviations (including engine-required renames and choices recorded for open questions), final-output column dictionary and rebuild runbook. Keep column documentation here, not in propagated dataset schemas. Use native object links such as `[clean_customers](recipe:clean_customers)`.
- Perform cleanup under the invariants and Cobuild confirmation protocol. Prove replacement schema/values and check impacts before deleting originals; record deleted assets and keep the ownership inventory current.

Save `documentation_evidence.md` with enumerated ownership, displayed descriptions, zone placement, wiki and required surfaces. Completion requires that inventory, validation evidence and the rebuild scenario's job result, never the Cobuild report alone. Run any finish check the caller or source guide requires once, for the final state. Fix required failures; change the project for a warning only when it reveals an unmet contract obligation, and explain the others. Report inherited findings separately without claiming a clean project or expanding scope.

A prose edit needs documentation read-back; a data/schema/storage change invalidates affected output/parity evidence; deletion needs dependency/surface checks. After local fixes, use targeted checks rather than another full build. Follow any caller acceptance/closing gates; hand off project URL, evidence, delivered surfaces, deviations and unresolved limits.
