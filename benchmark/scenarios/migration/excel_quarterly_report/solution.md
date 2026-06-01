# Solution: excel_quarterly_report

## Approach
Two branches: (1) Group recipe for department+category summary, then rename step to match expected column names.
(2) Passthrough prepare recipe (DateFormatter) to extract month, then Pivot recipe.

Note: no backslash line continuations — the runner executes each line as a separate command.

## Commands

```bash
dku recipe create-group expense_group -i migration_expenses --output-ds expense_grouped -k department -k category --agg "amount:sum,avg,count" --no-global-count -P {project}
dku recipe run expense_group --wait --auto-update-schema -P {project}
dku recipe create-filter expense_rename -i expense_grouped --output-ds expense_summary --filter-formula '1==1' -P {project}
dku recipe add-rename expense_rename --mappings '{"amount_sum":"total_amount","amount_avg":"average_amount","amount_count":"transaction_count"}' -P {project}
dku recipe run expense_rename --wait --auto-update-schema -P {project}
dku recipe create-filter expense_prep -i migration_expenses --output-ds expense_with_month --filter-formula '1==1' -P {project}
dku recipe add-step expense_prep --type DateFormatter --params '{"inCol":"date","outCol":"month","format":"yyyy-MM"}' -P {project}
dku recipe run expense_prep --wait --auto-update-schema -P {project}
dku recipe create-pivot expense_pivot -i expense_with_month --output-ds expense_monthly --row-key department --column-key month --value-column amount --agg-type SUM --no-global-count -P {project}
dku recipe run expense_pivot --wait --auto-update-schema -P {project}
```

## Notes
- `create-group --agg "amount:sum,avg,count"` creates `amount_sum`, `amount_avg`, `amount_count` — rename maps to expected names
- `create-filter --filter-formula '1==1'` creates a passthrough shaker recipe for `add-rename`/`add-step` to target
- DateFormatter uses `inCol`/`outCol` (not `column`/`outputColumn`) per CLAUDE.md gotcha
