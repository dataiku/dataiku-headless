# Solution

```bash
dku recipe create-topn top_10 -i products --output-ds top_products --sort-col unit_price:desc -P {project}
dku recipe run top_10 --wait --auto-update-schema -P {project}
```
