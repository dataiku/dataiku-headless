# Solution

```bash
dku ml create-prediction orders amount --type REGRESSION -P {project} -o json | jq -r '"\(.analysis_id) \(.mltask_id)"' > /tmp/{project}_deploy_ids.txt
dku ml train $(cat /tmp/{project}_deploy_ids.txt) -P {project} -o json | jq -r '.model_ids[0]' > /tmp/{project}_deploy_model_id.txt
dku ml deploy $(cat /tmp/{project}_deploy_ids.txt) $(cat /tmp/{project}_deploy_model_id.txt) --name order_amount_model --train-dataset orders --no-redo-optimization -P {project}
```
