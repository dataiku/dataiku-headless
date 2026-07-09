---
name: prepare-geo-ip-resolver
description: "Observed JSON patterns for the GeoIPResolver prepare/shaker processor."
---

# GeoIPResolver Processor

Resolve an IP address column into geographical attributes (country, city, lat/lng, timezone, etc.). Each requested attribute produces a new column named `{outColPrefix}{attribute}` (e.g., `outColPrefix: "ip"` + `extract_country: true` → column `ipcountry`).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input column name | Input column holding IP address strings (IPv4/IPv6). |
| `outColPrefix` | yes | `string` | Any non-empty string | Prefix prepended to each extracted attribute name to form output column names. |
| `extract_country` | no | `bool` | `true` / `false` | Emit `{prefix}country` with country name. |
| `extract_countrycode` | no | `bool` | `true` / `false` | Emit `{prefix}country_code` (ISO 3166-1 alpha-2). |
| `extract_countrycode3` | no | `bool` | `true` / `false` | Emit `{prefix}country_code3` (ISO 3166-1 alpha-3). |
| `extract_continentcode` | no | `bool` | `true` / `false` | Emit `{prefix}continent_code`. |
| `extract_region` | no | `bool` | `true` / `false` | Emit `{prefix}region` (and related region columns). |
| `extract_city` | no | `bool` | `true` / `false` | Emit `{prefix}city`. |
| `extract_postalcode` | no | `bool` | `true` / `false` | Emit `{prefix}postal_code`. |
| `extract_latlng` | no | `bool` | `true` / `false` | Emit `{prefix}latitude` and `{prefix}longitude`. |
| `extract_geopoint` | no | `bool` | `true` / `false` | Emit `{prefix}geopoint` (DSS geopoint type). |
| `extract_timezone` | no | `bool` | `true` / `false` | Emit `{prefix}timezone`. |

At least one `extract_*` flag should be `true` or the processor produces no output columns.

## Canonical Variant

```json
{
  "type": "GeoIPResolver",
  "params": {
    "inCol": "ip",
    "outColPrefix": "ip",
    "extract_country": true,
    "extract_countrycode": false,
    "extract_countrycode3": false,
    "extract_continentcode": false,
    "extract_region": false,
    "extract_city": false,
    "extract_postalcode": false,
    "extract_latlng": false,
    "extract_geopoint": false,
    "extract_timezone": false
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. `inCol` must be a raw IP string column; do not point at a derived column.
3. Pick `outColPrefix` to avoid clashes with existing column names — output columns are `{prefix}{attribute}`.
4. Enable only the attributes you actually need; each adds a column to the output schema.
5. Requires a configured DSS GeoIP database on the instance; rows with unresolvable IPs yield empty values rather than errors.
