# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- The benchmark intent includes a runnable LLM evaluation workflow with produced scoring outputs.
- The current executable path proves eval-store creation and recipe registration only.

```bash
dku evaluation-store create qa_eval_store --flavor LLM -P {project} -o json | jq -r '.id' > /tmp/{project}_eval_store_id.txt
dku dataset create eval_scored --type Filesystem -c filesystem_managed -P {project}
dku dataset create eval_metrics --type Filesystem -c filesystem_managed -P {project}
dku recipe create-llm-eval qa_eval_recipe --input qa_pairs --eval-store "$(cat /tmp/{project}_eval_store_id.txt)" --output-ds eval_scored --output-metrics eval_metrics --task-type QUESTION_ANSWERING --metrics answerRelevancy,faithfulness --input-col question --output-col answer --ground-truth-col expected --context-col context --completion-llm "$(dku llm list -P {project} -o json | jq -r '.[0].id')" --embedding-llm "$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P {project} -o json | jq -r '.[0].id')" -P {project}
```
