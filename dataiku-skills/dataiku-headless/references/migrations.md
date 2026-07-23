---
name: migrations
description: Translate business logic from third-party tools (e.g. Alteryx, Tableau Prep, SAS, Excel) into runnable Dataiku flows. Use when user supplies a source bundle and asks to migrate, rebuild, port, or recreate its logic in DSS.
---


# Migrations

Translate business logic from third-party tools (e.g. Alteryx, Tableau Prep, SAS, Excel) into runnable Dataiku flows.

A migration consists of four phases: plan, build, validate, and document and cleanup. The "build" and "validate" phase may loop multiple times if the "validation" encounters issues with the assets created in the "build" phase.

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
    * The requested final output dataset must be produced in DSS from those migrated source datasets through one or more Dataiku recipes; uploading a precomputed final output dataset is not a valid migration.
4. Create a Validation Plan for the migrated project and write it to `<bundle_dir>/migration_v<n>/validation_plan.md`. The Validation Plan should (at least) include:
  - Check that the input datasets of the Dataiku Flow match the input datasets of the source bundle.
  - That the migrated Dataiku Flow accurately reproduces the business logic and transformation contained within the Source Bundle.
  - That the Flow outputs are sensible, match the expected outputs, and are all present.
5. Create a Documentation and Cleanup plan and write it to `<bundle_dir>/migration_v<n>/documentation_and_cleanup_plan.md`. The Documentation and Cleanup Plan must include all of the following:
  - Documentation

    Descriptions:
    1. Add a concise yet useful description to the Project.
    2. Add a concise yet useful description to all migration-created Datasets and Recipes, including intermediate assets, not only source and final outputs.

    Flow Zones:
    1. Make a plan to split up the project into an appropriate number of Flow Zones.
    2. Create the Flow Zones and add a concise description to each Flow Zone.
    3. Move all migration-created Flow assets (for example datasets and recipes) into an appropriate zone.

    Wiki:
    1. Create a Project Wiki.
    2. Populate the Wiki with the migration plan created in Phase 1; it should be human-readable.
    3. Populate the Wiki with the validation plan created in Phase 1; it should be human-readable and note the results of all validation checks.

  - Cleanup

    1. Delete any orphaned migration-created Flow assets (for example datasets and recipes) that are not part of the final migrated Flow.
    2. Do not delete pre-existing user/project assets unless the user explicitly requests it.


## Phase 2: Build

Create the Dataiku project. If no project key is specified in the user message, create the project using a sensible project key.
Read the Migration Plan from `<bundle_dir>/migration_v<n>/migration_plan.md` and build the Dataiku project via Cobuild (`./cobuild.md`).

The Build phase must create the DSS flow that performs the transformation logic. A locally computed final result that is only uploaded into DSS does not satisfy this phase.

## Phase 3: Validate

Read the Validation Plan from `<bundle_dir>/migration_v<n>/validation_plan.md`. Use the Validation Plan to check that the migration was successfull.
If any part of the validation fails, repeat the Build and then re-validate. Loop as many times as necessary until the Validation Plan passes.

Validation must confirm that the requested final output dataset is produced by a recipe chain rooted in the migrated source datasets.

Validation must also confirm that the completed migrated flow contains no code recipes unless the user explicitly requested code.

Validation is not complete until the migration also satisfies the Documentation and Cleanup Plan.

## Phase 4: Document and Cleanup

Read the Documentation and Cleanup plan from `<bundle_dir>/migration_v<n>/documentation_and_cleanup_plan.md`. Apply the Documentation and Cleanup Plan fully via Cobuild.

The migration is not complete until all required documentation, Flow Zone, Wiki, and cleanup tasks from that plan have been completed.


# Migration Notes

## Visual-only rule

Unless the user explicitly requests a code-based transformation, migrations must be implemented with visual recipe families only. Code recipes are forbidden by default.

Do not use Python, SQL, R, or other code recipes merely because the logic is awkward, stateful, easier to express in code, or difficult to reproduce visually. Difficulty is not an exception.

If the user explicitly asks for code, a code recipe may be used only for the part the user asked to implement in code. Otherwise, the migration must remain fully visual. Visual recipe families are defined in `./recipes.md`.

## Input-boundary invariant

A valid Dataiku migration must begin from the same logical source datasets as the original source bundle, at equivalent grain. The migration process may upload only those original source inputs. It is forbidden to upload locally derived substitutes for source inputs, and must not upload any cleaned, filtered, joined, aggregated, ranked, summarized, or final-result table as if it were a source dataset.

If multiple upload attempts are made while establishing the correct source boundary, only the final intended source dataset may remain in the completed project; failed attempts must be cleaned up in Phase 4.

## DSS execution requirement

A valid migration must implement the transformation logic inside DSS.

The requested final output dataset must be produced in DSS from the migrated source datasets through one or more Dataiku recipes. It is not valid to compute the final result locally and upload that precomputed final dataset as the deliverable.

Source-boundary fidelity alone is not sufficient: the migrated project must contain the DSS flow that performs the transformation.

## Cleanup safety rule

Cleanup may delete migration-created failed attempts and orphaned assets created during the current migration. This cleanup is required.
Do not delete assets that clearly pre-date the migration unless the user explicitly asks for that deletion.

## Source Bundle helper scripts

Source-parsing helpers sit beside their Source Subskill: `sources/<kind>/*.py`. Planner-domain, source-bound, optional. Discover via `ls sources/<kind>/`; first docstring line states purpose · inputs → outputs · deps. Pick on demand, adapt to the bundle before running.
