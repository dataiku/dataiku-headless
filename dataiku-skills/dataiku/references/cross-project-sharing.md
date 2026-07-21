---
name: cross-project-sharing
description: Understand and inspect Dataiku cross-project sharing relationships. Use when an agent must determine which source-project objects are exposed to target projects before asking Cobuild to change project assets.
---

# Cross-Project Sharing

Use this skill to inspect existing cross-project sharing relationships and gather grounded context for Cobuild.

## Cross-Project Sharing Concepts

Cross-project sharing is an outbound relationship: a source project owns an object and exposes it to one or more target projects. The source project remains the owner; target projects can use the shared object as a read-only input.

A sharing relationship is defined by the source object and its target projects. One source project can expose different objects to different target projects, so inspect the source project when determining what it currently shares.

Common shared objects include datasets, managed folders, saved models, knowledge banks, and evaluation stores. Before requesting a sharing change, identify the source project, target project or projects, and the exact object to expose or remove.

## Workflow

1. Identify the source project that owns the object and the target project or projects that should use it.
2. Use `list_shared_objects` with the source project to inspect its outgoing sharing relationships.
3. Review each returned object's `type`, `local_name`, and `target_projects`. This lists objects exposed by the source project, not objects shared into it.
4. Use the discovered source object and target-project details to ground any Cobuild request to create, remove, or change sharing relationships.
5. Route sharing mutations through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_shared_objects`

## Safety Rules

- Discover source projects, target projects, and object identifiers via tools; do not invent identifiers.
- Inspecting a source project's sharing configuration requires `Read project conf` and `Write project conf` permissions on that source project.
- Keep this skill read-only. Route sharing creation, changes, and removal through `./dataiku-skills/cobuild/SKILL.md`.
- Confirm the source project, target project or projects, and affected objects before requesting a sharing change.
