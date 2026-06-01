# Solution

```bash
dku semantic-model create atu_contract_intelligence -P {project}
dku semantic-model create-version atu_contract_intelligence v1 -P {project}
dku semantic-model set-active-version atu_contract_intelligence v1 -P {project}

dku semantic-model add-entity atu_contract_intelligence --name Supplier --from-dataset suppliers --pk supplier_id --index-values supplier_name,category -P {project}
dku semantic-model add-entity atu_contract_intelligence --name Contract --from-dataset contracts --pk contract_id --index-values description -P {project}
dku semantic-model add-entity atu_contract_intelligence --name Invoice --from-dataset erp_postings --pk transaction_id --index-values description -P {project}
dku semantic-model add-entity atu_contract_intelligence --name CostCenter --from-dataset cost_centers --pk cost_center_code --index-values cost_center_name,department -P {project}
dku semantic-model add-entity atu_contract_intelligence --name GLAccount --from-dataset gl_accounts --pk gl_account --index-values gl_account_name -P {project}
dku semantic-model add-entity atu_contract_intelligence --name HeadcountSnapshot --from-dataset headcount_monthly --pk snapshot_month,department -P {project}

dku semantic-model add-relationship atu_contract_intelligence --from Contract --to Supplier --on supplier_id -P {project}
dku semantic-model add-relationship atu_contract_intelligence --from Invoice --to Supplier --on supplier_id -P {project}
dku semantic-model add-relationship atu_contract_intelligence --from Invoice --to Contract --expression "left.contract_ref = right.contract_id" -P {project}
dku semantic-model add-relationship atu_contract_intelligence --from Contract --to CostCenter --expression "left.cost_center = right.cost_center_code" -P {project}
dku semantic-model add-relationship atu_contract_intelligence --from Invoice --to CostCenter --expression "left.cost_center = right.cost_center_code" -P {project}
dku semantic-model add-relationship atu_contract_intelligence --from Contract --to GLAccount --on gl_account -P {project}
dku semantic-model add-relationship atu_contract_intelligence --from Invoice --to GLAccount --on gl_account -P {project}

dku semantic-model add-metric atu_contract_intelligence --entity Contract --name "Total Monthly Value" --expression "SUM(monthly_value_eur)" -P {project}
dku semantic-model add-metric atu_contract_intelligence --entity Contract --name "Total Annual Value" --expression "SUM(annual_value_eur)" -P {project}
dku semantic-model add-metric atu_contract_intelligence --entity Invoice --name "Total Spend" --expression "SUM(amount_eur)" -P {project}
dku semantic-model add-metric atu_contract_intelligence --entity Invoice --name "Transaction Count" --expression "COUNT(*)" -P {project}
dku semantic-model add-metric atu_contract_intelligence --entity HeadcountSnapshot --name "Total FTE" --expression "SUM(fte_count)" -P {project}

dku semantic-model update-index atu_contract_intelligence --wait -P {project}
```
