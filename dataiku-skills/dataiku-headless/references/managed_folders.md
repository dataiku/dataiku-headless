---
name: managed-folders
description: Understand and inspect Dataiku managed folders and, when explicitly needed, upload local files into them. Use when an agent must inspect folder storage or contents, gather context for Cobuild, or place a user-supplied local file into an existing folder.
---

# Managed Folders

Use this guide to understand and inspect managed folders, and to handle the direct local-file upload exception.

## Managed Folder Concepts

A managed folder is a connection-backed project asset for arbitrary files and file-based artifacts. It is appropriate for documents, binary files, exports, model artifacts, and other non-tabular content.

Managed folders differ from datasets, which represent tabular data, and project libraries, which hold source code and small code-supporting resources.

Folder connection, path, and contents determine how a folder can be used. Create or modify a folder through Cobuild so its connection and surrounding Flow context are selected deliberately.

## Modification Routes

| Action | Route |
| --- | --- |
| Create, delete, reconfigure, or restructure a managed folder | Cobuild |
| Change folder metadata or broader project assets that use the folder | Cobuild |
| Place a user-supplied local file in an existing folder | Direct upload exception |

Direct upload can replace an existing file at the same folder path. Inspect the target path and obtain explicit user intent before replacing it.

## Workflow

1. Use `list_managed_folders` to discover exact folder IDs, names, types, and connections.
2. Use `get_managed_folder_info` and `get_managed_folder_contents` to inspect a selected folder before any follow-up action.
3. For a requested local-file upload, confirm the local source file and target folder path. If the target path already exists, obtain explicit replacement intent.
4. Use `upload_file_to_managed_folder` only for that explicit local-file placement.
5. Re-inspect folder contents when confirmation that the file is present matters.
6. For folder creation or other project-asset changes, inspect `./connections.md` when storage context is unclear, then route the change through `./cobuild.md`.

## Preferred Tools

- `list_managed_folders`
- `get_managed_folder_info`
- `get_managed_folder_contents`
- `upload_file_to_managed_folder`

## Safety Rules

- Do not replace an existing folder path without explicit user intent.
