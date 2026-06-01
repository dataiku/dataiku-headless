# Solution

```bash
dku recipe create-filter keep_hardware -i products --output-ds hardware_only --filter-formula "category == 'Hardware'" -P {project}
dku recipe run keep_hardware --wait --auto-update-schema -P {project}
dku recipe create-sort sort_hardware -i hardware_only --output-ds hardware_products_sorted --sort-col unit_price:desc -P {project}
dku recipe run sort_hardware --wait --auto-update-schema -P {project}
```
