# Solution

```bash
dku recipe create-filter filter_alpha -i room_bookings --output-ds alpha_occ -f 'room_id == "Alpha" && status == "Occupied"' -P {project}
dku recipe run filter_alpha --wait --auto-update-schema -P {project}
dku recipe create-filter filter_beta -i room_bookings --output-ds beta_occ -f 'room_id == "Beta" && status == "Occupied"' -P {project}
dku recipe run filter_beta --wait --auto-update-schema -P {project}
dku recipe create-prepare prep_alpha -i alpha_occ --output-ds alpha_ready -P {project}
dku recipe add-rename prep_alpha --from start_date --to alpha_start -P {project}
dku recipe add-rename prep_alpha --from end_date --to alpha_end -P {project}
dku recipe run prep_alpha --wait --auto-update-schema -P {project}
dku recipe create-prepare prep_beta -i beta_occ --output-ds beta_ready -P {project}
dku recipe add-rename prep_beta --from start_date --to beta_start -P {project}
dku recipe add-rename prep_beta --from end_date --to beta_end -P {project}
dku recipe run prep_beta --wait --auto-update-schema -P {project}
dku recipe create-join cross_ab -i alpha_ready -i beta_ready --output-ds ab_pairs --join-type CROSS -P {project}
dku recipe run cross_ab --wait --auto-update-schema -P {project}
dku recipe create-prepare compute_overlap -i ab_pairs --output-ds overlap_days -P {project}
dku recipe add-formula compute_overlap --column overlap_start --expr 'max(alpha_start, beta_start)' -P {project}
dku recipe add-formula compute_overlap --column overlap_end --expr 'min(alpha_end, beta_end)' -P {project}
dku recipe add-formula compute_overlap --column q2_start --expr 'inc(trunc(alpha_start, "years"), 3, "months")' -P {project}
dku recipe add-formula compute_overlap --column q2_end --expr 'inc(inc(trunc(alpha_start, "years"), 6, "months"), -1, "days")' -P {project}
dku recipe add-formula compute_overlap --column clipped_start --expr 'max(overlap_start, q2_start)' -P {project}
dku recipe add-formula compute_overlap --column clipped_end --expr 'min(overlap_end, q2_end)' -P {project}
dku recipe add-formula compute_overlap --column overlap_days --expr 'max(0, diff(clipped_end, clipped_start, "days"))' -P {project}
dku recipe run compute_overlap --wait --auto-update-schema -P {project}
dku recipe create-group sum_overlap -i overlap_days --output-ds room_overlap_total --agg 'overlap_days:sum' --no-global-count -P {project}
dku recipe run sum_overlap --wait --auto-update-schema -P {project}
```
