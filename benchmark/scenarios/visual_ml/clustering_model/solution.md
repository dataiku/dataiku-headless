# Solution

```bash
dku ml create-clustering products -P {project} -o json | jq -r '"\(.analysis_id) \(.mltask_id)"' > /tmp/{project}_clustering_ids.txt
dku ml train $(cat /tmp/{project}_clustering_ids.txt) -P {project}
```
