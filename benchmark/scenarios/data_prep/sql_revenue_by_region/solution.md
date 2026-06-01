# Solution

```bash
dku dataset set-schema orders -d 'order_id string, customer_id string, product_id string, region string, amount double, date date' -P {project}
dku dataset create revenue_by_region --type Filesystem -P {project}
dku recipe create-group revenue_calc -i orders --output-ds revenue_by_region -k region --agg "amount:sum" --no-global-count --rename "amount_sum:total_revenue" -P {project}
dku recipe run revenue_calc --wait --auto-update-schema -P {project}
```
