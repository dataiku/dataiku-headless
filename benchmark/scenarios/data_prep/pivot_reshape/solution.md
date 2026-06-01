# Solution

```bash
dku dataset set-schema orders -P {project} --definition '[{"name":"order_id","type":"string"},{"name":"customer_id","type":"string"},{"name":"product_id","type":"string"},{"name":"region","type":"string"},{"name":"amount","type":"double"},{"name":"date","type":"string"}]'
dku recipe create-join enrich_orders_products -i orders -i products --output-ds orders_enriched --join-key product_id -P {project}
dku recipe run enrich_orders_products --wait --auto-update-schema -P {project}
dku recipe create-pivot category_pivot -i orders_enriched --output-ds monthly_category_wide --row-key date --column-key category --value-column amount --agg-type SUM --no-global-count -P {project}
dku recipe run category_pivot --wait --auto-update-schema -P {project}
```
