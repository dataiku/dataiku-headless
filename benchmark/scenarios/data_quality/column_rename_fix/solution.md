# Solution

```bash
dku dataset schema inventory -P {project} -o json
dku recipe get-definition inventory_cleaned -P {project} -o json
dku recipe delete inventory_cleaned -P {project} --yes
dku recipe create-filter inventory_cleaned -i inventory --output-ds inventory_cleaned --filter-formula "quantity_available > 0" -P {project}
dku recipe run inventory_cleaned --wait --auto-update-schema -P {project}
dku dataset schema inventory_cleaned -P {project} -o json
dku dataset head inventory_cleaned -P {project} -n 5 -o json
```
