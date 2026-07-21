# Semantic models

A semantic model gives business meaning to project data for natural-language
querying. The model is a container; versions hold the substantive definition and
one version is active.

| Concept | Purpose |
|---|---|
| Entity | Business object backed by a dataset |
| Attribute | Dataset field with a business name and filtering/relationship role |
| Metric | Named business calculation over an entity |
| Filter | Reusable business subset and guidance |
| Relationship | Link between entities grounded in compatible keys and grain |
| Glossary term | Vocabulary and synonyms |
| Golden query | Curated natural-language question and expected query pattern |
| Distinct-value indexing | Makes useful business values recognizable in requests |

Inspect source schemas before defining entities, keys, metrics, or relationships.
Do not infer a relationship from matching names. Prefer a non-active version for
review before changing the active definition. Avoid broad distinct-value indexing
on high-cardinality identifiers or measures.
