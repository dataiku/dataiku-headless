---
name: llms-and-knowledge-banks
description: Understand and inspect Dataiku LLMs, Knowledge Banks, and Retrieval-Augmented LLMs. Use when an agent must gather existing GenAI object context before asking Cobuild to create or modify project assets.
---

# LLMs And Knowledge Banks

Use this skill to understand and inspect existing Dataiku LLMs, Knowledge Banks, and Retrieval-Augmented LLMs.

## GenAI Object Concepts

An LLM is a configured model available for capabilities such as text completion, embeddings, reranking, or image generation. Its available purposes determine whether it is suitable for a particular GenAI task.

A Knowledge Bank stores indexed content for retrieval. Its configuration determines the embedding model, vector-store behavior, metadata schema, filtering capabilities, and other retrieval behavior.

A Retrieval-Augmented LLM combines an LLM with a Knowledge Bank and retrieval settings. It uses relevant retrieved content to ground responses.

Knowledge Banks and RAG LLMs are project objects. Reproducible GenAI flow steps that create, populate, or update Knowledge Bank content belong to the recipes skill tree rather than this skill.

## Workflow

1. Use `list_llms` to discover available LLMs and `get_llm_info` to inspect a selected model's capabilities and configuration.
2. Use `list_knowledge_banks` to discover Knowledge Banks and `get_knowledge_bank_settings` to inspect a selected bank.
3. Use `search_knowledge_bank` only when validating retrieved content, diagnosing retrieval relevance, or gathering context for a retrieval change.
4. Use `list_retrieval_augmented_llms` to discover RAG LLMs and `get_retrieval_augmented_llm_settings` to inspect a selected object.
5. Route Knowledge Bank and RAG-LLM creation, edits, deletion, and builds through `./dataiku-skills/cobuild/SKILL.md`.
6. Route GenAI flow-step creation or changes through `./dataiku-skills/recipes/SKILL.md` and Cobuild.

## Preferred Tools

- `list_llms`
- `get_llm_info`
- `list_knowledge_banks`
- `get_knowledge_bank_settings`
- `search_knowledge_bank`
- `list_retrieval_augmented_llms`
- `get_retrieval_augmented_llm_settings`

## Safety Rules

- Discover LLM, Knowledge Bank, and RAG-LLM identifiers via tools; do not invent identifiers.
- Keep this skill read-only. Route Knowledge Bank and RAG-LLM changes through `./dataiku-skills/cobuild/SKILL.md`.
- Keep GenAI flow construction under `./dataiku-skills/recipes/SKILL.md`.
- Inspect a Knowledge Bank's settings before interpreting search results or requesting a retrieval configuration change.
