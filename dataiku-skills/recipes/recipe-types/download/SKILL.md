---
name: dataiku-recipe-download
description: "Download files from file-based connections into a managed folder."
---

# Download Recipe Overview

The download recipe fetches files from external sources (file-based connections) and writes them to one output managed folder.

## I/O Requirements

**Inputs:** none (sources are configured in `params.sources[]`, not as DSS flow inputs).

**Output:** exactly 1 managed folder (role `main`). Pass the folder **ID** (not display name) to `create_recipe`.

## Steps to Create or Update a Download Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply download-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `params`.
2. Update download behavior with `set_recipe_settings` action `set_params` (`sources`, file-sync flags, and variable-loop controls are the primary control blocks).

## Required Reference Files

Read this reference before editing download recipes:

- [Download recipe settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed download recipes, behavior is params-driven and payload is not used; prefer `set_params` over `set_payload`.
2. Keep `sources[]` coherent:
- each source needs `providerType` and source-specific `params`;
- preserve source access fields unless explicitly asked to change them.
3. Preserve routing/security-related fields unless explicitly requested (`useGlobalProxy`, `connection`, `trustAnySSLCertificate`).
4. For output folder changes, use `set_recipe_settings` action `set_outputs` and reference discovered folder ids/names from `list_managed_folders` (do not attempt output wiring through params).
5. Keep sync behavior explicit:
- `deleteExtraFiles=true` removes destination files not present at source;
- `copyEvenUpToDateFiles=true` forces recopy of unchanged files.
6. Preserve `variablesExpansionLoopConfig` unless explicitly requested.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For download, prefer `set_params`; `set_payload` is usually unnecessary.
- For deterministic edits of nested source configuration, read current params then use `set_params` with `merge=false`.

## DSS Documentation

- Download recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/download.html
