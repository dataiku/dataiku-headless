# Solution

```bash
dku recipe create-prepare clean_orders -i orders --output-ds cleaned_orders -P {project}
dku recipe add-rename clean_orders --from amount --to revenue -P {project}
dku recipe add-formula clean_orders --column revenue_with_tax --expr 'revenue * 1.2' -P {project}
dku recipe add-filter-rows clean_orders --formula 'revenue > 10' -P {project}
dku recipe run clean_orders -P {project} -w
```
