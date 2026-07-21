---
name: dataiku-headless
description: Operate Dataiku DSS end to end. Use for any task that inspects, builds, runs, migrates, or verifies Dataiku projects, flows, datasets, recipes, jobs, scenarios, dashboards, ML models, GenAI agents, semantic models, WebApps, or wikis. Also use to decide whether work is a read, a Cobuild delegation, a bootstrap action, or direct execution of an existing asset.
license: Apache-2.0
metadata:
  author: dataiku
  tags: dataiku, dss, cobuild
---

# Dataiku DSS

This is the single entry point for Dataiku work. Choose one playbook from the
task table, then open only the factual reference needed for that task. The
objective-based router replaces repeated per-object workflow and safety text;
object-specific facts remain in the references.

Get exact parameters, defaults, and enums from the live tool schema. Do not
restate or guess them from these documents.

## Multi-stage judgment

Multi-stage work — a new flow, a migration, an agent system, anything with
several dependent delegate-and-verify cycles — read `soul.md` first. It is the
judgment layer above the playbooks: what their steps are for, and how to choose
when no rule decides. Skip it for one-shot reads, one direct execution, or a
single isolated Cobuild change.

## Permanent operating rules

1. **Orient from DSS state.** For work in a known project, start with
   `get_project_overview`. Add `get_flow_graph` when topology, dependencies,
   build order, branching, or zones matter. Use targeted list/read tools when the
   overview does not carry the needed object detail.
2. **Route project asset changes through Cobuild.** Creating, changing, moving, or
   deleting project assets belongs in a Cobuild conversation. Direct bootstrap
   actions exist only where work must precede Cobuild or transfer caller-owned
   data: `create_project`, `create_upload_dataset`,
   `upload_file_to_managed_folder`, and `write_project_library_file`.
3. **Execute only existing behavior directly.** `build_datasets`, `run_recipe`,
   and `run_scenario` execute assets whose design already exists. Any request
   that changes behavior goes through Cobuild.
4. **Grant edit access per message.** Keep `allow_edit_project=false` for
   inspection, explanation, and planning. Set it to true only on the message that
   carries a user-requested change.
5. **Verify independently.** A completed Cobuild turn says the request finished;
   it does not prove the resulting state or data. Check saved settings, runtime
   evidence, samples, metrics, jobs, Data Quality results, or model/application
   evidence that matches the claim.
6. **Use the audit for its stated scope.** `audit_project` checks bounded Flow
   evidence. DSS consistency failures and explicit caller contracts block its
   verdict; naming, documentation, zoning, and similar maintainability findings
   are advisory. Models, agents, scenarios, connections, and live applications
   need their targeted reads.
7. **Treat partial reads as partial.** Respect `truncated`, warnings, limits, and
   per-section errors. Narrow or page the question before concluding that omitted
   state does not exist.
8. **Keep conversation identity stable.** Reuse one `conversation_id` for related
   work in one project and instance. Conversations and turns are process-local: a
   server restart drops them, so start a new conversation rather than reusing an old
   id. Poll a returned `turn_id`; do not resend an in-progress or timed-out mutation.
9. **Stop at a coverage gap.** If neither the registered tools nor Cobuild can
   perform an action, report the gap. Do not invent an unregistered REST,
   `dataikuapi`, or local-code mutation path.

## Task to playbook

| Task | Playbook |
|---|---|
| Build, change, refactor, or extend a project asset | `playbooks/build-via-cobuild.md` |
| Investigate or explain a project, Flow, dataset, or object without changing it | `playbooks/inspect-and-explain.md` |
| Rebuild or re-run assets whose behavior is already defined | `playbooks/direct-execution.md` |
| Check a delegated result or finish an evidence-based review | `playbooks/verify-cobuild-output.md` |
| Port an Alteryx, SAS, Excel, Tableau Prep, or other legacy workflow | `playbooks/migrate.md` |

## References to open on demand

| Need | Reference |
|---|---|
| Which read discovers or inspects an object, and how changes route | `references/object-model.md` |
| Write a bounded, testable Cobuild request | `references/cobuild-prompt-patterns.md` |
| Choose a visual, ML, GenAI, or explicitly requested code recipe family | `references/recipe-families.md` |
| Inspect and verify ML models, LLMs, Knowledge Banks, agents, and reviews | `references/ml-and-genai-objects.md` |
| Choose a connection and place uploaded data, files, or project code | `references/connections-and-storage.md` |
| Handle deletion consent, ambiguous outcomes, overlap, instance switches, and secrets | `references/safety-and-confirmations.md` |

Migration source notes and parser helpers live under
`references/migration-sources/`. Formula syntax and prepare-processor facts live
under `references/recipe-shared/`. Detailed Agent, Data Quality, and wiki facts
that do not belong in the router live under `references/objects/`.
