# Recipe families

Selection knowledge for naming the right transformation in a Cobuild prompt. This
is *which family fits an intent*, not how to author a payload — Cobuild owns
payloads now. Open it when a build or migration needs you to specify a recipe.

**Visual-first (the load-bearing rule).** Use a visual recipe family unless the user
explicitly requests code. Complexity, awkwardness, statefulness, or "cleaner in
code" are never reasons — a visual flow is reviewable on the graph, a code recipe is
a black box. If the user asks for code, it applies only to the part requested.

## Data prep (visual — the default)

| Intent | Family | Watch for |
|---|---|---|
| Clean / parse / standardize / derive columns | `prepare` | Row-local transforms; 100+ processors |
| Keyed match / enrich | `join`, `fuzzyjoin`, `geojoin` | A non-unique key multiplies rows — state the grain |
| Append compatible rows | `vstack` | Schemas must align |
| Merge rows into a target | `upsert` | Define the match key and update behavior |
| Change grain (aggregate) | `grouping` | Aggregation is lossy; name keys + measures |
| Partitioned analytics (rank, lag, running total) | `window` | Partition + order keys are the design |
| Long → wide reshape | `pivot` | Schema changes with the pivot column's values |
| Route rows to multiple outputs | `split` | Identify each output's condition |
| Sample / order / dedup / top-N | `sampling`, `sort`, `distinct`, `topn` | Distinct on a subset ≠ full-row dedup |
| Move data across storage | `sync`, `download`, `export` | Storage move, not transformation; `download`/`export` need a managed folder |

When reading or reviewing an existing `prepare` recipe's settings, the processor
catalog is in `recipe-shared/prepare-processors-overview.md`; formula-step syntax
and its traps are in `recipe-shared/dataiku-formula-language.md`.

## ML recipes

| Family | Does | Grounding |
|---|---|---|
| `generate_features` | Derives features via visual joins/transforms/aggregations | Preserve the entity grain |
| `prediction_scoring` | Applies a saved prediction model | Input schema must match the model's features |
| `clustering_scoring` | Assigns cluster labels from a trained model | — |
| `evaluation` | Scores a model against reference data | Name the reference outcome + success criterion |
| `standalone_evaluation` | Evaluates prediction outputs with no saved model | — |

Training recipes appear in the Flow after an ML analysis is deployed — configured
through the analysis, not as ordinary recipes. See
`ml-and-genai-objects.md` for model design and the red flags to raise.

## GenAI recipes

| Intent | Families | Required context |
|---|---|---|
| Prompt / classify / summarize text | `prompt`, `nlp_llm_*_classification`, `nlp_llm_summarization` | LLM or agent, source columns, expected output shape |
| Build retrieval content | `nlp_llm_rag_embedding`, `embed_documents`, `extract_content` | Knowledge Bank + LLM; dataset or managed folder |
| Customize / evaluate GenAI | `nlp_llm_finetuning`, `nlp_llm_evaluation`, `nlp_agent_evaluation` | Evaluation purpose, expected outputs, agent context |

A prompt-recipe request names the source columns, the intended outcome, the selected
LLM or agent, and the output format to validate. See `ml-and-genai-objects.md`.

## Code recipes (only on explicit request)

`python`, `r`, `sql_query`, `sql_script`, `pyspark`, `spark_scala`,
`spark_sql_query`, `shell`. Reach here only after the user explicitly asked for
code, and only for the part they asked to code. Inspect existing code before
requesting a change; carry code-env and project-library context into the prompt when
the recipe depends on them.
