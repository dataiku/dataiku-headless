---
name: prepare-tokenizer
description: "Observed JSON patterns for the Tokenizer prepare/shaker processor."
---

# Tokenizer Processor

Tokenize free-text column into words; optionally normalize, stem, remove stop words, sort. Emit as JSON array (`TO_JSON`), one row per token (`FOLD`), or one column per token (`SPLIT`). No SQL translation; DSS/stream engine only. `stem`/`clearStopWords` are language-specific, depend on `language`.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any existing column name | Input text column to tokenize. |
| `outCol` | conditional | `string<column_name>` | Any valid output column name | Output column for `TO_JSON`/`FOLD`; required for those. Ignored for `SPLIT`. |
| `operation` | no | `enum` | `TO_JSON` \| `FOLD` \| `SPLIT` | Default `TO_JSON`. TO_JSON=token array to `outCol`; FOLD=one output row per token; SPLIT=one column per token via `prefix`. |
| `prefix` | conditional | `string<any>` | Any string | Per-token column prefix (`prefix`+`0`, `prefix`+`1`, ...); required when `operation`=`SPLIT`. |
| `normalize` | no | `boolean` | `true` \| `false` | Lowercase, strip punctuation/accents, Unicode-normalize. Default `false`. |
| `stem` | no | `boolean` | `true` \| `false` | Reduce each word to stem (language-specific). Default `false`. |
| `clearStopWords` | no | `boolean` | `true` \| `false` | Remove stop words (language-specific). Default `false`. |
| `sortAlphabetically` | no | `boolean` | `true` \| `false` | Sort tokens alphabetically. Default `false`. |
| `language` | no | `enum` | One of ~70 codes incl. `english`, `english_2021`, `french`, `french_2021`, `german`, `spanish`, `chinese`, `japanese` | Default `english_2021`. Used only for stemming/stop-word removal. |

## Canonical Variant

```json
{
  "type": "Tokenizer",
  "params": {
    "inCol": "free_text",
    "outCol": "free_text_tokens",
    "operation": "TO_JSON",
    "normalize": true,
    "clearStopWords": true,
    "stem": false,
    "sortAlphabetically": false,
    "prefix": "",
    "language": "english_2021"
  }
}
```
