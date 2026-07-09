---
name: dataiku-recipe-embed_documents
description: "Embed documents from managed folders into a Knowledge Bank, with optional vision extraction."
---

# Embed Documents Recipe Overview

Use this skill with `recipes` for work focused on recipe type `embed_documents`.

This recipe reads documents from a managed folder, extracts and chunks their contents, and populates a Knowledge Bank. When vision extraction is configured it also writes extracted image artifacts to a second managed folder.

## I/O Requirements

**Input:** exactly 1 managed folder (role `main`). When calling `create_recipe`, reference the folder by its **ID** (e.g., `SKxXpma3`), not its display name.

**Outputs:**
- 1 Knowledge Bank (role `knowledge_bank`) — **always required**. Include `embedding_llm` in the output object; if omitted, `DKU_DEFAULT_EMBEDDING_LLM` must be set on the instance.
- 1 managed folder for extracted images (role `images`) — **required when vision extraction is used**, omit otherwise.

**When is the images folder required?**
- `params.extractionMode` is `MANAGED_VISUAL_ONLY`, OR
- any extraction rule (`params.rules[].actionToPerform` or `allOtherRule.actionToPerform`) uses `"VLM"` mode or sets `storeInMultimodalColumn: "IMAGES"`.

Text-only modes (`MANAGED_TEXT_ONLY`, or `CUSTOM_RULES` with only `STRUCTURED` actions) do not need an images folder. **However, `create_recipe` always auto-creates an images managed-folder output regardless of extraction mode.** In text-only mode this folder is unused; remove it with `set_outputs` + `mode="replace"` if you want a clean recipe.

**Create-time examples:**

Text-only (no vision):
```json
{
  "recipe_type": "embed_documents",
  "inputs": ["<folder_id>"],
  "outputs": [
    {"name": "<kb_id>", "role": "knowledge_bank", "embedding_llm": "<llm_id>"}
  ]
}
```

With vision extraction:
```json
{
  "recipe_type": "embed_documents",
  "inputs": ["<folder_id>"],
  "outputs": [
    {"name": "<images_folder>", "role": "images"},
    {"name": "<kb_id>", "role": "knowledge_bank", "embedding_llm": "<llm_id>"}
  ]
}
```

## Steps to Create or Update an Embed Documents Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply embedding-specific updates:

1. Read current settings with `get_recipe_settings` and inspect both `params` and `payload`.
2. Update chunking/vector-store behavior with `set_recipe_settings` actions `set_params` and/or `set_payload`.

## Required Reference Files

Read these references before editing embed-documents recipes:

- [Embed documents settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. Treat the primary input as a managed-folder ref, not a dataset.
2. Preserve `params.extractionMode`, VLM settings, and `allOtherRule` unless the user explicitly asks to change document extraction behavior.
3. Preserve `vectorStoreUpdateMethod` and `clearVectorStore` unless the user explicitly asks for a reset or overwrite-mode change.
4. If the user requests vision extraction on a recipe that has no images-folder output, add the managed folder output first (`set_outputs` with `role="images"`), then update `params` to enable vision.
5. If the user switches from vision to text-only, remove the images-folder output via `set_outputs` with `mode="replace"` after disabling vision in `params`.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Use `set_params` for extraction behavior and `set_payload` for chunk/vector-store behavior.
- Prefer full round-trips for `params.allOtherRule` edits; it is easy to drop nested extraction settings by accident.

## DSS Reference

- Reference: `Embedding and searching documents` (https://doc.dataiku.com/dss/latest/generative-ai/knowledge/documents.html)
