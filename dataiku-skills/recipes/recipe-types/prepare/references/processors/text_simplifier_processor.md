---
name: prepare-text-simplifier-processor
description: "Observed JSON patterns for the TextSimplifierProcessor prepare/shaker processor."
---

# TextSimplifierProcessor Processor

Perform various simplifications on a text column, including normalization, stemming, stop-word removal, and alphabetical token sorting.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input text column name | Input text column to simplify. |
| `outCol` | no | `string<column_name>` \| `""` | Any valid output column name \| empty string | Empty string applies simplification in place on `inCol`; non-empty writes to a new/output column. |
| `normalize` | yes | `boolean` | `true` \| `false` | Lowercase + remove punctuation/accents + Unicode NFD normalization. |
| `stem` | yes | `boolean` | `true` \| `false` | Language-specific stemming (word roots). |
| `clearStopWords` | yes | `boolean` | `true` \| `false` | Language-specific stop-word removal. |
| `sortAlphabetically` | yes | `boolean` | `true` \| `false` | Sort words alphabetically in the output text. |
| `language` | yes | `enum` | See `Supported language values` below. | Used by language-specific options (`stem`, `clearStopWords`). |

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

## Canonical Variants

### Normalize text into a new column

```json
{
  "type": "TextSimplifierProcessor",
  "params": {
    "inCol": "long_text",
    "outCol": "long_text_normalized",
    "sortAlphabetically": false,
    "normalize": true,
    "language": "english_2021",
    "clearStopWords": false,
    "stem": false
  }
}
```

### Normalize + stem + remove stop words

```json
{
  "type": "TextSimplifierProcessor",
  "params": {
    "inCol": "long_text",
    "outCol": "long_text_normalized_stemmed_no_stop_words",
    "sortAlphabetically": false,
    "normalize": true,
    "language": "english_2021",
    "clearStopWords": true,
    "stem": true
  }
}
```

### Stop-word removal with alphabetical sorting

```json
{
  "type": "TextSimplifierProcessor",
  "params": {
    "inCol": "long_text",
    "outCol": "long_text_fr_stop_words_sorted_alphabetically",
    "sortAlphabetically": true,
    "normalize": false,
    "language": "french_2021",
    "clearStopWords": true,
    "stem": false
  }
}
```

### In-place normalization

```json
{
  "type": "TextSimplifierProcessor",
  "params": {
    "inCol": "long_text",
    "outCol": "",
    "sortAlphabetically": false,
    "normalize": true,
    "language": "english_2021",
    "clearStopWords": false,
    "stem": false
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `TextSimplifierProcessor`.
3. Keep `language` coherent when `stem` or `clearStopWords` is enabled.
4. Use `outCol=""` only when in-place overwrite is intentional.

## References

- Dataiku DSS: Simplify text (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/simplify-text.html#simplify-text
