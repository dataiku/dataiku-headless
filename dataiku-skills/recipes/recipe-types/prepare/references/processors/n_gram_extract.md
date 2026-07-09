---
name: prepare-n-gram-extract
description: "Observed JSON patterns for the NGramExtract prepare/shaker processor."
---

# NGramExtract Processor

Extract word n-grams from text column; emit as JSON array / one row per n-gram / one column per n-gram. Not SQL-translatable; stream engine only (Snowflake-targeted recipe falls back to DSS).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any existing text column name | Input column; n-grams extracted from it. |
| `outCol` | no | `string<column_name>` \| `""` | Any valid output column name or empty string | Empty=in-place on `inCol`. Used for `TO_JSON`/`FOLD`; ignored for `SPLIT`. |
| `nmin` | yes | `integer` | `2`..`10` | Smallest terms per n-gram. Default `2`. |
| `nmax` | yes | `integer` | `2`..`10` | Largest terms per n-gram. Default `2`. Must be `>= nmin` to produce output. |
| `skip` | no | `boolean` | `true` \| `false` | Also compute skip n-grams (non-adjacent terms). Default `false`; greatly increases output size. |
| `sentenceSplit` | no | `boolean` | `true` \| `false` | Compute n-grams on blocks split by `.,:;()?!` and newlines. Default `true`. |
| `operation` | conditional | `enum` | `TO_JSON` \| `FOLD` \| `SPLIT` | Output mode; UI default `TO_JSON`. `TO_JSON`=JSON array; `FOLD`=one row per n-gram (copies other columns); `SPLIT`=one column per n-gram. |
| `prefix` | conditional | `string<any>` | Any valid column-name prefix | Generated-column prefix; required for `SPLIT`. Empty defaults at runtime to `inCol + "_"`. |
| `normalize` | no | `boolean` | `true` \| `false` | Lowercase; strip punctuation+accents; Unicode NFD normalize. Default `true` here. |
| `stem` | no | `boolean` | `true` \| `false` | Stem each word (Snowball). Default `false`; throws if `language` unsupported for stemming. |
| `clearStopWords` | no | `boolean` | `true` \| `false` | Remove language-specific stop words before extraction. Default `true` here. |
| `sortAlphabetically` | no | `boolean` | `true` \| `false` | Sort words alphabetically within text. Default `false`. |
| `language` | no | `enum` | See `Supported language values` below | Language for stemming+stop words. Default `english_2021`; revision suffix (`_YYYY`) stripped for stemmer lookup. |

## Supported language values

```text
afrikaans
albanian
arabic
armenian
basque
bengali
bulgarian
catalan
chinese
chinese_traditional
croatian
czech
danish
dutch
dutch_2021
english
english_2021
estonian
finnish
french
french_2021
german
german_2021
greek
gujarati
hebrew
hindi
hungarian
icelandic
indonesian
irish
italian
italian_2021
japanese
kannada
korean
latvian
lithuanian
luxembourgish
macedonian
malayalam
marathi
nepali
norwegian
persian
polish
portuguese
portuguese_2021
romanian
russian
sanskrit
serbian
sinhala
slovak
slovenian
spanish
spanish_2021
swedish
tagalog
tamil
tatar
telugu
thai
turkish
ukrainian
urdu
vietnamese
yoruba
```

## Canonical Variant

```json
{
  "type": "NGramExtract",
  "params": {
    "inCol": "free_text",
    "outCol": "free_text_ngrams",
    "nmin": 2,
    "nmax": 3,
    "skip": false,
    "sentenceSplit": true,
    "operation": "TO_JSON",
    "prefix": "",
    "normalize": true,
    "stem": false,
    "clearStopWords": true,
    "sortAlphabetically": false,
    "language": "english_2021"
  }
}
```
