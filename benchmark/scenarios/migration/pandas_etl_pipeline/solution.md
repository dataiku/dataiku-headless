# Solution: pandas_etl_pipeline

## Approach
Four-recipe chain: Filter → Prepare (month) → Group → Rename → Sort.
Rename step after Group maps DSS default names to expected output column names.

Note: no backslash line continuations — the runner executes each line as a separate command.

## Commands

```bash
dku recipe create-filter tx_filter -i migration_transactions --output-ds tx_filtered --filter-formula 'val("amount") != "" && status == "completed"' -P {project}
dku recipe run tx_filter --wait --auto-update-schema -P {project}
dku recipe create-filter tx_prep -i tx_filtered --output-ds tx_with_month --filter-formula '1==1' -P {project}
dku recipe add-step tx_prep --type DateFormatter --params '{"inCol":"timestamp","outCol":"month","format":"yyyy-MM"}' -P {project}
dku recipe run tx_prep --wait --auto-update-schema -P {project}
dku recipe create-group tx_group -i tx_with_month --output-ds tx_grouped -k category -k region --agg "amount:sum,avg,count" --no-global-count -P {project}
dku recipe run tx_group --wait --auto-update-schema -P {project}
dku recipe create-filter tx_rename -i tx_grouped --output-ds tx_renamed --filter-formula '1==1' -P {project}
dku recipe add-rename tx_rename --mappings '{"amount_sum":"total_amount","amount_avg":"average_amount","amount_count":"transaction_count"}' -P {project}
dku recipe run tx_rename --wait --auto-update-schema -P {project}
dku recipe create-sort tx_sort -i tx_renamed --output-ds tx_summary --sort-col total_amount:desc -P {project}
dku recipe run tx_sort --wait --auto-update-schema -P {project}
```

## Notes
- `val("amount") != ""` catches null/empty amounts (DSS reads CSV nulls as empty strings)
- `create-filter --filter-formula '1==1'` creates a passthrough shaker recipe for `add-step`/`add-rename` to target
- `create-group` produces `amount_sum`/`amount_avg`/`amount_count` — rename maps to `total_amount`/`average_amount`/`transaction_count`
- DateFormatter uses `inCol`/`outCol` (not `column`/`outputColumn`) per CLAUDE.md gotcha
- `no_python_recipes` is optional: agents may use Python for the filter step
