---
name: cross-project-sharing
description: Inspect existing cross-project shared objects in DSS and use the results as context for Cobuild. Use when an agent must understand existing sharing relationships before asking Cobuild to change project assets.
---

# Cross-Project Sharing Inspection

Use this skill to inspect current shared objects in a project.

## Workflow

1. Use `list_shared_objects` to discover what is already shared.
2. Use the returned project and object details to ground Cobuild prompts when the user wants to create, remove, or change sharing relationships.
3. Route sharing mutations through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_shared_objects`

## Safety Rules

- Never invent source or target object identifiers.
- Do not document direct share/unshare mutation workflows here.
