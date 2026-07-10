---
name: project-libraries
description: Inspect a Dataiku project's library tree and, when explicitly needed, write a project library file from a local workspace path. Use this skill to discover, read, search, and validate project library content before asking Cobuild to make broader project changes.
---

# Project Library Operations

Use this skill to inspect the project library and to write a file only when the user explicitly wants to place local source content into the project library.

## Workflow

1. Use `list_project_library` to discover the current tree.
2. Use `read_project_library_file`, `search_project_library`, and `validate_project_library_file` to understand existing content before changing anything.
3. If the user explicitly wants to upload or replace a project library file from the local workspace, use `write_project_library_file`.
4. If the task requires broader project-library restructuring or other project-asset modifications, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_project_library`
- `read_project_library_file`
- `search_project_library`
- `validate_project_library_file`
- `write_project_library_file`

## Safety Rules

- Never invent library paths.
- Read a file before overwriting it unless the user explicitly wants a blind replacement.
- Keep direct write guidance here limited to `write_project_library_file`.
