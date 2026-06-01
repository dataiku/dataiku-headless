# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- Intent is a usable contract assistant: embedding build, live retrieval, tool
  invocation and citation. The executable path proves object creation and graph
  wiring only.

```bash
# Knowledge bank from the contract documents (vector-store backed)
dku recipe create-embed embed_contract_docs --input contract_docs --output-kb contracts_kb --embedding-llm "$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P {project} -o json | jq -r '.[0].id')" --embed-column doc_text -P {project}

# Structured agent
dku agent create atu_contract_qa --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="atu_contract_qa") | .id' > /tmp/{project}_atuqa_id.txt

# Two grounding tools: knowledge-base search + structured contract lookup
dku agent-tool create search_contracts_kb --type VectorStoreSearch --kb "$(dku knowledge list -P {project} -o json | jq -r '.[] | select(.name=="contracts_kb") | .id')" -P {project}
dku agent-tool create contract_lookup --type DatasetRowLookup --dataset contracts -P {project}
dku agent-tool list -P {project} -o json | jq -r '.[] | select(.name=="search_contracts_kb") | .id' > /tmp/{project}_kbtool_id.txt
dku agent-tool list -P {project} -o json | jq -r '.[] | select(.name=="contract_lookup") | .id' > /tmp/{project}_dstool_id.txt

# Tool-calling loop wired to BOTH tools
python3 -c 'import json,pathlib; kb=pathlib.Path("/tmp/{project}_kbtool_id.txt").read_text().strip(); ds=pathlib.Path("/tmp/{project}_dstool_id.txt").read_text().strip(); mk=lambda t:{"toolRef":t,"type":"EXPLICIT_TOOL","forwardContext":True,"returnSources":True,"enableSetArgs":False,"setArgs":[],"outputHandling":"ADD_TO_MESSAGES","treatAsJSON":False}; block={"type":"STANDARD_REACT","id":"qa_block","tools":[mk(kb),mk(ds)],"systemPromptAfterHistory":"You are the ATU contract intelligence assistant. Search the contract knowledge base for relevant terms and use the contract lookup tool to pull exact records before answering. Always cite the contract ID you used.","outputMode":"SAVE_TO_STATE","outputKey":"contract_answer","streamOutput":False,"defaultNextBlock":"emit_answer"}; open("/tmp/{project}_qa_block.json","w").write(json.dumps(block))'
dku agent-block add "$(cat /tmp/{project}_atuqa_id.txt)" --set-start -b @/tmp/{project}_qa_block.json -P {project}
dku agent-block add "$(cat /tmp/{project}_atuqa_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"emit_answer","templateType":"CEL_EXPANSION","template":"{{state.contract_answer}}","addToMessages":true}' -P {project}
```
