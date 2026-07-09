---
name: nlp-llm-rag-embedding-settings-and-payload-reference
description: "Observed params and payload structure for nlp_llm_rag_embedding recipes."
---

# nlp_llm_rag_embedding Settings And Payload Reference

Use this reference for `nlp_llm_rag_embedding` edits.

## Observed Settings Shape

In observed nlp_llm_rag_embedding recipes:

- `params` holds only container/execution settings
- `payload` controls which column to embed, metadata columns, chunking behavior, and vector-store update behavior

Observed top-level `params` keys:

- `containerSelection`

Observed top-level `payload` keys:

- `knowledgeColumn`
- `metadataColumns`
- `chunkSizeCharacters`
- `chunkOverlapCharacters`
- `documentSplittingMode`
- `vectorStoreUpdateMethod`
- `clearVectorStore`

## Params Notes

`params.containerSelection` controls the execution container. Preserve it unless the user explicitly asks to change execution behavior.

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `knowledgeColumn` | yes | `string` | Column whose text is embedded into the Knowledge Bank. |
| `metadataColumns` | no | `list<{column: string}>` | Columns stored as metadata alongside embeddings. Empty list is valid. |
| `documentSplittingMode` | no | `enum` | Observed: `CHARACTERS_BASED` |
| `chunkSizeCharacters` | no | `integer` | Observed: `3000` |
| `chunkOverlapCharacters` | no | `integer` | Observed: `120` |
| `vectorStoreUpdateMethod` | no | `enum` | Observed: `OVERWRITE`. Controls whether existing vectors are replaced or merged. |
| `clearVectorStore` | no | `boolean` | Preserve unless the user explicitly requests a full reset of the Knowledge Bank. |

## Canonical Settings Example (Trimmed)

```json
{
  "params": {
    "containerSelection": {
      "containerMode": "INHERIT"
    }
  },
  "payload": {
    "knowledgeColumn": "extracted_content",
    "metadataColumns": [
      {"column": "source_file"},
      {"column": "page_range"}
    ],
    "chunkSizeCharacters": 3000,
    "chunkOverlapCharacters": 120,
    "documentSplittingMode": "CHARACTERS_BASED",
    "vectorStoreUpdateMethod": "OVERWRITE",
    "clearVectorStore": false
  }
}
```
