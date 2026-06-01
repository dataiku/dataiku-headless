# Solution

```bash
dku insight create "Revenue by Region" --type chart --dataset orders -P {project}
dku insight create "Products by Category" --type chart --dataset products -P {project}
dku insight list -P {project} -o json | jq -r '.[] | select(.name=="Revenue by Region") | .id' > /tmp/{project}_revenue_id.txt
dku insight list -P {project} -o json | jq -r '.[] | select(.name=="Products by Category") | .id' > /tmp/{project}_products_id.txt
dku insight set-chart-type "$(cat /tmp/{project}_revenue_id.txt)" stacked_bars -P {project}
dku insight add-dimension "$(cat /tmp/{project}_revenue_id.txt)" --column region -P {project}
dku insight add-measure "$(cat /tmp/{project}_revenue_id.txt)" --column amount --agg SUM -P {project}
dku insight set-chart-type "$(cat /tmp/{project}_products_id.txt)" pie -P {project}
dku insight add-dimension "$(cat /tmp/{project}_products_id.txt)" --column category -P {project}
dku insight add-measure "$(cat /tmp/{project}_products_id.txt)" --column unit_price --agg SUM -P {project}
dku insight validate "$(cat /tmp/{project}_revenue_id.txt)" -P {project}
dku insight validate "$(cat /tmp/{project}_products_id.txt)" -P {project}
dku dashboard create "Analytics Board" -P {project}
dku dashboard list -P {project} -o json | jq -r '.[] | select(.name=="Analytics Board") | .id' > /tmp/{project}_dash_id.txt
dku dashboard add-tile "$(cat /tmp/{project}_dash_id.txt)" --insight "$(cat /tmp/{project}_revenue_id.txt)" -w 6 -P {project}
dku dashboard add-tile "$(cat /tmp/{project}_dash_id.txt)" --insight "$(cat /tmp/{project}_products_id.txt)" -w 6 -P {project}
```
