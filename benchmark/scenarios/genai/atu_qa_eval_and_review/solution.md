# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- Production scores answers against five domain-specific LLM-judge metrics and
  runs the review against live agent outputs. The executable path proves the
  evaluation store, the scoring recipe, and the trait-based review exist and are
  wired; it does not run the evaluation or the review.

```bash
# Agent evaluation store + in-flow scoring of the recorded answers
# (eval-store `create -o json` emits the id on stdout; the store is not returned by `evaluation-store list`.
#  Each solution line runs in its own shell, so ids are passed via /tmp files rather than shell variables.)
dku evaluation-store create contract_eval_store --flavor AGENT -P {project} -o json | jq -r '.id' > /tmp/{project}_esid.txt
dku dataset create agent_scores -P {project}
dku dataset create agent_metrics -P {project}
dku recipe create-agent-eval agent_evaluate --input agent_answers --eval-store "$(cat /tmp/{project}_esid.txt)" --input-format PROMPT_RECIPE --output-ds agent_scores --output-metrics agent_metrics -P {project}

# Trait-based review linked to the agent
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="atu_contract_qa") | .id' > /tmp/{project}_atuqa_id.txt
dku agent-review create atu_contract_qa_review -P {project}
dku agent-review set-agent atu_contract_qa_review --agent "$(cat /tmp/{project}_atuqa_id.txt)" -P {project}
dku agent-review set-llm atu_contract_qa_review --llm "$(dku llm list -P {project} -o json | jq -r '.[0].id')" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Reference --description "Semantic equivalence to reference answer" --criteria "Does the answer match the reference answer in meaning?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Relevance --description "Addresses the asked question" --criteria "Does the answer address the question that was asked?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Completeness --description "All parts of multi-part questions are addressed" --criteria "Are all parts of the question answered?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Groundedness --description "Claims are supportable from retrieved contract and SAP data" --criteria "Is every claim supported by the retrieved contract and posting data?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Numeracy --description "EUR arithmetic and reconciliation correct" --criteria "Are the EUR figures and the arithmetic correct?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Cited --description "Every factual claim has an inline citation" --criteria "Does every factual claim carry an inline citation?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name Governed --description "Sources cited are approved governed sources" --criteria "Are all cited sources approved governed sources?" -P {project}
dku agent-review add-trait atu_contract_qa_review --name ScopeDiscipline --description "Out-of-scope questions are rejected and in-scope are answered" --criteria "Did the agent answer in-scope questions and refuse out-of-scope ones?" -P {project}
```
