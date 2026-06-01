# Solution

```bash
dku dataset set-schema orders -P {project} --definition '[{"name":"order_id","type":"string"},{"name":"customer_id","type":"string"},{"name":"product_id","type":"string"},{"name":"region","type":"string"},{"name":"amount","type":"double"},{"name":"date","type":"string"}]'
dku recipe create-group aggregate_revenue -i orders --output-ds revenue_by_region -k region --agg amount:sum --no-global-count -P {project}
dku recipe run aggregate_revenue --wait --auto-update-schema -P {project}
```
