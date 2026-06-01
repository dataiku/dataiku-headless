# Solution: alteryx_rfm_pipeline

## Approach
Two-recipe pipeline: Filter (remove zero-order customers) → Prepare with GREL formula steps (RFM scoring).
`create-filter` creates a shaker/prepare recipe; subsequent `add-formula` calls append GREL steps to it.

Note: no backslash line continuations — the runner executes each line as a separate command.

## Commands

```bash
dku recipe create-filter rfm_filter -i migration_rfm_customers --output-ds rfm_filtered --filter-formula 'numval("order_count_12mo") != 0' -P {project}
dku recipe run rfm_filter --wait --auto-update-schema -P {project}
dku recipe create-filter rfm_score -i rfm_filtered --output-ds rfm_output --filter-formula '1==1' -P {project}
dku recipe add-formula rfm_score --column recency_score --expr 'if(numval("days_since_last_order")<=30,5,if(numval("days_since_last_order")<=60,4,if(numval("days_since_last_order")<=90,3,if(numval("days_since_last_order")<=180,2,1))))' -P {project}
dku recipe add-formula rfm_score --column frequency_score --expr 'if(numval("order_count_12mo")>=15,5,if(numval("order_count_12mo")>=10,4,if(numval("order_count_12mo")>=5,3,if(numval("order_count_12mo")>=3,2,1))))' -P {project}
dku recipe add-formula rfm_score --column monetary_score --expr 'if(numval("total_spend_12mo")>=5000,5,if(numval("total_spend_12mo")>=2000,4,if(numval("total_spend_12mo")>=1000,3,if(numval("total_spend_12mo")>=500,2,1))))' -P {project}
dku recipe add-formula rfm_score --column rfm_score --expr 'recency_score + frequency_score + monetary_score' -P {project}
dku recipe add-formula rfm_score --column segment --expr 'if(rfm_score>=12,"Gold",if(rfm_score>=8,"Silver","Bronze"))' -P {project}
dku recipe add-formula rfm_score --column lifetime_value --expr 'numval("avg_order_value") * numval("order_count_12mo") * 3' -P {project}
dku recipe add-formula rfm_score --column at_risk --expr 'if((segment=="Gold" || segment=="Silver") && numval("days_since_last_order")>60,"true","false")' -P {project}
dku recipe run rfm_score --wait --auto-update-schema -P {project}
```

## Notes
- `create-filter` creates a shaker (Prepare) recipe — `add-formula` appends GREL steps to it
- `numval("col")` is required: bare column references in GREL return empty
- GREL steps execute in sequence, so later formulas can reference columns added by earlier steps
- The fixture has 100 rows; roughly 90 survive the zero-order filter (satisfies min: 80 check)
