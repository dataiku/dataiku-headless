---
name: prepare-geo-point-buffer-processor
description: "Observed JSON patterns for the GeoPointBufferProcessor prepare/shaker processor."
---

# GeoPointBufferProcessor

Create circle or rectangle areas around geopoint values.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputColumn` | yes | `string<column_name>` | Any valid geopoint column name | Input center point column. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Output geometry column. |
| `shapeMode` | yes | `enum` | `CIRCLE` \| `RECTANGLE` | Shape generated around the geopoint. |
| `unitMode` | yes | `enum` | `KILOMETERS` \| `MILES` | Unit system for radius/width/height values. |
| `radius` | yes | `number` | Any numeric value | Circle size input; present in both observed variants. |
| `width` | yes | `number` | Any numeric value | Rectangle width input. |
| `height` | yes | `number` | Any numeric value | Rectangle height input. |

## Canonical Variants

### Circle buffer in kilometers

```json
{
  "type": "GeoPointBufferProcessor",
  "params": {
    "inputColumn": "geopoint",
    "outputColumn": "geopoint_area_1km_circle",
    "shapeMode": "CIRCLE",
    "unitMode": "KILOMETERS",
    "radius": 1.0,
    "width": 0.0,
    "height": 0.0
  }
}
```

### Rectangle buffer in miles

```json
{
  "type": "GeoPointBufferProcessor",
  "params": {
    "inputColumn": "geopoint",
    "outputColumn": "geopoint_area_5x10_mi_rectangle",
    "shapeMode": "RECTANGLE",
    "unitMode": "MILES",
    "radius": 1.0,
    "width": 5.0,
    "height": 10.0
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `GeoPointBufferProcessor`.
3. Keep `shapeMode`, `radius`, `width`, and `height` consistent to avoid unintended geometry.
4. Set distinct `outputColumn` names when defining multiple buffered area variants.
