# Solution

```bash
dku agent create stateful_agent --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="stateful_agent") | .id' > /tmp/{project}_stateful_agent_id.txt
dku agent-block add "$(cat /tmp/{project}_stateful_agent_id.txt)" --set-start -b '{"type":"SET_STATE_ENTRIES","id":"init_state","entriesToSet":[{"secret":false,"key":"status","value":"'\''collecting'\''"}],"nextBlock":"capture"}' -P {project}
dku agent-block add "$(cat /tmp/{project}_stateful_agent_id.txt)" -b '{"type":"LLM_REQUEST","id":"capture","llmId":"'"$(dku llm list -P {project} -o json | jq -r '.[0].id')"'","passConversationHistory":true,"systemPromptAfterHistory":"Return a one-line summary of the conversation.","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputKey":"summary","nextBlock":"emit_state"}' -P {project}
dku agent-block add "$(cat /tmp/{project}_stateful_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"emit_state","templateType":"CEL_EXPANSION","template":"{{state.status}} :: {{state.summary}}","addToMessages":true}' -P {project}
```
