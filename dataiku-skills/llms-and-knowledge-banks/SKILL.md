---
name: llms-and-knowledge-banks
description: Inspect DSS LLMs, Knowledge Banks, and Retrieval-Augmented LLMs. Use when an agent must understand existing GenAI project objects before asking Cobuild to create or modify project assets.
---

# LLM Project Object Inspection

Use this skill to inspect existing LLM-related project objects.

## Workflow

1. Use `list_llms` and `get_llm_info` to inspect available LLMs.
2. Use `list_knowledge_banks`, `get_knowledge_bank_settings`, and `search_knowledge_bank` to inspect existing knowledge banks.
3. Use `list_retrieval_augmented_llms` and `get_retrieval_augmented_llm_settings` to inspect existing RAG LLMs.
4. Route Knowledge Bank and RAG-LLM creation or modification through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_llms`
- `get_llm_info`
- `list_knowledge_banks`
- `get_knowledge_bank_settings`
- `search_knowledge_bank`
- `list_retrieval_augmented_llms`
- `get_retrieval_augmented_llm_settings`

## Safety Rules

- Keep this skill focused on inspection and grounding for Cobuild prompts.
- Do not document direct Knowledge Bank or RAG-LLM mutation workflows here.
