---
name: semantic-models
description: Understand and inspect Dataiku semantic models and their versions, then use grounded context for Cobuild semantic-model work. Use when reviewing business data definitions or planning semantic-model changes.
---

# Semantic Models

Use this guide to understand existing semantic models and plan grounded semantic-model work through Cobuild.

Apply the shared operating rules in `../SKILL.md` for routing, grounding, and validation.

## Semantic Model Concepts

A semantic model gives business meaning to project data so natural-language questions can be translated into more accurate queries.

A model is a container with one or more versions. A version contains the substantive business definition, and one version is active. Versions define entities backed by datasets, their attributes, metrics, filters, relationships, glossary terms, golden queries, and distinct-value indexing behavior.

Creating or editing a non-active version allows deliberate review before activation. Distinct-value indexing can help resolve useful business dimensions, but should not be applied indiscriminately to high-cardinality identifiers or measures.

Creation, versioning, activation, indexing, and deletion route through Cobuild.

| Concept | Purpose |
| --- | --- |
| Model and version | A model is the named container; versions hold its substantive definition. One version is active. |
| Entity | A business object mapped to a dataset, such as customers, orders, or products. |
| Attribute | A named dataset field with business meaning. Attributes can be used for selection, filtering, and relationships. |
| Metric | A named business calculation over an entity. |
| Filter | A reusable business subset with guidance about when it applies. |
| Relationship | A business relationship between entities, grounded in compatible keys and data grain. |
| Glossary term | Business vocabulary and synonyms that clarify user language. |
| Golden query | A curated natural-language question and expected query pattern that guides query generation. |
| Distinct-value indexing | Indexing of useful business values so they can be recognized in user requests. |

Ground entities and attributes in inspected dataset schemas. Validate entity grain and key behavior before describing a relationship, and prefer a reviewable version before changing an active semantic definition used by consumers.

## Workflow

1. Use `list_semantic_models` to discover models, versions, and the active version.
2. Use `get_semantic_model_version_settings` to inspect a selected version's business definition.
3. Inspect source datasets and schemas before requesting entity, attribute, metric, filter, or relationship changes.
4. Decide whether a request should change the active version or create a version for review first.
5. Route semantic-model creation, versioning, activation, indexing, and deletion through `./cobuild.md`.

## Supporting Context

- Entity datasets and schemas: `./datasets.md`
- Source Flow context: `./projects.md` and `./recipes.md`
- LLM or semantic-query use cases: `./llms-and-knowledge-banks.md`

## Preferred Tools

- `list_semantic_models`
- `get_semantic_model_version_settings`

## Safety Rules

- Preserve the active version unless activation is explicitly requested.
- Do not infer primary keys or relationships from names alone; inspect source datasets.
- Avoid indiscriminate distinct-value indexing, especially for high-cardinality identifiers and measures.
- Preserve existing business vocabulary, golden queries, and relationships unless the requested change requires them to change.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct semantic-model mutation workflows here.
