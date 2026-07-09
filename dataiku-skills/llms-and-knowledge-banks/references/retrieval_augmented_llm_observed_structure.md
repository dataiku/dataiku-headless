---
name: retrieval-augmented-llm-observed-structure-reference
description: "Observed settings structure reference for Retrieval-Augmented LLM objects, for conservative round-trip editing guidance."
---

# Observed Retrieval-Augmented LLM Settings Structure Reference

Use this reference when editing Retrieval-Augmented LLM settings through `get_retrieval_augmented_llm_settings` and `set_retrieval_augmented_llm_settings`.

## Observed Settings Shape

In observed Retrieval-Augmented LLM objects:

- the top-level object is versioned
- `activeVersion` selects the active entry in `versions[]`
- the RAG configuration lives inside `versions[i].ragllmSettings`
- top-level metadata containers such as `tags`, `customFields`, and `checklists` are part of the returned settings object
- each version also includes metadata and agent-setting blocks outside `ragllmSettings`

## Top-Level Fields

Observed top-level fields:

- `activeVersion`
- `versions`
- `projectKey`
- `id`
- `tags`
- `customFields`
- `checklists`

Top-level field matrix:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `activeVersion` | yes | `string<version_id>` | Active version selector. Preserve unless intentionally changing version routing. |
| `versions` | yes | `list<object>` | Full per-version settings list. Preserve unrelated versions. |
| `projectKey` | yes | `string<project_key>` | Project context field returned by DSS. Preserve as-is. |
| `id` | yes | `string<rag_llm_id>` | Retrieval-Augmented LLM id. Preserve as-is. |
| `tags` | yes | `list<object>` | Metadata container. Preserve when present. |
| `customFields` | yes | `object` | Metadata container. Preserve when present. |
| `checklists` | yes | `object` | Metadata container. Preserve when present. |

## `versions[]` Model

Observed `versions[]` fields:

- `versionId`
- `versionTag`
- `creationTag`
- `pythonAgentSettings`
- `pluginAgentSettings`
- `toolsUsingAgentSettings`
- `structuredAgentSettings`
- `ragllmSettings`
- `quickTestQueryStr`
- `guardrailsPipelineSettings`

`versions[]` field matrix:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `versionId` | yes | `string<version_id>` | Version identifier. Preserve unless intentionally managing versions. |
| `versionTag` | yes | `object` | DSS version metadata. Preserve. |
| `creationTag` | yes | `object` | DSS creation metadata. Preserve. |
| `pythonAgentSettings` | yes | `object` | Agent/runtime block outside RAG settings. Preserve unless intentionally changing agent behavior. |
| `pluginAgentSettings` | yes | `object` | Agent/runtime block outside RAG settings. Preserve unless intentionally changing agent behavior. |
| `toolsUsingAgentSettings` | yes | `object` | Agent/runtime block outside RAG settings. Preserve unless intentionally changing agent behavior. |
| `structuredAgentSettings` | yes | `object` | Agent/runtime block outside RAG settings. Preserve unless intentionally changing agent behavior. |
| `ragllmSettings` | yes | `object` | Actual Retrieval-Augmented LLM configuration block. |
| `quickTestQueryStr` | yes | `string<any>` | Quick-test payload stored by DSS. Preserve when present. |
| `guardrailsPipelineSettings` | yes | `object` | Version-level guardrails pipeline block. Preserve unless intentionally changing it. |

## `ragllmSettings` Field Matrix

Observed top-level `ragllmSettings` fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `kbRef` | yes | `string<knowledge_bank_id>` | Backing Knowledge Bank reference. |
| `llmId` | yes | `string<llm_id>` | Base LLM used for answer generation. Preserve unless intentionally switching models. |
| `printSources` | yes | `boolean` | Source-display toggle. |
| `includeContentInSources` | yes | `boolean` | Source-content inclusion toggle. |
| `outputFormat` | yes | `enum/string` | Observed: `SEPARATED`, `TEXT`. |
| `searchInputStrategySettings` | yes | `object` | Search-input strategy block. See below. |
| `retrievalSource` | yes | `enum/string` | Observed: `MULTIMODAL`, `EMBEDDING`. |
| `ragSpecificGuardrails` | yes | `object` | Guardrail settings block. See below. |
| `guardrailsPipelineSettings` | yes | `object` | Guardrails pipeline block inside `ragllmSettings`. Preserve when present. |
| `completionSettings` | yes | `object` | Completion/runtime block for answer generation. Preserve unless intentionally changing completion behavior. |
| `noSourcesStrategy` | yes | `enum/string` | Observed: `CONTINUE`, `FAIL`. |
| `contextMessage` | yes | `string<any>` | Retrieval grounding instruction. Preserve unless intentionally rewriting prompting behavior. |
| `enforceDocumentLevelSecurity` | yes | `boolean` | Document-level security toggle. |
| `performFiltering` | yes | `boolean` | Retrieval filtering master toggle. |
| `allowDynamicFiltering` | yes | `boolean` | Observed only as `false`; preserve when present. |
| `allowAgentInferredFiltering` | yes | `boolean` | Observed only as `false`; preserve when present. |
| `filter` | yes | `object` | Filter block. See below. |
| `columnsDescriptions` | yes | `list<object>` | Column-description block. Observed as empty list; preserve when present. |
| `retrievalColumns` | yes | `list<string>` | Retrieval column selection. Preserve ordering/content unless intentionally changing retrieval scope. |
| `searchType` | yes | `enum/string` | Observed: `SIMILARITY`, `SIMILARITY_THRESHOLD`, `MMR`. |
| `similarityThreshold` | yes | `number` | Threshold parameter. Observed even when `searchType` was not threshold-based. Preserve unless intentionally changing retrieval behavior. |
| `maxDocuments` | yes | `integer` | Maximum retrieved documents. |
| `mmrK` | yes | `integer` | MMR retrieval parameter. Observed even when `searchType` was not `MMR`. Preserve unless intentionally changing retrieval behavior. |
| `mmrDiversity` | yes | `number` | MMR diversity parameter. Observed even when `searchType` was not `MMR`. Preserve unless intentionally changing retrieval behavior. |
| `useAdvancedReranking` | yes | `boolean` | Observed only as `false`; preserve when present. |
| `rrfRankConstant` | yes | `integer` | Hybrid/reranking-related parameter. Observed even when advanced reranking was disabled. Preserve unless intentionally changing ranking behavior. |
| `rrfRankWindowSize` | yes | `integer` | Hybrid/reranking-related parameter. Observed even when advanced reranking was disabled. Preserve unless intentionally changing ranking behavior. |
| `includeScore` | yes | `boolean` | Observed only as `false`; preserve when present. |
| `allowEmptyQuery` | yes | `boolean` | Observed only as `false`; preserve when present. |
| `reranking` | yes | `object` | Reranking block. See below. |
| `sourcesSettings` | yes | `object` | Sources formatting block. See below. |
| `augmentationFallbackStrategy` | yes | `enum/string` | Observed: `USE_EMBEDDING`, `FAIL`, `SKIP`. |

## Nested Block Notes

### `searchInputStrategySettings`

Observed fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `strategy` | yes | `enum/string` | Observed: `RAW_QUERY`, `REWRITE_QUERY`. |
| `rewritePrompt` | yes | `string<any>` | Observed even when `strategy="RAW_QUERY"`. Preserve unless intentionally changing rewrite behavior. |

### `ragSpecificGuardrails`

Observed fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `faithfulnessSettings` | yes | `object` | Present in all observed objects. |
| `relevancySettings` | yes | `object` | Present in all observed objects. |
| `multimodalFaithfulnessSettings` | yes | `object` | Present in all observed objects. |
| `multimodalRelevancySettings` | yes | `object` | Present in all observed objects. |
| `embeddingModelId` | conditional | `string<llm_id>` | Observed when guardrails used embedding-based evaluation. |
| `llmId` | conditional | `string<llm_id>` | Observed when guardrails used an LLM-backed evaluator. |

Observed subfield pattern for the `*Settings` blocks:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `answerOverwrite` | yes | `string<any>` | Replacement answer text when overwrite handling is used. |
| `enabled` | yes | `boolean` | Guardrail enable/disable toggle. |
| `threshold` | yes | `number` | Guardrail threshold. |
| `handling` | yes | `enum/string` | Observed: `FAIL`, `OVERWRITE_ANSWER`. |

### `filter`

Observed fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `distinct` | yes | `boolean` | Distinct toggle. |
| `enabled` | yes | `boolean` | Filter enable toggle. |
| `uiData` | conditional | `object` | UI-edited filter-builder payload. Observed both with and without `performFiltering=true`. Preserve when present. |

Observed `filter.uiData` notes:

- `uiData` can be structurally rich and nested
- `uiData.conditions[]` may include nested `subCondition` blocks
- do not reconstruct this block from scratch unless intentionally rewriting the filter

### `reranking`

Observed fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `enabled` | yes | `boolean` | Reranking enable toggle. |
| `maxDocuments` | yes | `integer` | Reranked-document cap. |
| `llmId` | conditional | `string<llm_id>` | Present when reranking is enabled. Preserve when present. |

### `sourcesSettings`

Observed fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `snippetFormat` | yes | `enum/string` | Observed: `TEXT`, `JSON`. |
| `metadataInSources` | yes | `list<string>` | Source metadata fields to render. |
| `titleMetadata` | conditional | `string<column_name>` | Observed in some objects. Preserve when present. |
| `thumbnailURLMetadata` | conditional | `string<column_name>` | Observed in some objects. Preserve when present. |
| `snippetMetadata` | conditional | `string<column_name>` | Observed in some objects. Preserve when present. |

## Versioning Notes

Observed versioned behavior:

- one live object had multiple entries in `versions[]`
- `activeVersion` pointed to only one of those entries
- different versions carried different `ragllmSettings.sourcesSettings` content

When editing a Retrieval-Augmented LLM:

- modify only the intended version, usually the active version
- preserve all unrelated versions in `versions[]`
- preserve version metadata blocks even when changing only `ragllmSettings`

## Recommended Update Pattern

- Always start from live `get_retrieval_augmented_llm_settings` output.
- Prefer narrow edits inside `versions[i].ragllmSettings` instead of reconstructing the full object.
- Preserve top-level metadata containers such as `tags`, `customFields`, and `checklists`.
- Preserve per-version metadata and agent-setting blocks even if they seem unrelated to RAG behavior.
- Do not remove nested blocks just because a target feature is disabled; disabled blocks were still present in observed objects.
- Do not guess absent nested keys; some optional fields appeared only when DSS had materialized them.
- When changing one setting, keep adjacent feature blocks unchanged unless the live settings show DSS changed them too.
