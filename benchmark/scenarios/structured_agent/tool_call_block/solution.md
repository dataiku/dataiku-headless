# Solution

```bash
dku agent create tool_agent --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="tool_agent") | .id' > /tmp/{project}_tool_agent_id.txt
dku agent-tool create customer_lookup --type DatasetRowLookup --dataset customers -P {project}
dku agent-tool list -P {project} -o json | jq -r '.[] | select(.name=="customer_lookup") | .id' > /tmp/{project}_customer_lookup_id.txt
python3 -c 'import json,pathlib; tool=pathlib.Path("/tmp/{project}_customer_lookup_id.txt").read_text().strip(); block={"type":"STANDARD_REACT","id":"lookup_block","tools":[{"toolRef":tool,"type":"EXPLICIT_TOOL","forwardContext":True,"returnSources":True,"enableSetArgs":False,"setArgs":[],"outputHandling":"ADD_TO_MESSAGES","treatAsJSON":False}],"systemPromptAfterHistory":"Use the dataset lookup tool to find customer details before answering.","outputMode":"SAVE_TO_STATE","outputKey":"lookup_results","streamOutput":False,"defaultNextBlock":"emit_results"}; open("/tmp/{project}_tool_block.json","w").write(json.dumps(block))'
dku agent-block add "$(cat /tmp/{project}_tool_agent_id.txt)" --set-start -b @/tmp/{project}_tool_block.json -P {project}
dku agent-block add "$(cat /tmp/{project}_tool_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"emit_results","templateType":"CEL_EXPANSION","template":"Lookup complete: {{state.lookup_results}}","addToMessages":true}' -P {project}
```
