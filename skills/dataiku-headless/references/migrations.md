---
name: migrations
description: Translate business logic from third-party tools (e.g. Alteryx, Tableau Prep, SAS, Excel) into runnable Dataiku flows. Use when user supplies a source bundle and asks to migrate, rebuild, port, or recreate its logic in Dataiku.
---


# Migrations

Translate business logic from third-party tools (e.g. Alteryx, Tableau Prep, SAS, Excel) into runnable Dataiku flows.

A migration consists of four phases: plan, build, validate, and document and cleanup. The "build" and "validate" phase may loop multiple times if the "validation" encounters issues with the assets created in the "build" phase. The loaded Source Subskill may add deliverables and phase steps of its own; they are binding.

## Phase 1: Plan

The purpose of this phase is to inspect the project to be migrated (i.e. the `source bundle`), and to generate a migration, validation, and documentation and cleanup plan.

1. Resolve the source bundle path from user message. Create a working directory `<bundle_dir>/migration_v<n>/`, where `<n>` starts at `1` and increases if present.
2. Determine the source platform (e.g. Alteryx, Excel, SAS, etc.) from the user message and source bundle. Load `./migrations/sources/<source platform>/<source platform>.md` in full. For unknown platforms, proceed best-effort.
3. Review the source bundle and write a Migration Plan to `<bundle_dir>/migration_v<n>/migration_plan.md`. The Migration Plan should include:
  - Business Intent:
    * Read the instructions/notes/readme sheets, step annotations, comments, object descriptions from the bundle.
    * Summarize the business intent of the source bundle.
  - Input Data Sources:
    * List of the input data sources.
    * Explain the role of each source in accomplishing the Business Intent.
  - Dataiku Migration Plan (discover and read the needed Dataiku guides, starting with `../SKILL.md`):
    * Translate the source bundle logic into a plan for a Dataiku Flow. The migrated flow must use only visual recipe families unless the user explicitly requests a code-based transformation. Do not choose a Code recipe because it seems easier, faster, more reliable, or more expressive. If the user did not explicitly ask for code, keep searching for a visual-recipe implementation.
    * The migrated Dataiku Flow **must** start from the same input datasets as the source bundle; it is forbidden to upload locally derived substitutes for source inputs, and must not upload any cleaned, filtered, joined, aggregated, ranked, summarized, or final-result table as if it were a source dataset.
    * The requested final output dataset must be produced in Dataiku from those migrated source datasets through one or more Dataiku recipes; uploading a precomputed final output dataset is not a valid migration.
    * Time semantics: source now-functions remain `now()` in delivery; use a temporary as-of pin for historical parity, then restore and re-verify live behavior.
4. Create a Validation Plan for the migrated project and write it to `<bundle_dir>/migration_v<n>/validation_plan.md`. The Validation Plan should (at least) include:
  - Check that the input datasets of the Dataiku Flow match the input datasets of the source bundle.
  - That the migrated Dataiku Flow accurately reproduces the business logic and transformation contained within the Source Bundle.
  - That the Flow outputs are sensible, match the expected outputs, and are all present.
5. Write a Documentation and Cleanup Plan to `<bundle_dir>/migration_v<n>/documentation_and_cleanup_plan.md`. The plan must distinguish migration-created assets from pre-existing project assets and cover:
  - Flow Zones: zone every migration-created Flow asset by stage or functional area, renaming the undeletable default zone for the first stage.
  - Descriptions: the project's short and long descriptions; a description for every migration-created dataset, recipe, and zone, including intermediate assets; renaming generated `compute_<output>` recipes to names that state the transformation.
  - Wiki: a human-readable Project Wiki containing the migration plan, validation plan and results, and a final-output column dictionary. Keep column documentation out of datasets because it drifts through downstream recipe schemas.
  - Cleanup: the cleanup required by the Cleanup safety rule (see Migration Notes), and a rebuild scenario covering every final output.
6. If the source bundle has more than 20 source steps or unresolved `needs-human-input` questions, pause and surface the inventory, plans, and open questions. Otherwise print the plans and continue; unattended runs never stop.

## Phase 2: Build

Create the Dataiku project. If no project key is specified in the user message, create the project using a sensible project key.
Read the Migration Plan from `<bundle_dir>/migration_v<n>/migration_plan.md` and build the Dataiku project via Cobuild (`./cobuild.md`).

Execute the build as a sequence of coherent, independently verifiable units of work — typically one recipe, or one bounded group of related assets, per Cobuild turn. After each unit, inspect and verify the result before instructing the next; never send one monolithic instruction covering the whole flow.

The Build phase must create the Dataiku flow that performs the transformation logic. A locally computed final result that is only uploaded into Dataiku does not satisfy this phase.

Place migrated Python or R source per `./project-libraries.md`, and give Cobuild prompts that same destination path.

## Phase 3: Validate

Read the Validation Plan from `<bundle_dir>/migration_v<n>/validation_plan.md`. Use the Validation Plan to check that the migration was successfull.
If any part of the validation fails, repeat the Build and then re-validate. Loop as many times as necessary until the Validation Plan passes.

Validation must confirm that the requested final output dataset is produced by a recipe chain rooted in the migrated source datasets.

Validation must also confirm that the completed migrated flow contains no code recipes unless the user explicitly requested code.

## Phase 4: Document and Cleanup

Read the Documentation and Cleanup Plan from `<bundle_dir>/migration_v<n>/documentation_and_cleanup_plan.md` and apply it via Cobuild, except for read-back and project settings:

- Displaying zone descriptions in the Flow is a project display setting that neither Cobuild nor the available tools can change; record in the documentation evidence that the user must enable it manually.
- When setting descriptions, set the field Dataiku displays: dataset `description`; recipe and zone `shortDesc` (ask Cobuild for "short description"; their long `description` is not rendered).
- Apply the planned cleanup under the Cleanup safety rule below. Create and run the rebuild scenario; its job result is the final build proof.

Use read tools to enumerate every zone, dataset, and recipe, verify each displayed description is non-empty (`short_description` for zones and recipes; `description` for datasets), and write the inventory to `<bundle_dir>/migration_v<n>/documentation_evidence.md`. Completion claims require this inventory, validation evidence, and the scenario job result; never rely on the Cobuild report.


# Migration Notes

## Visual-only rule

Unless the user explicitly requests a code-based transformation, migrations must be implemented with visual recipe families only. Code recipes are forbidden by default.

Do not use Python, SQL, R, or other code recipes merely because the logic is awkward, stateful, easier to express in code, or difficult to reproduce visually. Difficulty is not an exception.

A statistic missing from a visual recipe's aggregate list is not yet a justification either: quantiles, medians, and modes compose from Window ranking and TopN recipes. Record a deviation only after the visual composition genuinely fails.

If the user explicitly asks for code, a code recipe may be used only for the part the user asked to implement in code. Otherwise, the migration must remain fully visual. Visual recipe families are defined in `./recipes.md`.

## Input-boundary invariant

A valid Dataiku migration must begin from the same logical source datasets as the original source bundle, at equivalent grain. The migration process may upload only those original source inputs. It is forbidden to upload locally derived substitutes for source inputs, and must not upload any cleaned, filtered, joined, aggregated, ranked, summarized, or final-result table as if it were a source dataset.

If multiple upload attempts are made while establishing the correct source boundary, only the final intended source dataset may remain in the completed project; failed attempts must be cleaned up in Phase 4.

Expected outputs may be uploaded only as parity reference datasets during validation, never wired into the delivered flow, and are deleted during cleanup.

## Dataiku execution requirement

A valid migration must implement the transformation logic inside Dataiku.

The requested final output dataset must be produced in Dataiku from the migrated source datasets through one or more Dataiku recipes. It is not valid to compute the final result locally and upload that precomputed final dataset as the deliverable.

Source-boundary fidelity alone is not sufficient: the migrated project must contain the Dataiku flow that performs the transformation.

## Gap resolution

Classify every non-obvious source construct:

- `derivable`: a function of its inputs (formula chains, lookups, query steps). Migrate it as Flow logic; never upload it as a source dataset.
- `hand-authored`: manually entered or edited values with no recoverable rule. Preserve them as source data and document them; never re-derive them.
- `needs-human-input`: answerable only by the workflow owner. Ask; do not guess.

Carry unresolved items in the Migration Plan and surface them at the Phase 1 step 6 gate.

## Cleanup safety rule

Cleanup may delete migration-created failed attempts and orphaned assets created during the current migration. This cleanup is required.
Do not delete assets that clearly pre-date the migration unless the user explicitly asks for that deletion.

## Source Bundle helper scripts

Source-parsing helpers sit in their Source Subskill's helpers directory: `sources/<kind>/helpers/*.py`. Planner-domain, source-bound, optional. Discover via `ls sources/<kind>/helpers/`; first docstring line states purpose · inputs → outputs · deps. Pick on demand, adapt to the bundle before running.
