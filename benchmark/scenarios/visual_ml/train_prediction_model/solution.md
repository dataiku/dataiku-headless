# Solution

```bash
dku ml create-prediction customers tier -P {project} -o json | jq -r '"\(.analysis_id) \(.mltask_id)"' > /tmp/{project}_prediction_ids.txt
dku ml train $(cat /tmp/{project}_prediction_ids.txt) -P {project}
```
