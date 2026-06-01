# Solution

```bash
dku agent create multi_step_agent --type STRUCTURED_AGENT -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="multi_step_agent") | .id' > /tmp/{project}_multi_step_agent_id.txt
dku agent-block add "$(cat /tmp/{project}_multi_step_agent_id.txt)" --set-start -b '{"type":"SET_STATE_ENTRIES","id":"init","entriesToSet":[{"secret":false,"key":"status","value":"'\''ready'\''"}],"nextBlock":"summarize"}' -P {project}
dku agent-block add "$(cat /tmp/{project}_multi_step_agent_id.txt)" -b '{"type":"LLM_REQUEST","id":"summarize","llmId":"'"$(dku llm list -P {project} -o json | jq -r '.[0].id')"'","passConversationHistory":true,"systemPromptAfterHistory":"Summarize the user request in one sentence.","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputKey":"summary","nextBlock":"emit"}' -P {project}
dku agent-block add "$(cat /tmp/{project}_multi_step_agent_id.txt)" -b '{"type":"EMIT_OUTPUT","id":"emit","templateType":"CEL_EXPANSION","template":"State={{state.status}} Summary={{state.summary}}","addToMessages":true}' -P {project}
```
