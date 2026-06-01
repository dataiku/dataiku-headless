# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- Intent is a working self-serve strategist: live semantic querying, retrieval,
  brief generation and runtime budget flagging. The executable path proves the
  semantic model, knowledge bank, agent, knowledge-base tool, tool-calling loop
  and the encoded governance threshold exist and are wired.

```bash
# Semantic layer over the campaign tables
dku semantic-model create wpp_campaign_schema -P {project}
dku semantic-model create-version wpp_campaign_schema v1 -P {project}
dku semantic-model set-active-version wpp_campaign_schema v1 -P {project}
dku semantic-model add-entity wpp_campaign_schema --name Campaign --from-dataset campaigns --pk campaign_id --index-values campaign_name,brand,market -P {project}
dku semantic-model add-entity wpp_campaign_schema --name Channel --from-dataset channels --pk channel_id --index-values channel_name,channel_type -P {project}
dku semantic-model add-entity wpp_campaign_schema --name Performance --from-dataset performance --pk campaign_id,channel_id -P {project}
dku semantic-model add-relationship wpp_campaign_schema --from Performance --to Campaign --on campaign_id -P {project}
dku semantic-model add-relationship wpp_campaign_schema --from Performance --to Channel --on channel_id -P {project}
dku semantic-model add-metric wpp_campaign_schema --entity Performance --name "Total Spend" --expression "SUM(spend_eur)" -P {project}
dku semantic-model update-index wpp_campaign_schema --wait -P {project}

# Brand-guide knowledge bank
dku recipe create-embed embed_wpp_brand_docs --input brand_docs --output-kb wpp_campaign_kb --embedding-llm "$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P {project} -o json | jq -r '.[0].id')" --embed-column doc_text -P {project}

# Governed strategist agent
dku agent create wpp_campaign_strategist --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="wpp_campaign_strategist") | .id' > /tmp/{project}_wpp_agent_id.txt
dku agent-tool create search_wpp_kb --type VectorStoreSearch --kb "$(dku knowledge list -P {project} -o json | jq -r '.[] | select(.name=="wpp_campaign_kb") | .id')" -P {project}
dku agent-tool create campaign_lookup --type DatasetRowLookup --dataset campaigns -P {project}
dku agent-tool list -P {project} -o json | jq -r '.[] | select(.name=="search_wpp_kb") | .id' > /tmp/{project}_wppkb_tool.txt
dku agent-tool list -P {project} -o json | jq -r '.[] | select(.name=="campaign_lookup") | .id' > /tmp/{project}_wppds_tool.txt
python3 -c 'import json,pathlib; kb=pathlib.Path("/tmp/{project}_wppkb_tool.txt").read_text().strip(); ds=pathlib.Path("/tmp/{project}_wppds_tool.txt").read_text().strip(); mk=lambda t:{"toolRef":t,"type":"EXPLICIT_TOOL","forwardContext":True,"returnSources":True,"enableSetArgs":False,"setArgs":[],"outputHandling":"ADD_TO_MESSAGES","treatAsJSON":False}; block={"type":"STANDARD_REACT","id":"strategist_block","tools":[mk(kb),mk(ds)],"systemPromptAfterHistory":"You are the WPP campaign strategist. Search the brand knowledge base and look up campaign records to produce a campaign brief with audience channel mix and cited sources. GOVERNANCE RULE: flag any campaign whose total budget exceeds EUR 5000000 as requiring governance review before delivering the brief.","outputMode":"SAVE_TO_STATE","outputKey":"campaign_brief","streamOutput":False,"defaultNextBlock":"emit_brief"}; open("/tmp/{project}_wpp_block.json","w").write(json.dumps(block))'
dku agent-block add "$(cat /tmp/{project}_wpp_agent_id.txt)" --set-start -b @/tmp/{project}_wpp_block.json -P {project}
dku agent-block add "$(cat /tmp/{project}_wpp_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"emit_brief","templateType":"CEL_EXPANSION","template":"{{state.campaign_brief}}","addToMessages":true}' -P {project}
```
