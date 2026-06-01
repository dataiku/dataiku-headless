# Solution

```bash
dku agent create router_agent --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="router_agent") | .id' > /tmp/{project}_router_agent_id.txt
dku agent-block add "$(cat /tmp/{project}_router_agent_id.txt)" --set-start -b '{"type":"LLM_REQUEST","id":"classify","llmId":"'"$(dku llm list -P {project} -o json | jq -r '.[0].id')"'","passConversationHistory":true,"systemPromptAfterHistory":"Classify the request as pricing or support. Return only one word.","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputKey":"intent","nextBlock":"route"}' -P {project}
dku agent-block add "$(cat /tmp/{project}_router_agent_id.txt)" -b '{"type":"ROUTING","id":"route","clausesBasedDecisions":[{"clause":{"type":"EXPRESSION","expression":{"expression":"state[\"intent\"] == \"pricing\""}},"nextBlock":"pricing_reply"}],"defaultNextBlockIfNoClauseMatch":"support_reply"}' -P {project}
dku agent-block add "$(cat /tmp/{project}_router_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"pricing_reply","templateType":"CEL_EXPANSION","template":"Pricing request received.","addToMessages":true}' -P {project}
dku agent-block add "$(cat /tmp/{project}_router_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"support_reply","templateType":"CEL_EXPANSION","template":"Support request received.","addToMessages":true}' -P {project}
```
