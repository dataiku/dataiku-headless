# Solution

```bash
dku semantic-model create revenue_semantic_model -P {project}
dku semantic-model create-version revenue_semantic_model v1 -P {project}
dku semantic-model set-active-version revenue_semantic_model v1 -P {project}
dku semantic-model add-entity revenue_semantic_model --from-dataset customers --pk customer_id --index-values country,tier -P {project}
dku semantic-model add-entity revenue_semantic_model --from-dataset orders --pk order_id --index-values region -P {project}
dku semantic-model add-relationship revenue_semantic_model --from customers --to orders --on customer_id -P {project}
dku semantic-model update-index revenue_semantic_model --wait -P {project}
```
