# Solution

```bash
dku recipe create-split region_split -i orders --output-ds orders_east --output-ds orders_west --output-ds orders_north --output-ds orders_south --mode VALUES --column region --value-split East=0 --value-split West=1 --value-split North=2 --value-split South=3 -P {project}
dku recipe run region_split --wait --auto-update-schema -P {project}
```
