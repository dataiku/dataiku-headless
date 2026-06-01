# Solution

```bash
dku semantic-model create orders_semantic_model -P {project}
dku semantic-model create-version orders_semantic_model v1 -P {project}
dku semantic-model set-active-version orders_semantic_model v1 -P {project}
dku semantic-model add-entity orders_semantic_model --from-dataset orders --pk order_id --index-values region -P {project}
dku semantic-model add-metric orders_semantic_model --entity orders --name "Total Revenue" --expression "SUM(amount)" -P {project}
dku semantic-model update-index orders_semantic_model --wait -P {project}
```
