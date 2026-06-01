# Solution

```bash
dku recipe create-distinct get_categories -i products --output-ds product_categories --on category -P {project}
dku recipe run get_categories --wait --auto-update-schema -P {project}
```
