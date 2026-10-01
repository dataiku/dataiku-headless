---
name: project-libraries
description: Understand and inspect a Dataiku project's library tree and, when explicitly needed, write a project library file from a local workspace path. Use when an agent must inspect project source, add a user-supplied local source file, or gather context before Cobuild makes broader library changes.
---

# Project Libraries

Use this guide to understand and inspect the project library, and to handle the direct local-source-file write exception.

## Project Library Concepts

A project library is the per-project source tree available to project code, including recipes, notebooks, and WebApps. Use it for Python modules, R scripts, SQL templates, JSON fixtures, and other small code-supporting resources.

Do not use the project library as a general file store. Use managed folders for binary files, large data files, exports, and job artifacts. Use datasets for tabular lookup or reference data.

A project library can contain internal files and git-imported external libraries. External libraries contribute to the same tree but are configured from a remote repository; they should not be recreated through individual file uploads.

By default the tree has top-level `python/` and `R/` source folders. The `pythonPath` list in `/external-libraries.json` lists the Python source folders. Place Python files under `/python/` and R files under `/R/`, preserving their relative structure; keep Python source out of the library root. Each subfolder of a Python source folder needs an `__init__.py`.

## Modification Routes

| Action | Route |
| --- | --- |
| Write one user-supplied local source file | Direct write exception (stdio only) |
| Move, rename, delete, or restructure library content | Cobuild |
| Configure, update, or remove a git-imported external library | Cobuild |

## Workflow

1. Use `list_project_library` to discover the current tree and distinguish internal from external content when relevant. Read `/external-libraries.json` when a non-default source folder may apply.
2. Use `read_project_library_file` and `search_project_library` to understand existing source before changing it. Before writing a module, check the listing for a file with the same name elsewhere in the tree.
3. In stdio, when the user explicitly wants to add or replace a local source file, use `write_project_library_file`. Place Python under `/python/...` and R under `/R/...`; place SQL templates, JSON fixtures, and other support files in an appropriate non-source path. Add an `__init__.py` only for each new Python package subfolder. It is unavailable in Streamable HTTP.
4. Read the existing target before replacement. Use overwrite only with explicit user intent.
5. Validate or re-read a written Python file with `validate_project_library_file` and `read_project_library_file`.
6. When the user mentions a git-hosted library, repository, branch, tag, or commit, route external-library configuration through `./cobuild.md`.
7. Route all other library restructuring and project-asset changes through Cobuild.

## Preferred Tools

- `list_project_library`
- `read_project_library_file`
- `search_project_library`
- `validate_project_library_file`
- `write_project_library_file`

## Safety Rules

- Never use overwrite without explicit user intent.
- Never keep the same module at two library paths.
- Never place credentials, tokens, or other secrets in project library source.
