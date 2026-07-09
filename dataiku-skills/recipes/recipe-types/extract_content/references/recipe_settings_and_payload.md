---
name: extract-content-settings-and-payload-reference
description: "Observed params and payload structure for extract-content recipes."
---

# Extract Content Settings And Payload Reference

Use this reference for `extract_content` edits.

## Observed Settings Shape

In observed extract-content recipes:

- `params` controls extraction/VLM behavior
- `payload` controls whether images/screenshots are stored and the vector-store update behavior

Observed top-level `params` keys:

- `extractionMode`
- `defaultVlmId`
- `defaultImageHandlingMode`
- `rules`
- `allOtherRule`

Observed top-level `payload` keys:

- `storeImages`
- `storeScreenshots`
- `vectorStoreUpdateMethod`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `storeImages` | no | `boolean` | Observed: `false` |
| `storeScreenshots` | no | `boolean` | Observed: `false` |
| `vectorStoreUpdateMethod` | no | `enum` | Observed: `SMART_OVERWRITE` |

## Canonical Settings Example (Trimmed)

```json
{
  "params": {
    "extractionMode": "MANAGED_TEXT_ONLY",
    "defaultVlmId": "anthropic:<connection>:<model>",
    "defaultImageHandlingMode": "OCR",
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
    "storeImages": false,
    "storeScreenshots": false,
    "vectorStoreUpdateMethod": "SMART_OVERWRITE"
  }
}
```
