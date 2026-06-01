# GeoPointCreator

**When:** Create a geopoint column from latitude/longitude columns. Use instead of manually formatting WKT in Python. Output is a WKT POINT in EPSG:4326 (WGS84) that can be used in geo join recipes and map charts.

**CLI shortcut:** `dku recipe add-geopoint RECIPE --lat-column lat --lon-column lon [--output-column geopoint] -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `lat_column` | Yes | Latitude column name |
| `lon_column` | Yes | Longitude column name |
| `out_column` | No | Output geopoint column name (default `"geopoint"`) |

```json
{"lat_column": "lat", "lon_column": "lon", "out_column": "geopoint"}
```
