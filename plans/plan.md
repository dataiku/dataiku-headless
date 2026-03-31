# CLI Expansion Plan

## Scope

Prioritize missing DSS capabilities that:

- materially improve agent success in real DSS operations
- fit the CLI's composable `dku <noun> <verb>` model
- are supported by the current `dataikuapi` version or stable public REST endpoints

This plan covers:

1. Wave 1: easy wins with existing `dataikuapi` wrappers
2. Wave 2: high-value additions that need broader command design and likely some raw REST usage

This plan does not include implementation yet.

## Prioritization Rules

Use these rules to sequence work:

1. Prefer commands that help agents inspect, validate, and recover over niche admin surfaces.
2. Prefer existing `dataikuapi` wrappers over raw REST when both exist.
3. Prefer extending existing nouns before adding entirely new top-level groups, unless the DSS concept is clearly first-class.
4. Every command must ship with prescriptive help text and error messages.
5. Every new capability should be reflected in docs and agent skills, not just code.

## Wave 1

### 1. Dataset Metrics, Checks, and Data Quality

#### Goal

Add observability and validation workflows around datasets so agents can verify data state instead of only creating and building datasets.

#### Proposed Command Surface

Extend `dataset`:

- `dku dataset metrics NAME -P PROJ`
- `dku dataset compute-metrics NAME -P PROJ [--partition PART] [--metric-id ID ...]`
- `dku dataset checks NAME -P PROJ`
- `dku dataset run-checks NAME -P PROJ [--partition PART] [--check ID ...]`
- `dku dataset metric-history NAME -P PROJ --metric METRIC`

Add new `data-quality` group:

- `dku data-quality instance-status`
- `dku data-quality project-status -P PROJ`
- `dku data-quality project-timeline -P PROJ`
- `dku data-quality rules DATASET -P PROJ`
- `dku data-quality create-rule DATASET -P PROJ --definition JSON`
- `dku data-quality compute DATASET -P PROJ [--partition PART]`
- `dku data-quality status DATASET -P PROJ`
- `dku data-quality history DATASET -P PROJ`
- `dku data-quality delete-rule DATASET RULE_ID -P PROJ`

#### API Mapping

- `DSSDataset.get_last_metric_values()`
- `DSSDataset.compute_metrics()`
- `DSSDataset.run_checks()`
- `DSSDataset.get_metric_history()`
- `DSSClient.get_data_quality_status()`
- `DSSProject.get_data_quality_status()`
- `DSSProject.get_data_quality_timeline()`
- `DSSDataset.get_data_quality_rules()`
- `DSSDataQualityRuleSet.list_rules()`
- `DSSDataQualityRuleSet.create_rule()`
- `DSSDataQualityRuleSet.compute_rules()`
- `DSSDataQualityRuleSet.get_status()`
- `DSSDataQualityRuleSet.get_rules_history()`

#### Tests

- unit tests for command parsing and output rendering
- tests for empty metrics/checks results
- tests for partitioned vs non-partitioned calls
- tests for JSON definition input on rule creation
- tests for admin/project permission failures with prescriptive guidance

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add dataset validation workflows to `skills/dku-cli/SKILL.md`
- add gotchas about metrics vs checks vs data-quality rules if needed

#### Open Questions

- Should `data-quality` be a dedicated noun or folded under `dataset`?
- Should rule editing be fully raw-definition based in v1, or do we want helper flags for common rule types?

### 2. Workspace

#### Goal

Expose DSS workspaces as a first-class CLI resource for organizing datasets, dashboards, wiki articles, and links.

#### Proposed Command Surface

New `workspace` group:

- `dku workspace list`
- `dku workspace get KEY`
- `dku workspace create KEY --name NAME [--description TEXT] [--color HEX]`
- `dku workspace delete KEY`
- `dku workspace objects KEY`
- `dku workspace add-object KEY --type TYPE --id ID [--project PROJ]`
- `dku workspace add-link KEY --name NAME --url URL [--description TEXT]`
- `dku workspace remove-object KEY OBJECT_ID`
- `dku workspace set-definition KEY --definition JSON`

#### API Mapping

- `DSSClient.list_workspaces()`
- `DSSClient.get_workspace()`
- `DSSClient.create_workspace()`
- `DSSWorkspace.get_settings()`
- `DSSWorkspace.list_objects()`
- `DSSWorkspace.add_object()`
- `DSSWorkspace.delete()`
- `DSSWorkspaceSettings.save()`

#### Tests

- CRUD command tests
- object-add tests for supported object types
- raw definition update tests
- error-path tests for invalid object type and missing project context

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add workspace discovery examples to `skills/dku-cli/SKILL.md`

#### Open Questions

- Should object add support only generic raw refs in v1, or also convenience flags for dataset/dashboard/wiki/article/link?
- Is `set-definition` sufficient, or do we also want `set-permissions` in the initial pass?

### 3. Data Collection

#### Goal

Add CLI support for Data Collections, which are a first-class DSS object currently absent from the CLI.

#### Proposed Command Surface

New `data-collection` group:

- `dku data-collection list`
- `dku data-collection get ID`
- `dku data-collection create --name NAME [--id ID] [--description TEXT] [--color HEX]`
- `dku data-collection delete ID`
- `dku data-collection set-definition ID --definition JSON`

#### API Mapping

- `DSSClient.list_data_collections()`
- `DSSClient.get_data_collection()`
- `DSSClient.create_data_collection()`
- data collection settings methods or raw REST if settings save is not wrapped cleanly

#### Tests

- CRUD tests
- explicit-id vs generated-id creation tests
- raw definition update tests if implemented in v1

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add discovery/inspection guidance to `skills/dku-cli/SKILL.md`

#### Open Questions

- Confirm whether settings mutation is fully wrapped in the installed `dataikuapi`, or whether `set-definition` needs raw REST.
- Decide whether permissions belong in v1 or a later pass.

### 4. API Service Package Lifecycle and Bundle Lifecycle

#### Goal

Close obvious lifecycle gaps in already-supported nouns instead of introducing new top-level concepts first.

#### Proposed Command Surface

Extend `api-service`:

- `dku api-service publish-package SERVICE_ID PACKAGE_ID -P PROJ [--published-service ID]`
- `dku api-service delete-package SERVICE_ID PACKAGE_ID -P PROJ`

Extend `bundle`:

- `dku bundle publish BUNDLE_ID -P PROJ [--published-project-key KEY]`
- `dku bundle delete-exported BUNDLE_ID -P PROJ`
- `dku bundle list-imported -P PROJ`

#### API Mapping

- `DSSAPIService.publish_package()`
- `DSSAPIService.delete_package()`
- `DSSProject.publish_bundle()`
- `DSSProject.delete_exported_bundle()`
- `DSSProject.list_imported_bundles()`

#### Tests

- package publish/delete tests
- bundle publish/delete/list-imported tests
- output rendering for list-imported
- permission failure tests with guidance

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- update bundle and API service examples in `skills/dku-cli/SKILL.md`

#### Open Questions

- Should `bundle publish` live under `bundle` only, or do we later add deployer-aware publish flows under `project-deployer`?

### 5. Discussion

#### Goal

Expose DSS discussions so agents can inspect and participate in object-level collaboration from the CLI.

#### Proposed Command Surface

New `discussion` group:

- `dku discussion list --object-type TYPE --object-id ID -P PROJ`
- `dku discussion create --object-type TYPE --object-id ID --topic TOPIC --message TEXT -P PROJ`
- `dku discussion get --object-type TYPE --object-id ID DISCUSSION_ID -P PROJ`
- `dku discussion reply --object-type TYPE --object-id ID DISCUSSION_ID --message TEXT -P PROJ`
- `dku discussion set-metadata --object-type TYPE --object-id ID DISCUSSION_ID --definition JSON -P PROJ`

#### API Mapping

- `DSSClient.get_object_discussions()`
- `DSSObjectDiscussions.list_discussions()`
- `DSSObjectDiscussions.create_discussion()`
- `DSSObjectDiscussions.get_discussion()`
- `DSSDiscussion.add_reply()`
- `DSSDiscussion.set_metadata()`

#### Tests

- object discussion list/create/get/reply tests
- metadata update tests
- invalid object type tests with prescriptive guidance

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add collaboration usage patterns to `skills/dku-cli/SKILL.md`

#### Open Questions

- Which object types should be explicitly supported in help text for v1?
- Should message input support literal, `@file`, and stdin like code/prompt commands?

## Wave 2

### 6. Project Deployer

#### Goal

Expose deployment workflows for published bundles and automation-node deployment management.

#### Proposed Command Surface

New `project-deployer` group with sub-areas:

- `deployment list|get|create|delete|status|start-update`
- `infra list|get|create|delete`
- `project list|get|create|delete`
- `upload-bundle PATH [--project-key KEY]`
- `stages`

#### API Mapping

- `DSSClient.get_projectdeployer()`
- `DSSProjectDeployer.list_deployments()`
- `DSSProjectDeployer.create_deployment()`
- `DSSProjectDeployer.list_infras()`
- `DSSProjectDeployer.create_infra()`
- `DSSProjectDeployer.list_projects()`
- `DSSProjectDeployer.create_project()`
- `DSSProjectDeployer.upload_bundle()`
- deployment and infra status/update methods in `projectdeployer.py`

#### Tests

- list/get/create flows for deployment/infra/project
- async future handling for updates
- invalid infra/bundle/project guidance tests

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add deployer workflows to `skills/dku-cli/SKILL.md`
- likely add a dedicated deployer reference doc under `skills/dku-cli/references/`

#### Open Questions

- Should `project-deployer` be a single noun with many verbs, or split by subresource in the CLI syntax?
- How much of the deployment settings surface should be exposed in v1 vs raw JSON only?

### 7. Plugin Lifecycle and Dev Plugin Git Operations

#### Goal

Fill the largest plugin-management gaps for agent-driven plugin development and maintenance.

#### Proposed Command Surface

Extend `plugin`:

- `install-git`
- `install-store`
- `download`
- `update-git`
- `update-store`
- `move-to-dev`
- `git-remote`
- `git-branches`
- `git-pull`
- `git-push`
- `git-fetch`
- `git-reset-local`
- `git-reset-remote`
- plugin file operations if supported cleanly

#### API Mapping

- wrapped plugin APIs where available
- public REST endpoints where wrapper coverage is partial

#### Tests

- install/update/download flows
- git operation tests against mocked client responses
- admin permission and unsafe operation messaging tests

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- update plugin guidance in `skills/dku-cli/SKILL.md`
- cross-link from `skills/dataiku/references/plugin-workflow.md` if needed

#### Open Questions

- Which plugin operations are safe enough for first-class commands vs too admin/destructive for the initial pass?
- Should dev-plugin git operations live under `plugin git-*` or a dedicated sub-group?

### 8. Notebook and SQL Notebook

#### Goal

Support inspection and lightweight lifecycle operations on DSS notebooks from the CLI.

#### Proposed Command Surface

New `notebook` group:

- `list`, `get`, `create`, `delete`, `sessions`, `stop-session`

New `sql-notebook` group:

- `list`, `get`, `create`, `delete`, `history`

#### API Mapping

- `DSSProject.list_jupyter_notebooks()`
- `DSSProject.get_jupyter_notebook()`
- `DSSProject.create_jupyter_notebook()`
- `DSSProject.list_sql_notebooks()`
- `DSSProject.get_sql_notebook()`
- `DSSProject.create_sql_notebook()`

#### Tests

- list/get/create/delete flows
- session-management tests for jupyter notebooks
- history rendering tests for SQL notebooks

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add notebook inspection guidance to `skills/dku-cli/SKILL.md`

#### Open Questions

- Should notebook content editing be in scope, or inspection-only in v1?
- Should Jupyter and SQL notebooks be separate top-level nouns?

### 9. Saved Model Lifecycle Expansion

#### Goal

Expand beyond saved-model inspection into packaging, evaluation, and version management workflows.

#### Proposed Command Surface

Extend `model`:

- `create`
- `set-definition`
- `evaluate-version`
- `set-version-meta`
- `import-mlflow-version`
- artifact/documentation download commands as justified by API support

#### API Mapping

- saved model APIs in `dataikuapi.dss.savedmodel`
- REST endpoints if wrapper coverage is uneven

#### Tests

- create/update/version-management flows
- artifact and evaluation paths where implemented

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- expand model lifecycle examples in `skills/dku-cli/SKILL.md`

#### Open Questions

- Which parts of the saved-model API are stable and worth exposing directly vs leaving to raw REST later?

### 10. Admin and Security Expansion

#### Goal

Broaden coverage of common administrative workflows only after the safer object-level gaps are closed.

#### Proposed Command Surface

Extend `user`:

- `get`, `update`, `delete`, `resync`, `last-activity`

Add `group`:

- `list`, `get`, `create`, `update`, `delete`

Extend `connection`:

- `get`, `update`, `delete`

Extend `code-env`:

- `set-jupyter`

#### API Mapping

- admin and security methods from `dataikuapi`
- REST endpoints for gaps

#### Tests

- admin-only permission handling
- CRUD and mutation flows
- careful error guidance for destructive operations

#### Docs and Skills Updates

- update `docs/command-api-mapping.md`
- add admin operation caveats to `skills/dku-cli/SKILL.md`

#### Open Questions

- Which admin operations require explicit confirmation patterns in the CLI?
- Do we want to defer destructive admin commands until after benchmark evidence justifies them?

## Cross-Cutting Work Required For Every Item

### Command Design

- keep noun/verb patterns consistent with existing CLI groups
- prefer extending existing nouns before introducing aliases
- support `-o table|json|csv` where list/get output makes sense
- support `--definition @file.json` and stdin input for raw JSON mutation commands

### Error Handling

- use prescriptive error messages that tell the agent what to run next
- distinguish permission failures from not-found and bad-input failures
- add gotchas to skills when a failure mode is likely to recur

### Testing

- update unit coverage for command parsing and output rendering
- add failure-path tests for every new noun or mutating command
- test both table and JSON output for list/get flows

### Documentation

- update `docs/command-api-mapping.md`
- update `README.md` command inventory if command counts change
- update `skills/dku-cli/SKILL.md` cheat sheet, examples, or gotchas where relevant

## Recommended Implementation Order

1. dataset metrics/checks + data quality
2. workspace
3. data-collection
4. api-service package lifecycle + bundle lifecycle
5. discussion
6. project-deployer
7. plugin lifecycle and dev-plugin git operations
8. notebook and sql-notebook
9. saved model lifecycle expansion
10. admin and security expansion

## Approval Checkpoints

Before implementation, confirm:

1. whether `data-quality` should be its own noun or live under `dataset` ? under dataset
2. whether `workspace` and `data-collection` should both be added in wave 1
3. whether `discussion` is worth shipping before `project-deployer`
4. whether plugin git/dev operations should be included in the first implementation milestone or kept for later
