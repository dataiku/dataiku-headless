# Solution

```bash
dku recipe create-embed embed_products_pipeline --input products --output-kb products_kb --embedding-llm "$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P {project} -o json | jq -r '.[0].id')" --embed-column category -P {project}
dku knowledge list -P {project} -o json | jq -r '.[] | select(.name=="products_kb") | .id' > /tmp/{project}_pipeline_kb_id.txt
dku rag create "Products RAG" --kb "$(cat /tmp/{project}_pipeline_kb_id.txt)" --llm "$(dku llm list -P {project} -o json | jq -r '.[0].id')" -P {project}
dku agent create genai_pipeline_agent --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="genai_pipeline_agent") | .id' > /tmp/{project}_genai_agent_id.txt
dku agent-tool create kb_search_tool --type VectorStoreSearch --knowledge-bank products_kb -P {project}
dku agent-tool list -P {project} -o json | jq -r '.[] | select(.name=="kb_search_tool") | .id' > /tmp/{project}_pipeline_tool_id.txt
python3 -c 'import json,pathlib; tool=pathlib.Path("/tmp/{project}_pipeline_tool_id.txt").read_text().strip(); block={"type":"STANDARD_REACT","id":"kb_react","tools":[{"toolRef":tool,"type":"EXPLICIT_TOOL","forwardContext":True,"returnSources":True,"enableSetArgs":False,"setArgs":[],"outputHandling":"ADD_TO_MESSAGES","treatAsJSON":False}],"systemPromptAfterHistory":"Use the KB search tool to answer product questions.","outputMode":"SAVE_TO_STATE","outputKey":"kb_answer","streamOutput":False,"defaultNextBlock":"emit_answer"}; open("/tmp/{project}_pipeline_block.json","w").write(json.dumps(block))'
dku agent-block add "$(cat /tmp/{project}_genai_agent_id.txt)" --set-start -b @/tmp/{project}_pipeline_block.json -P {project}
dku agent-block add "$(cat /tmp/{project}_genai_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"emit_answer","templateType":"CEL_EXPANSION","template":"{{state.kb_answer}}","addToMessages":true}' -P {project}
```
