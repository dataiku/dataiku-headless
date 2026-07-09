---
name: managed_folders
description: Inspect and maintain Dataiku managed folders through MCP tools. Use when an agent must create folders, upload local files, list folders, inspect folder contents/info/metrics, or delete folders with explicit user intent.
---

# Folder Operations

Use Dataiku MCP tools for managed-folder inspection and controlled maintenance in a project.

## Follow This Execution Pattern

1. Use `get_flow_items_in_traversal_order` to understand flow dependencies before folder changes.
2. Use `list_managed_folders` to discover exact folder ids/names and storage backends.
3. Use `get_managed_folder_contents`, `get_managed_folder_info`, and `get_managed_folder_metrics` before proposing destructive changes.
4. For delete, require explicit user confirmation before calling `delete_managed_folder`.

## Creating New Managed Folders

Use this section when the user explicitly wants a new managed folder, or when another workflow needs a missing folder output created first.

- Use an explicitly requested connection when the user provides one.
- Otherwise prefer the same connection as adjacent managed folders when `list_managed_folders` or `get_managed_folder_info` shows a clear match.
- Use the configured default folder connection only when there is no stronger context signal.
- Use `create_managed_folder` to create the new managed folder.

## Creating a Dataset from Folder Files

Use `create_files_in_folder_dataset` when files in a managed folder need to be read as a dataset.

- Pass `files_selection` to scope which files are read — see the files-in-folder-dataset-selection-rules reference for the full schema and examples. Omit it to read all files.
- Autodetect runs automatically. If `autodetect_warning` is present, fix column types with `set_dataset_column_storage_types` (see datasets skill).
- `columns: null` in the result means autodetect failed; `columns: []` means autodetect ran but found no columns.

## Uploading Content

Use `upload_file_to_managed_folder` when the user explicitly wants to place a local file in a managed folder.

- Inspect the folder first with `get_managed_folder_contents` to see existing contents.
- Uploading to an existing target path replaces that file.

## Preferred Tools

- Discover: `get_flow_items_in_traversal_order`, `list_managed_folders`
- Create folder: `create_managed_folder`
- Create dataset from folder: `create_files_in_folder_dataset`
- Upload: `upload_file_to_managed_folder`
- Inspect: `get_managed_folder_contents`, `get_managed_folder_info`, `get_managed_folder_metrics`
- Metadata: `get_flow_object_metadata`, `set_flow_object_metadata` (use `object_type="managed_folder"`, folder id as `object_name`)
- Delete: `delete_managed_folder`

## Safety Rules

- Never set `overwrite=true` without explicit user intent.
- Never upload over an existing managed-folder path without explicit user intent.
- Never delete a managed folder without explicit user intent.
- Prefer folder id for destructive actions when there is any ambiguity in folder names.
