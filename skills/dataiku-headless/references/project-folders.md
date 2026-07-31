---
name: project-folders
description: Understand and manage Dataiku project folders. Use when an agent must inspect the folder hierarchy or organize projects into folders.
---

# Project Folders

Use this guide to inspect and manage the instance-level folder hierarchy for projects.

## Project Folder Concepts

Project folders organize projects across the Dataiku instance. They are separate from Flow zones, which organize items inside one project's Flow, and from managed folders, which are storage objects inside a project.

Project folders can be nested. Moving a project between them changes where it appears in the instance hierarchy, not the project's internal Flow.

## Modification Routes

| Action | Route |
| --- | --- |
| Create a project folder | `create_project_folder` |
| Create a project directly in a project folder | `create_project` with `folder_id` |
| Move a project into a project folder | `move_project_to_folder` |
| Delete an empty project folder | `delete_project_folder` |

## Workflow

1. Use `list_project_folders` to inspect the hierarchy, discover candidate folder IDs, and see immediate child folder names.
2. Use `get_project_folder` when you need one folder's immediate child folders or projects.
3. For folder creation, identify the parent folder first, then call `create_project_folder`.
4. To create a project directly inside a folder, confirm the project key with `list_projects` and pass the target `folder_id` to `create_project`.
5. For project moves, confirm the project key with `list_projects`, then call `move_project_to_folder`.
6. Delete a folder only when the user explicitly asks for it and the folder is empty.
7. Verify changes by re-reading `list_project_folders` or `get_project_folder`.

## Preferred Tools

- `list_project_folders`
- `get_project_folder`
- `create_project_folder`
- `create_project`
- `move_project_to_folder`
- `delete_project_folder`
- `list_projects`

## Safety Rules

- Confirm the exact destination folder before moving a project.
- Treat deletion as destructive. Delete only when the user explicitly asks for it.
- Do not confuse project folders with Flow zones or managed folders.
- Do not invent folder identifiers. Discover them from `list_project_folders`.
