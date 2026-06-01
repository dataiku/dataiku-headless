# Solution

```bash
dku scenario create order_pipeline -P {project}
dku scenario get-definition order_pipeline -P {project} -o json | jq -r '.id' > /tmp/{project}_scenario_id.txt
dku scenario add-trigger-dataset order_pipeline --dataset orders -P {project}
dku recipe run sort_orders -P {project} -w
dku scenario run order_pipeline -P {project} -w
dku scenario status order_pipeline -P {project} -o json
```
