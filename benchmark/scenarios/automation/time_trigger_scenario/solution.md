# Solution

```bash
dku scenario create daily_refresh -P {project}
dku scenario add-trigger daily_refresh --trigger '{"active":true,"type":"temporal","params":{"frequency":"Daily","hour":2,"minute":0,"repeatFrequency":1,"timezone":"SERVER"}}' -P {project}
```
