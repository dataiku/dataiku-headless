# Solution

```bash
dku agent-tool create customer_lookup --type DatasetRowLookup --dataset customers -P {project}
dku agent list -P {project} -o json | jq -r '.[] | select(.name=="customer_assistant") | .id' > /tmp/{project}_agent_id.txt
dku agent set-prompt "$(cat /tmp/{project}_agent_id.txt)" --prompt "You are a helpful customer assistant." --new-version --activate -P {project}
dku agent add-tool "$(cat /tmp/{project}_agent_id.txt)" --tool customer_lookup --new-version -P {project}
```
