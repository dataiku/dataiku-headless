# Solution

```bash
dku dataset set-schema orders -P {project} --definition '[{"name":"order_id","type":"string"},{"name":"customer_id","type":"string"},{"name":"product_id","type":"string"},{"name":"region","type":"string"},{"name":"amount","type":"double"},{"name":"date","type":"string"}]'
dku recipe create-sort copy_orders -i orders --output-ds orders_typed --sort-col order_id -P {project}
dku recipe run copy_orders --wait --auto-update-schema -P {project}
```
