---
name: prepare-change-crs-processor
description: "Observed JSON patterns for the ChangeCRSProcessor prepare/shaker processor."
---

# ChangeCRSProcessor Processor

Convert geometry values from one coordinate reference system (CRS) to another. Source and target CRS can be given either as a EPSG code (e.g., "EPSG:4326") or as a projected coordinate system WKT (e.g., "PROJCS[…]").

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `geomCol` | yes | `string<column_name>` | Any valid geometry/geopoint column name | Source geometry column to reproject. |
| `fromCRS` | yes | `string<crs_code>` | Any CRS code string (for example `EPSG:3857`) | Input/source CRS of values in `geomCol`. |
| `toCRS` | yes | `string<crs_code>` | Any CRS code string (for example `EPSG:4326`) | Target CRS for converted geometry values. |

## Canonical Variant

```json
{
  "type": "ChangeCRSProcessor",
  "params": {
    "fromCRS": "EPSG:3857",
    "geomCol": "geopoint",
    "toCRS": "EPSG:4326"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ChangeCRSProcessor`.
3. Ensure `fromCRS` matches the actual CRS currently stored in `geomCol`.
4. Confirm downstream geospatial steps expect `toCRS` after conversion.

## References

- Dataiku DSS: Change CRS (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/change-crs.html
