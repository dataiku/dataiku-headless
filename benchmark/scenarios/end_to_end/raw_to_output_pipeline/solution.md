# Solution

```bash
dku recipe create-join enrich_orders_products -i orders -i products --output-ds orders_enriched --join-key product_id -P {project}
dku recipe run enrich_orders_products --wait --auto-update-schema -P {project}
dku recipe create-group aggregate_sales_rollup -i orders_enriched --output-ds final_sales_rollup -k region -k category --agg amount:sum --no-global-count -P {project}
dku recipe run aggregate_sales_rollup --wait --auto-update-schema -P {project}
```
