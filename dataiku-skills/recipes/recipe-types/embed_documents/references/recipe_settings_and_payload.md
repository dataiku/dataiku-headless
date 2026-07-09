---
name: embed-documents-settings-and-payload-reference
description: "Observed params and payload structure for document-embedding recipes."
---

# Embed Documents Settings And Payload Reference

Use this reference for `embed_documents` edits.

## Observed Settings Shape

In observed embed-documents recipes:

- `params` controls extraction/VLM behavior
- `payload` controls chunking and vector-store update behavior

Observed `params.extractionMode` values:
- `MANAGED_TEXT_ONLY` — text extraction only, no images folder
- `MANAGED_VISUAL_ONLY` — full vision extraction, images folder required
- `CUSTOM_RULES` — per-file-type rules; images folder required if any rule uses VLM

Observed top-level `params` keys:

- `extractionMode`
- `defaultVlmId`
- `defaultImageHandlingMode`
- `rules`
- `allOtherRule`

Observed top-level `payload` keys:

- `userDefinedMetadataColumns`
- `metadataColumns`
- `chunkOverlapCharacters`
- `chunkSizeCharacters`
- `clearVectorStore`
- `vectorStoreUpdateMethod`
- `documentSplittingMode`

## Params Notes

`params.allOtherRule` is nested and easy to damage with partial updates. It commonly contains:

- `actionToPerform`
- `structuredSettings`
- `splittingSettings`
- `storeInMultimodalColumn`
- `reExtractUnmodifiedDocuments`

Preserve unknown nested fields unless intentionally changing extraction behavior.

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `documentSplittingMode` | no | `enum` | Observed: `CHARACTERS_BASED` |
| `chunkSizeCharacters` | no | `integer` | Observed: `3000` |
| `chunkOverlapCharacters` | no | `integer` | Observed: `120` |
| `vectorStoreUpdateMethod` | no | `enum` | Observed: `SMART_OVERWRITE` |
| `clearVectorStore` | no | `boolean` | Preserve unless explicitly resetting the KB. |
| `metadataColumns` | no | `list<object>` | Empty in observed snapshot. |
| `userDefinedMetadataColumns` | no | `list<object>` | Empty in observed snapshot. |

## Canonical Settings Examples (Trimmed)

**Text-only** (`MANAGED_TEXT_ONLY`) — KB output only, no images folder:

```json
{
  "params": {
    "extractionMode": "MANAGED_TEXT_ONLY",
    "defaultVlmId": "openai:<connection>:<model>",
    "defaultImageHandlingMode": "IGNORE",
    "rules": [],
    "allOtherRule": {
      "actionToPerform": "DONOTEXTRACT",
      "splittingSettings": {
        "chunkSizeCharacters": 3000,
        "chunkOverlapCharacters": 120
      }
    }
  },
  "payload": {
    "chunkSizeCharacters": 3000,
    "chunkOverlapCharacters": 120,
    "clearVectorStore": false,
    "vectorStoreUpdateMethod": "SMART_OVERWRITE",
    "documentSplittingMode": "CHARACTERS_BASED"
  }
}
```

**Vision extraction** (`MANAGED_VISUAL_ONLY`) — requires both an images managed-folder output and a KB output:

```json
{
  "params": {
    "extractionMode": "MANAGED_VISUAL_ONLY",
    "defaultVlmId": "openai:<connection>:<model>",
    "defaultImageHandlingMode": "IGNORE",
    "rules": [],
    "allOtherRule": {
      "actionToPerform": "DONOTEXTRACT",
      "splittingSettings": {
        "chunkSizeCharacters": 3000,
        "chunkOverlapCharacters": 120
      }
    }
  },
  "payload": {
    "chunkSizeCharacters": 3000,
    "chunkOverlapCharacters": 120,
    "clearVectorStore": false,
    "vectorStoreUpdateMethod": "SMART_OVERWRITE",
    "documentSplittingMode": "CHARACTERS_BASED"
  }
}
```
