---
name: project-libraries
description: Read and edit a Dataiku project's library — the per-project tree of Python modules and supporting files mounted onto recipes, notebooks, and webapps. Use when an agent must list, read, write, validate, search, create, rename, move, or delete project library files/folders, or configure external (git-imported) libraries linked to the project.
---

# Project Library Operations

## Do NOT use this skill for

- **Binary or large data file transport** (anything over ~100 KB, anything not source code). Project library is for *code that runs inside DSS*. For data, use a managed folder.
- **Per-row reference / lookup data** (mapping CSVs, label tables). Use a managed dataset.
- **Job-run artifacts or scratch files** (job outputs, exports, temp data). Use a managed folder, scenario variables, or a dataset, depending on the artifact.

If you find yourself trying to use project library as a general file store, stop. That's the wrong tool.

## When this skill is the right fit

- Python modules imported by recipes, notebooks, or webapps (`/python/<module>.py`).
- R scripts and small text resources used by project code.
- SQL templates, JSON fixtures, and small configuration files.
- Configuring or removing git-imported external libraries that contribute files to the same tree.

## Execution Pattern

1. Inspect before mutating: `list_project_library` for the current tree. Use `source="external"` or `include_external_metadata=true` when you need to understand git-imported libraries.
2. Announce the intended action in one sentence.
3. Read before overwrite: use `read_project_library_file` before replacing an existing file so you understand what is already there.
4. Validate Python with `validate_project_library_file` before writing when the target is a `.py` file.
5. For file writes, materialize the content as a local workspace file first, then call `write_project_library_file` with that local `filepath`.
6. Mutate one thing at a time: `write_project_library_file`, `create_project_library_folder`, `rename_project_library_item`, `move_project_library_item`, `delete_project_library_item`, or `set_external_library`.
7. Validate by re-reading, re-listing, or searching the affected path.

## Git Imports Are External Libraries First

Whenever the user mentions a git URL, repo, branch/tag/commit, or any "git-hosted" library inside a project context, use `set_external_library` rather than copying remote repository contents into the internal file tree by hand.

If `set_external_library` fails (auth error, unreachable remote, invalid checkout, path conflict, etc.), stop and ask the user how to proceed. Never silently retry as an internal-tree write.

## Tool Reference

### Tree contents

| Goal | Tool |
| --- | --- |
| List files/folders recursively, optionally filtered to internal or external items | `list_project_library` |
| Read a text file | `read_project_library_file` |
| Validate Python (AST + extracted imports) | `validate_project_library_file` |
| Search file contents (substring or regex, optional file glob) | `search_project_library` |
| Create or update a file from a local workspace path | `write_project_library_file` |
| Create a folder (with intermediates) | `create_project_library_folder` |
| Rename a file or folder in place | `rename_project_library_item` |
| Move a file or folder under another folder | `move_project_library_item` |
| Delete a file or folder | `delete_project_library_item` |

### External (git-imported) libraries

| Goal | Tool |
| --- | --- |
| Create, update, or remove an external library configuration | `set_external_library` |
| Inspect external-library contents and metadata through the unified tree view | `list_project_library` |

`set_external_library` is declarative and keyed by `local_path`:
- `enabled=true` ensures the library exists with the requested `remote`, `checkout`, and `path_in_repo`
- if no library exists at that `local_path`, it creates one
- if one exists with the same config, it returns unchanged
- if one exists with different config, it updates and resets it
- `enabled=false` ensures the library does not exist
- when `enabled=false`, `remote` and `checkout` are not required
- when `enabled=false` and no matching library exists, it returns unchanged

## Key Behaviors

- **Paths use forward slashes**, leading slash optional. The root is `/`.
- **Unified tree view**: `list_project_library` can return `source: "internal"` and `source: "external"` items together, or filter to one side with `source="internal"` / `source="external"`.
- **Create parents automatically**: `write_project_library_file` creates missing intermediate folders on the way to the file path.
- **Local file source**: `write_project_library_file` uploads bytes from a local `filepath`; it does not accept inline file content.
- **Rename vs move**: `rename_project_library_item` only changes the basename; `new_name` must not contain `/`. To relocate use `move_project_library_item`.
- **Recursive delete**: `delete_project_library_item` requires `recursive=true` for folders.
- **Validation scope**: `validate_project_library_file` does AST parsing for Python files and returns extracted imports, including `relative_level` for relative imports. Non-Python files return `is_valid: true` with checks skipped.
- **Search controls**: `search_project_library` supports substring search by default, regex search with `is_regex=true`, case-insensitive matching with `case_insensitive=true`, and optional glob filtering with `file_glob`.

## Safety Rules

- Never invent paths — always call `list_project_library` first to discover the tree.
- Treat `write_project_library_file(overwrite=true)` as destructive: read the current file first unless the user explicitly wants a blind replacement.
- Treat `delete_project_library_item` as destructive, especially with `recursive=true` for folders.
- Never embed credentials into code files or commit messages. External-library configuration should stay in DSS config, not in source text.
