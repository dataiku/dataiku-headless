---
name: managed-folders
description: Inspect Dataiku managed folders and, when explicitly needed, upload local files into them. Use this skill to discover folders, inspect contents, and gather context for Cobuild; folder creation, deletion, and broader modifications should go through Cobuild.
---

# Managed Folder Operations

Use this skill to inspect managed folders and handle direct file uploads when the user explicitly wants to place a local file into a folder.

## Workflow

1. Use `list_managed_folders` to discover exact folder ids and names.
2. Use `get_managed_folder_info` and `get_managed_folder_contents` to understand the folder before any follow-up action.
3. If the user explicitly wants to upload a local file, use `upload_file_to_managed_folder`.
4. If the task requires creating, deleting, or otherwise modifying managed folders as project assets, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_managed_folders`
- `get_managed_folder_info`
- `get_managed_folder_contents`
- `upload_file_to_managed_folder`

## Safety Rules

- Never invent folder ids.
- Use `upload_file_to_managed_folder` only for explicit local-file placement.
- Do not document direct managed-folder creation or deletion workflows here.
