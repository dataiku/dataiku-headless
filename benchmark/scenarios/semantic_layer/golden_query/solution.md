# Solution

```bash
dku semantic-model create sales_semantic_model -P {project}
dku semantic-model create-version sales_semantic_model v1 -P {project}
dku semantic-model set-active-version sales_semantic_model v1 -P {project}
dku semantic-model add-entity sales_semantic_model --from-dataset orders --pk order_id --index-values region -P {project}
dku semantic-model add-entity sales_semantic_model --from-dataset products --pk product_id --index-values category,name -P {project}
dku semantic-model add-relationship sales_semantic_model --from orders --to products --on product_id -P {project}
dku semantic-model add-golden-query sales_semantic_model --name "monthly product revenue" --question "What was monthly product revenue?" --sql "SELECT o.date, p.category, SUM(o.amount) FROM orders o JOIN products p ON o.product_id = p.product_id GROUP BY o.date, p.category" -P {project}
dku semantic-model update-index sales_semantic_model --wait -P {project}
```
