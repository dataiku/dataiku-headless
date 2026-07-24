---
name: managed-folders
description: Understand and inspect Dataiku managed folders and, when explicitly needed, create one on a chosen connection or upload a local file into an existing folder. Use when an agent must inspect folder storage or contents, gather context for Cobuild, or directly create a managed folder or upload a local file when needed.
---

# Managed Folders

Use this guide to understand and inspect managed folders, and to handle the narrow direct exceptions for folder creation and local-file upload.

## Managed Folder Concepts

A managed folder is a connection-backed project asset for arbitrary files and file-based artifacts. It is appropriate for documents, binary files, exports, model artifacts, and other non-tabular content.

Managed folders differ from datasets, which represent tabular data, and project libraries, which hold source code and small code-supporting resources.

Folder connection, path, and contents determine how a folder can be used. Most managed-folder changes still belong in Cobuild so their surrounding Flow context is selected deliberately.

## Creation and Modification Routes

| Action | Route |
| --- | --- |
| Create a managed folder | Direct creation exception |
| Delete, reconfigure, or restructure a managed folder | Cobuild |
| Change folder metadata or broader project assets that use the folder | Cobuild |
| Place a user-supplied local file in an existing folder | Direct upload exception |

Direct upload can replace an existing file at the same folder path. Inspect the target path and obtain explicit user intent before replacing it.

## Workflow

1. Use `list_managed_folders` to discover exact folder IDs, names, types, and connections.
2. Use `get_managed_folder_info` and `get_managed_folder_contents` to inspect a selected folder before any follow-up action.
3. When a new folder is required before upload or other work can proceed, inspect `./connections.md` if needed and ask the caller to choose a compatible connection explicitly.
4. Use `create_managed_folder` only for that connection-backed bootstrap creation. Do not invent a default connection.
5. For a requested local-file upload, confirm the local source file and target folder path. If the target path already exists, obtain explicit replacement intent.
6. Use `upload_file_to_managed_folder` only for that explicit local-file placement.
7. Re-inspect folder contents when confirmation that the file is present matters.
8. Route folder deletion, reconfiguration, restructuring, and broader project-asset changes through `./cobuild.md`.

## Preferred Tools

- `list_managed_folders`
- `create_managed_folder`
- `get_managed_folder_info`
- `get_managed_folder_contents`
- `upload_file_to_managed_folder`

## Safety Rules

- Do not default to an instance-specific connection. The caller must discover and choose one.
- Do not replace an existing folder path without explicit user intent.
