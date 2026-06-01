# Solution

```bash
dku recipe create-join join_orders_products -i orders -i products --output-ds joined_data -k product_id -P {project}
dku recipe create-group group_by_region -i joined_data --output-ds region_totals -k region --agg 'amount:sum' --rename 'amount_sum:Total_Revenue' --no-global-count -P {project}
dku recipe create-sort sort_by_total -i region_totals --output-ds final_report --sort-col Total_Revenue:desc -P {project}
dku flow create-zone Ingestion -P {project}
dku flow create-zone Processing -P {project}
dku flow create-zone Reporting -P {project}
dku flow move orders products --zone Ingestion --type DATASET -P {project}
dku flow move join_orders_products group_by_region joined_data region_totals --zone Processing --type AUTO -P {project}
dku flow move sort_by_total final_report --zone Reporting --type AUTO -P {project}
dku recipe run sort_by_total -P {project} -w --type RECURSIVE_MISSING_ONLY_BUILD --auto-update-schema
```
