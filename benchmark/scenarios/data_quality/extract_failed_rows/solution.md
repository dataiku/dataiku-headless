# Solution

```bash
dku dq create customers --type not-empty --column customer_id -P {project}
dku dq compute customers -P {project}
dku recipe create-filter extract_bad -i customers --output-ds failed_customers --filter-formula "isNull(customer_id) || customer_id == ''" -P {project}
dku recipe run extract_bad --wait --auto-update-schema -P {project}
```
