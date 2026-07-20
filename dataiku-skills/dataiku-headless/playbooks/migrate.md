# Migrate a legacy workflow into DSS

Port business logic from a third-party tool (Alteryx, SAS, Tableau Prep, Excel)
into a runnable, reviewable Dataiku flow. A migration is a long delegate→verify
project — read `../soul.md` first. The build itself runs through
`build-via-cobuild.md`; this playbook is the migration-specific shape on top of it.

Four phases: **plan → build → validate → document & clean up.** Build and validate
loop until validation passes.

## Phase 1 — Plan

1. Resolve the source-bundle path. Create a working dir
   `<bundle_dir>/migration_v<n>/` (n starts at 1, increments if present).
2. Identify the source platform and read its source reference in full — the silent
   failure modes that make a migration wrong or mis-parsed:
   - Alteryx → `../references/migration-sources/alteryx/alteryx.md`
   - SAS → `../references/migration-sources/sas/sas.md`
   - Unknown platform → proceed best-effort from the bundle itself. To add a new
     source reference, see `../references/migration-sources/CONTRIBUTING.md`.
3. Write `migration_plan.md`: **Business intent** (harvested from the bundle's
   notes, annotations, comments, object descriptions), **input data sources** (each
   one's role), and a **Dataiku migration plan** translating the source logic into a
   visual flow. Ground recipe-family choices in `../references/recipe-families.md`.
4. Write `validation_plan.md`: inputs match the source bundle's inputs at equivalent
   grain; the flow reproduces the source's business logic; outputs are present,
   sensible, and match expectations.
5. Write `documentation_and_cleanup_plan.md`: descriptions on the project and every
   migration-created dataset/recipe; a zoning plan; a wiki carrying the migration and
   validation plans with results; and cleanup of orphaned/failed-attempt assets.

## Phase 2 — Build

Bootstrap the project (`create_project`) if none is given. Delegate the flow to
Cobuild per the migration plan, one verifiable unit at a time
(`build-via-cobuild.md`). The build must produce the DSS flow that performs the
transformation — a locally computed result merely uploaded into DSS does not count.

## Phase 3 — Validate

Run the validation plan (`verify-cobuild-output.md`). If any check fails, loop back
to Phase 2 and re-validate. Validation must confirm the final output is produced by
a recipe chain rooted in the migrated source datasets, and that the flow contains no
code recipes unless the user explicitly asked for code.

## Phase 4 — Document and clean up

Apply the documentation-and-cleanup plan through Cobuild in full. The migration is
not done until descriptions, zones, wiki, and cleanup are complete.

## Migration invariants (these make a migration valid, not just finished)

- **Visual-only by default.** Migrate with visual recipe families unless the user
  explicitly requested code. Difficulty, awkwardness, statefulness, or "easier in
  code" are never exceptions — keep searching for the visual realization
  (`../references/recipe-families.md`). If code is requested, it applies only to the
  part requested.
- **Input-boundary invariant.** The flow begins from the *same logical source
  datasets* as the bundle, at equivalent grain. Upload only those original sources —
  never a cleaned, filtered, joined, aggregated, ranked, or final-result table dressed
  up as a source.
- **DSS-execution requirement.** The final output is produced *inside* DSS from the
  migrated sources through recipes. Source fidelity alone is not enough; the flow must
  contain the transformation.
- **Cleanup safety.** Delete only migration-created failed attempts and orphans from
  this migration. Never delete assets that pre-date the migration unless the user
  explicitly asks.

## Source parsing helpers

Source-specific parsers sit beside their reference for the planner to adapt, not run
blindly — read the first docstring line (purpose · inputs → outputs · deps) and fit
the script to the bundle first. Alteryx ships
[`extract_package.py`](../references/migration-sources/alteryx/extract_package.py)
(unzip a `.yxzp` and inventory members) and
[`parse_workflow_graph.py`](../references/migration-sources/alteryx/parse_workflow_graph.py)
(parse one workflow XML into a tool-node + connection graph).

## Done when

- The flow's inputs are exactly the bundle's logical sources at equivalent grain —
  no derived table uploaded as a source.
- The requested final output is produced inside DSS by a recipe chain rooted in those
  sources, with no code recipes unless code was explicitly requested.
- The validation plan passes end-to-end, and `audit_project` reports no
  fail-severity findings.
- Descriptions, zones, and wiki (carrying both plans and their results) are complete,
  and failed-attempt/orphan assets from this migration are cleaned up.
