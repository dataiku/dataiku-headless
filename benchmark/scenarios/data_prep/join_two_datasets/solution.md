# Solution

```bash
dku recipe create-join enrich_orders -i orders -i customers --output-ds orders_with_customers --join-type LEFT --join-key customer_id -P {project}
dku recipe run enrich_orders --wait --auto-update-schema -P {project}
```
