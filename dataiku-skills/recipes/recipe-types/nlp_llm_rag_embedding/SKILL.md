---
name: dataiku-recipe-nlp_llm_rag_embedding
description: "Embed column text from a dataset into a Knowledge Bank for RAG retrieval and semantic search."
---

# nlp_llm_rag_embedding Recipe Skill

Use this skill with `recipes` for work focused on recipe type `nlp_llm_rag_embedding`.

## I/O Requirements

**Input:** exactly 1 dataset (role `main`).

**Output:** exactly 1 Knowledge Bank (role `knowledge_bank`). There is no dataset output.

When creating the recipe, include `embedding_llm` in the output object. If omitted, `DKU_DEFAULT_EMBEDDING_LLM` must be set on the instance.

```json
{
  "recipe_type": "nlp_llm_rag_embedding",
  "inputs": ["<input_dataset>"],
  "outputs": [
    {"name": "<knowledge_bank_id>", "role": "knowledge_bank", "embedding_llm": "<llm_id>"}
  ]
}
```

## Required Reference Files

Read these references before editing nlp_llm_rag_embedding recipes:

- [nlp_llm_rag_embedding settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and make an explicit decision about each field you change.

## Steps to Create or Update an nlp_llm_rag_embedding Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply embedding-specific updates:

1. Read current settings with `get_recipe_settings` and inspect both `params` and `payload`.
2. Update embedding behavior with `set_recipe_settings` actions `set_params` and/or `set_payload`.

## Type Notes

- Keep payload/params aligned to DSS expectations for `nlp_llm_rag_embedding`.
- Preserve existing instance-specific values unless explicitly asked to change them.
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `Introduction to Knowledge Banks and RAG` (https://doc.dataiku.com/dss/latest/generative-ai/knowledge/introduction.html)
