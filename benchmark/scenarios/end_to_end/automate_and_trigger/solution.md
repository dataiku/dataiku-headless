# Solution

```bash
dku recipe create-group aggregate_revenue_auto -i orders --output-ds automated_revenue_by_region -k region --agg amount:sum --no-global-count -P {project}
dku recipe run aggregate_revenue_auto --wait --auto-update-schema -P {project}
dku scenario create refresh_revenue_pipeline -P {project}
dku scenario add-trigger-dataset refresh_revenue_pipeline --dataset orders --delay 600 --grace-delay 60 -P {project}
```
