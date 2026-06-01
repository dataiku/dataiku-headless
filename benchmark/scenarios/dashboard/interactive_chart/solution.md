# Solution

```bash
dku insight create "Revenue by Region" --type chart --dataset orders -P {project}
dku insight list -P {project} -o json | jq -r '.[] | select(.name=="Revenue by Region") | .id' > /tmp/{project}_chart_id.txt
dku insight set-chart-type "$(cat /tmp/{project}_chart_id.txt)" grouped_columns -P {project}
dku insight add-dimension "$(cat /tmp/{project}_chart_id.txt)" --column region -P {project}
dku insight add-measure "$(cat /tmp/{project}_chart_id.txt)" --column amount --agg SUM -P {project}
dku insight validate "$(cat /tmp/{project}_chart_id.txt)" -P {project}
dku dashboard create "Operations Dashboard" -P {project}
dku dashboard list -P {project} -o json | jq -r '.[] | select(.name=="Operations Dashboard") | .id' > /tmp/{project}_dash_id.txt
dku dashboard add-tile "$(cat /tmp/{project}_dash_id.txt)" --insight "$(cat /tmp/{project}_chart_id.txt)" -P {project}
```
