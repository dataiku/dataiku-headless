---
name: prepare-geo-point-creator
description: "Observed JSON patterns for the GeoPointCreator prepare/shaker processor."
---

# GeoPointCreator

Create a geopoint column from separate latitude and longitude columns.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `lat_column` | yes | `string<column_name>` | Any valid numeric column name | Column containing latitude values. |
| `lon_column` | yes | `string<column_name>` | Any valid numeric column name | Column containing longitude values. |
| `out_column` | yes | `string<column_name>` | Any valid output column name | Output geopoint column. The value is stored as a WKT `POINT(lon lat)` string. |

## Canonical Variants

### Create a geopoint from lat/lon columns

```json
{
  "type": "GeoPointCreator",
  "params": {
    "lat_column": "latitude",
    "lon_column": "longitude",
    "out_column": "location"
  }
}
```

### Create two geopoints for distance calculation

```json
[
  {
    "type": "GeoPointCreator",
    "params": {
      "lat_column": "origin_lat",
      "lon_column": "origin_lon",
      "out_column": "origin_location"
    }
  },
  {
    "type": "GeoPointCreator",
    "params": {
      "lat_column": "dest_lat",
      "lon_column": "dest_lon",
      "out_column": "dest_location"
    }
  }
]
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `GeoPointCreator`.
3. Ensure `lat_column` and `lon_column` reference numeric columns containing valid WGS 84 coordinates.
4. Use distinct `out_column` names when creating multiple geopoint columns.
5. GeoPointCreator steps should precede any `GeoDistanceProcessor` or `GeoPointBufferProcessor` steps that consume the created geopoint column.

## References

- Dataiku DSS: Create GeoPoint from lat/lon
  https://doc.dataiku.com/dss/latest/preparation/processors/geo-point-creator.html
