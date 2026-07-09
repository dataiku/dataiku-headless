---
name: prepare-geo-distance-processor
description: "Observed JSON patterns for the GeoDistanceProcessor prepare/shaker processor."
---

# GeoDistanceProcessor

Compute the geographic distance between two geopoint columns or between a geopoint column and a fixed reference point.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `input1` | yes | `string<column_name>` | Any valid geopoint column name | First geopoint column (e.g. origin). |
| `input2` | conditional | `string<column_name>` | Any valid geopoint column name | Second geopoint column (e.g. destination). Required when `compareTo` is `COLUMN`. |
| `output` | yes | `string<column_name>` | Any valid output column name | Output column containing the computed distance as a numeric value. |
| `outputUnit` | yes | `enum` | `MILES` \| `KILOMETERS` | Unit of the output distance value. |
| `compareTo` | yes | `enum` | `COLUMN` \| `GEOPOINT` \| `GEOMETRY` | Whether to compute distance against another column, a fixed geopoint, or a fixed geometry. |
| `refLatitude` | conditional | `string` | A latitude value, e.g. `33.87` | Fixed-point latitude. Required when `compareTo` is `GEOPOINT`. |
| `refLongitude` | conditional | `string` | A longitude value, e.g. `-117.57` | Fixed-point longitude. Required when `compareTo` is `GEOPOINT`. |
| `refGeometry` | conditional | `string` | A WKT geometry, e.g. `POINT(-117.57 33.87)` | Fixed reference geometry. Required when `compareTo` is `GEOMETRY`. |

## Canonical Variants

### Distance between two geopoint columns in miles

```json
{
  "type": "GeoDistanceProcessor",
  "params": {
    "input1": "home_location",
    "input2": "work_location",
    "output": "commute_distance_miles",
    "outputUnit": "MILES",
    "compareTo": "COLUMN"
  }
}
```

### Distance between two geopoint columns in kilometers

```json
{
  "type": "GeoDistanceProcessor",
  "params": {
    "input1": "origin_geopoint",
    "input2": "destination_geopoint",
    "output": "distance_km",
    "outputUnit": "KILOMETERS",
    "compareTo": "COLUMN"
  }
}
```

### Distance from a column to a fixed geopoint

```json
{
  "type": "GeoDistanceProcessor",
  "params": {
    "input1": "store_location",
    "output": "distance_to_hq_miles",
    "outputUnit": "MILES",
    "compareTo": "GEOPOINT",
    "refLatitude": "40.7484",
    "refLongitude": "-73.9857"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `GeoDistanceProcessor`.
3. Input columns must contain valid geopoint values (created by `GeoPointCreator` or already in WKT `POINT(lon lat)` format).
4. When using `compareTo: "COLUMN"`, both `input1` and `input2` must be specified.
5. Keep the reference fields coherent with `compareTo`: `COLUMN` needs `input2`; `GEOPOINT` needs `refLatitude` + `refLongitude`; `GEOMETRY` needs `refGeometry`.
6. The output is a numeric value in the specified `outputUnit`; downstream formula steps can reference it directly.

## References

- Dataiku DSS: Compute distance between geopoints
  https://doc.dataiku.com/dss/latest/preparation/processors/geo-distance.html
