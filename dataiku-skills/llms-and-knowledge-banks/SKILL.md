---
name: llms-and-knowledge-banks
description: Inspect DSS LLMs, inspect/build existing Knowledge Banks, and create/update/inspect Retrieval-Augmented LLMs. Use this for project objects around GenAI flows, not for creating GenAI flow recipes themselves.
---

# LLM Project Objects

Use this skill for non-recipe LLM project objects that already exist in a DSS project.

This skill is intentionally narrow:
- it covers project-object inspection for `LLM`, `Knowledge Bank`, and `Retrieval-Augmented LLM`
- it covers building an existing Knowledge Bank object
- it covers creating and updating Retrieval-Augmented LLM objects
- it does **not** replace the `recipes` skill for GenAI flow steps

## When To Use This Skill

Use this skill when the user wants to:
- inspect which LLMs are available in a project
- inspect full metadata for a specific LLM
- inspect an existing Knowledge Bank
- build an existing Knowledge Bank
- search an existing Knowledge Bank
- delete an existing Knowledge Bank, after explicit confirmation
- inspect an existing Retrieval-Augmented LLM
- create a Retrieval-Augmented LLM from an existing Knowledge Bank
- update Retrieval-Augmented LLM settings through a full-settings round-trip

Do **not** use this skill when the user wants to create or edit flow steps such as:
- prompt recipes
- classification/summarization recipes
- embedding recipes
- document extraction recipes

Those belong under `dataiku-skills/recipes/SKILL.md` and the relevant recipe-type child skill.

## Follow This Execution Pattern

1. Use `get_flow_items_in_traversal_order` when flow context matters.
2. For model discovery, call `list_llms`.
3. For Knowledge Bank discovery, call `list_knowledge_banks`.
4. Before building or searching a Knowledge Bank, call `get_knowledge_bank_settings`.
5. Before deleting a Knowledge Bank, verify the target with `list_knowledge_banks` or `get_knowledge_bank_settings`, then confirm destructive intent with the user.
6. For Retrieval-Augmented LLM discovery, call `list_retrieval_augmented_llms`, then inspect one with `get_retrieval_augmented_llm_settings`.
7. To create a Retrieval-Augmented LLM, first discover the `knowledge_bank_ref` with `list_knowledge_banks` and the `llm_id` with `list_llms`, then call `create_retrieval_augmented_llm`.
8. To edit a Retrieval-Augmented LLM, always round-trip through `get_retrieval_augmented_llm_settings`, modify only what you need, then call `set_retrieval_augmented_llm_settings`. Always review [Observed Retrieval-Augmented LLM settings structure](references/retrieval_augmented_llm_observed_structure.md) before editing a Retrieval-Augmented LLM.

## Object Shape Notes

### LLM discovery and detail

Use `list_llms` to discover valid LLM IDs before choosing a model.

`list_llms` returns compact list rows:
- `id`
- `name`
- `type`
- `connection`
- `model`
- `available_purposes`

Use `list_llms(purpose=...)` to narrow by use case. Supported purposes are `ALL`, `GENERIC_COMPLETION`, `TEXT_EMBEDDING_EXTRACTION`, `IMAGE_EMBEDDING_EXTRACTION`, `RERANKING`, and `IMAGE_GENERATION`.

Use `get_llm_info` to inspect the full DSS payload for one LLM. Do not expect `list_llms` to include raw provider/model metadata.

### Knowledge Bank settings

`get_knowledge_bank_settings` returns a rich object, not just vector-store fields. Expect fields such as:
- `embeddingLLMId`
- `vectorStoreType`
- `distanceMetric`
- `metadataColumnsSchema`
- `filterCapabilities`
- `envSelection`
- `containerExecSelection`
- optional multimodal/image-storage fields such as `managedFolderId` and `multimodalColumn`

Treat these as live DSS settings. Preserve unknown fields unless the user explicitly asks to change them.

### Retrieval-Augmented LLM settings

`get_retrieval_augmented_llm_settings` returns a versioned object:
- top level includes `activeVersion`
- per-version configuration lives under `versions[]`
- the actual RAG configuration is typically inside `versions[i].ragllmSettings`

Observed live objects also show that:
- top-level `tags`, `customFields`, and `checklists` are part of the returned settings object
- each version also carries metadata and agent-setting blocks outside `ragllmSettings`
- disabled features may still keep populated nested blocks
- optional nested blocks appear only when DSS/UI has materialized them

When editing a Retrieval-Augmented LLM:
- first identify the active version
- make the minimum necessary change inside that version's `ragllmSettings` block unless the user explicitly wants version management
- preserve all unrelated versions in `versions[]`
- preserve top-level metadata containers such as `tags`, `customFields`, and `checklists`
- preserve per-version metadata and non-RAG settings blocks such as `versionTag`, `creationTag`, `pythonAgentSettings`, `pluginAgentSettings`, `toolsUsingAgentSettings`, `structuredAgentSettings`, `quickTestQueryStr`, and version-level `guardrailsPipelineSettings`
- do not guess absent nested fields
- do not remove disabled nested blocks just because they appear unused

## Preferred Tools

- Discover LLMs: `list_llms`, `get_llm_info`
- Discover KBs: `list_knowledge_banks`, `get_knowledge_bank_settings`
- Build KBs: `build_knowledge_bank`
- Search KBs: `search_knowledge_bank`
- Delete KBs: `delete_knowledge_bank` (requires explicit user intent)
- Discover RAG LLMs: `list_retrieval_augmented_llms`, `get_retrieval_augmented_llm_settings`
- Create RAG LLMs: `create_retrieval_augmented_llm`
- Edit RAG LLMs: `set_retrieval_augmented_llm_settings`
- Read RAG/KB metadata: `get_flow_object_metadata` (use object ID as `object_name`)

> **Limitation:** `set_flow_object_metadata` writes are silently ignored for `retrieval_augmented_llm` (Dataiku bug). Knowledge banks are unaffected.

## Flow-First Guardrails

- Do not create Knowledge Banks directly through project-object APIs when the user wants a reproducible flow artifact. Prefer flow recipes such as `embed_documents` or `nlp_llm_rag_embedding`.
- Treat `build_knowledge_bank` as a DSS build operation on an existing project object, not as object creation.
- For Knowledge Bank job tracking and investigation, load `../jobs/SKILL.md`.
- Retrieval-Augmented LLM creation is allowed here because DSS surfaces it as a visible flow object in the UI, even though the SDK creation path is project-object based.
- `set_retrieval_augmented_llm_settings` is a full replace. Always round-trip through `get_retrieval_augmented_llm_settings` first.
- For Retrieval-Augmented LLM edits, preserve `activeVersion`, unrelated version entries, top-level metadata containers, and per-version metadata/agent-setting blocks unless the user explicitly wants version-management or agent-setting changes.
- Treat `filter.uiData`, `reranking.llmId`, `ragSpecificGuardrails.embeddingModelId`, `ragSpecificGuardrails.llmId`, and `sourcesSettings` metadata fields as feature-conditional live fields, not as guaranteed schema.
- If the user asks to change only one knob such as `maxDocuments`, `searchType`, reranking, or sources formatting, do not rewrite adjacent feature blocks unless the live settings show DSS changed them too.
- Keep GenAI flow construction in the `recipes` skill tree to avoid overlapping ownership.
