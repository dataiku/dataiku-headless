# Solution

```bash
dku dataset list -P {project} -o json
dku recipe create-filter high_value_orders -i {project}_SRC.orders --output-ds high_value_orders --filter-formula 'amount > 100' -P {project}
dku recipe run high_value_orders --wait --auto-update-schema -P {project}
```
