# Solution

```bash
dku dataset set-schema user_sessions -P {project} --definition '[{"name":"session_id","type":"string"},{"name":"user_id","type":"string"},{"name":"login_time","type":"string"},{"name":"logout_time","type":"string"}]'
dku recipe create-sort sort_sessions -i user_sessions --output-ds sessions_sorted -s user_id -s login_time -P {project}
dku recipe run sort_sessions --wait --auto-update-schema -P {project}
dku recipe create-window gap_window -i sessions_sorted --output-ds sessions_with_lag -k user_id --order-key login_time --compute 'lag:logout_time' -P {project}
dku recipe run gap_window --wait --auto-update-schema -P {project}
dku recipe create-prepare calc_gap -i sessions_with_lag --output-ds gap_durations -P {project}
dku recipe add-formula calc_gap --column gap_hours --expr 'diff(asDatetimeNoTz(login_time, "yyyy-MM-dd'\''T'\''HH:mm:ss"), asDatetimeNoTz(logout_time_lag, "yyyy-MM-dd'\''T'\''HH:mm:ss"), "hours")' -P {project}
dku recipe run calc_gap --wait --auto-update-schema -P {project}
dku recipe create-group user_max_gap -i gap_durations --output-ds user_gaps -k user_id --agg 'gap_hours:max' --rename 'gap_hours_max:max_gap_hours' --no-global-count -P {project}
dku recipe run user_max_gap --wait --auto-update-schema -P {project}
dku recipe create-filter filter_long_gaps -i user_gaps --output-ds long_session_gaps -f 'max_gap_hours > 48' -P {project}
dku recipe run filter_long_gaps --wait --auto-update-schema -P {project}
```
