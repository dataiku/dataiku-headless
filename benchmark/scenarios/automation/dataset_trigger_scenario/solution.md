# Solution

```bash
dku scenario create orders_watchdog -P {project}
dku scenario add-trigger-dataset orders_watchdog --dataset orders --delay 600 --grace-delay 60 -P {project}
```
