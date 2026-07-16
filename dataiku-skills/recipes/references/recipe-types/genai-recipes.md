---
name: genai-recipes
description: Conceptual guide to selecting and interpreting Dataiku visual GenAI recipes for Cobuild requests.
---

# GenAI Recipes

Read this reference when a Flow transformation uses an LLM or agent, processes documents, creates retrieval content, or evaluates GenAI outputs. Read the supporting LLM, Knowledge Bank, managed-folder, or agent skill that applies to the selected recipe.

| Intent | Recipe types | Required context |
| --- | --- | --- |
| Prompt and transform text | `prompt`, `nlp_llm_model_provided_classification`, `nlp_llm_user_provided_classification`, `nlp_llm_summarization` | LLM or agent, source columns, expected output, and validation needs. |
| Build retrieval content | `nlp_llm_rag_embedding`, `embed_documents`, `extract_content` | Knowledge Bank and LLM context; datasets or managed folders as applicable. |
| Customize or evaluate GenAI | `nlp_llm_finetuning`, `nlp_llm_evaluation`, `nlp_agent_evaluation` | Evaluation purpose, expected outputs, and LLM or agent context. |

## Selection Notes

- A prompt recipe request should identify source columns, the prompt's intended outcome, the selected LLM or agent, and any expected output format or validation.
- Retrieval recipes differ between dataset-based embeddings and document-folder ingestion. Inspect the Knowledge Bank and source object before requesting a change.
- LLM and agent evaluation require evaluation-ready outputs. Agent evaluation also requires existing agent context.
