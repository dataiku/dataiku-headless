---
name: prepare-geometry-info-extractor
description: "Observed JSON patterns for the GeometryInfoExtractor prepare/shaker processor."
---

# GeometryInfoExtractor Processor

Extract centroid, length, area columns from WKT geometry column. SQL pushdown only on PostgreSQL+PostGIS or Snowflake; other engines use DSS engine with bundled JTS. Length/area in CRS units; differ between planar (JTS) and spheroidal (Snowflake geography).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputCol` | yes | `string<column_name>` | Geometry-meaning column in WKT | Input geometry column; parsed via Geometry meaning. Bad-geometry rows emit warning, skipped. |
| `centroidCol` | no | `string<column_name> \| ""` | Any valid output column name \| empty string | Output centroid point; created after `inputCol` only when non-blank. SQL path=`GEOPOINT` via `ST_Centroid`; engine path writes WKT. |
| `lengthCol` | no | `string<column_name> \| ""` | Any valid output column name \| empty string | Output geometry length; created only when non-blank. CRS units (often degrees, not meters). SQL path=`DOUBLE` via `ST_Length`. |
| `areaCol` | no | `string<column_name> \| ""` | Any valid output column name \| empty string | Output geometry area; created only when non-blank. CRS units. SQL path=`DOUBLE` via `ST_Area`. Meaningful only for polygons. |

## Canonical Variant

```json
{
  "type": "GeometryInfoExtractor",
  "params": {
    "centroidCol": "geometry_centroid",
    "areaCol": "geometry_area",
    "lengthCol": "geometry_length",
    "inputCol": "geometry_wkt"
  }
}
```
