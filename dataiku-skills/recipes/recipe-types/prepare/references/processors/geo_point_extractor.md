---
name: prepare-geo-point-extractor
description: "Observed JSON patterns for the GeoPointExtractor prepare/shaker processor."
---

# GeoPointExtractor Processor

Extract latitude+longitude columns from GeoPoint-format column. DSS engine only, not SQL-translatable.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any GeoPoint-format column | Input column; parsed via internal GeoPoint parser. Unparseable values yield no output for that row. |
| `lat_col` | no | `string<column_name> \| ""` | Any valid output column name \| empty string | Output Latitude column, created after input column, meaning forced to Latitude. Empty string=no latitude output. |
| `lon_col` | no | `string<column_name> \| ""` | Any valid output column name \| empty string | Output Longitude column, created after input column, meaning forced to Longitude. Empty string=no longitude output. |

## Canonical Variant

```json
{
  "type": "GeoPointExtractor",
  "params": {
    "lat_col": "geo_point_lat",
    "column": "geo_point",
    "lon_col": "geo_point_lon"
  }
}
```
