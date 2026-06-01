# Solution

```bash
dku dataset create nearby_stores --type UploadedFiles -P {project}
dku recipe create-geojoin find_nearby -i stores -i warehouses --output-ds nearby_stores --op WITHIN_DISTANCE --distance 200 --distance-unit km -P {project}
```
