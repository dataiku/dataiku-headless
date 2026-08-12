---
name: cross-project-sharing
description: Understand and inspect Dataiku cross-project sharing relationships. Use when an agent must determine which source-project objects are exposed to target projects before asking Cobuild to change project assets.
---

# Cross-Project Sharing

Use this guide to inspect existing cross-project sharing relationships and gather grounded context for Cobuild. To share a dataset into a project, run Cobuild in the target project that needs the dataset.

## Cross-Project Sharing Concepts

Cross-project sharing is an outbound relationship: a source project owns an object and exposes it to one or more target projects. The source project remains the owner; target projects can use the shared object as a read-only input.

A sharing relationship is defined by the source object and its target projects. One source project can expose different objects to different target projects, so inspect the source project when determining what it currently shares. Cobuild can create that relationship from the target project's conversation when a user wants to bring a dataset from another project into the target project's Flow. It may also make that choice while completing a broader request in the target project, without an explicit request to share a dataset.

Common shared objects include datasets, managed folders, saved models, knowledge banks, and evaluation stores. Before requesting a sharing change, identify the source project, target project or projects, and the exact object to expose or remove.

## Workflow

1. Identify the source project and dataset, and the target project that should use it.
2. Use `list_shared_objects` with the source project to inspect its outgoing sharing relationships when existing exposure matters.
3. Review each returned object's `type`, `local_name`, and `target_projects`. This lists objects exposed by the source project, not objects shared into it.
4. Start or continue a Cobuild conversation in the target project. Ask it to share the identified source-project dataset into that target project.
5. Use `list_datasets` in the target project to verify that the shared dataset is available before asking Cobuild to use it in the Flow.
6. For removal or other changes to an existing sharing relationship, ground the request with the same source object and target-project details, then route it through Cobuild.

## Preferred Tools

- `list_shared_objects`

## Safety Rules

- Inspecting a source project's sharing configuration requires `Read project conf` and `Write project conf` permissions on that source project.
- Confirm the source project, target project or projects, and affected objects before requesting a sharing change.
