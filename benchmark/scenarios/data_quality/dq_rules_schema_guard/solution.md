# Solution

```bash
# Add three DQ rules to the orders dataset
dku dq create orders -P {project} --type not-empty --column order_id --name "order_id not blank"
dku dq create orders -P {project} --type not-empty --column amount --name "amount not blank"
dku dq create orders -P {project} --type record-count --min 1 --name "at least one row"

# Run the rules to confirm they all pass
dku dq compute orders -P {project}
```
