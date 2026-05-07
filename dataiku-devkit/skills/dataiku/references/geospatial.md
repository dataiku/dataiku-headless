# Geospatial Data in Dataiku DSS

## Data Types

DSS supports two geospatial column types, both in **WKT** (Well-Known Text) format, **EPSG:4326** (WGS84):

| Type | WKT Example | Use Case |
|------|-------------|----------|
| `geopoint` | `POINT(2.3522 48.8566)` | Single location (store, customer, sensor) |
| `geometry` | `POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))` | Areas, routes, boundaries (delivery zones, regions) |

**Important:** WKT format is `POINT(longitude latitude)` — longitude comes first, which is the opposite of most APIs (lat, lon).

---

## Creating Geospatial Columns

### From lat/lon columns (most common)

```bash
# Add a prepare step that converts lat/lon to geopoint
dku recipe add-geopoint prep1 --lat-column latitude --lon-column longitude -P PROJ

# Or with a custom output column name
dku recipe add-geopoint prep1 --lat lat --lon lon --output-column location -P PROJ
```

### Via generic prepare step (advanced)

```bash
# GeoPointCreator with full params
dku recipe add-step prep1 --type GeoPointCreator \
  --params '{"lat_column": "lat", "lon_column": "lon", "out_column": "location"}' -P PROJ
```

---

## Geo Join Recipe

Joins two datasets using spatial relationships. **Always prefer this over Python haversine calculations.**

```bash
# Join stores with customers within 5km
dku recipe create-geojoin nearby_customers \
  -i stores -i customers \
  --output-ds store_customers \
  --operator WITHIN_DISTANCE --distance 5000 -u meter \
  -P PROJ

# Specify which geo columns to use
dku recipe create-geojoin geo_match \
  -i regions -i points \
  --output-ds matched \
  --operator CONTAINS \
  -g region_boundary -g point_location \
  -P PROJ
```

### Operators

| Operator | Description | Needs `--distance`? |
|----------|-------------|---------------------|
| `WITHIN_DISTANCE` | Rows within distance threshold (default) | Yes |
| `BEYOND_DISTANCE` | Rows farther than distance threshold | Yes |
| `INTERSECTS` | Geometries that overlap | No |
| `CONTAINS` | Left geometry contains right geometry | No |

### Distance Units

`meter` (default), `km`, `foot`, `yard`, `mile`, `nautical_mile`

---

## Fuzzy Join Recipe

Joins datasets using approximate string matching — useful for name deduplication, address matching, or linking messy text data.

```bash
# Match records by approximate name
dku recipe create-fuzzy-join dedup \
  -i source -i reference \
  --output-ds matched \
  --fuzzy-key company_name --max-distance 2 \
  -P PROJ

# Combine exact and fuzzy matching
dku recipe create-fuzzy-join addr_match \
  -i addresses1 -i addresses2 \
  --output-ds matched \
  --join-key postal_code --fuzzy-key street_name \
  --method JARO_WINKLER \
  -P PROJ
```

### Methods

| Method | Best For |
|--------|----------|
| `LEVENSHTEIN` (default) | General string matching, typos |
| `JARO_WINKLER` | Names and short strings |
| `NORMALIZED_LEVENSHTEIN` | Strings of varying lengths |

---

## Computing Distances

```bash
# Add distance column between two geopoint columns. Default unit is MILES;
# pass --unit KILOMETERS for km. Both inputs must be geopoint or geometry —
# use add-geopoint upstream to convert lat/lon pairs.
dku recipe add-geodistance prep1 \
  --from-column origin --to-column destination \
  --output-column distance_mi -P PROJ
```

---

## Prepare Recipe Geo Processors

All available via `dku recipe add-step --type TYPE --params '...'`:

| Processor | Purpose | Key Params |
|-----------|---------|------------|
| `GeoPointCreator` | lat/lon to geopoint | `lat_column`, `lon_column`, `out_column` |
| `GeoDistanceProcessor` | Distance between points | `input1`, `input2`, `output`, `outputUnit` (`MILES` / `KILOMETERS`), `compareTo` (`COLUMN`). NOT `*_column` suffixes — the `_column` form apply-schema-fails as `Empty column name`. CLI shortcut: `dku recipe add-geodistance --from A --to B --unit MILES -c dist` produces the right shape. |
| `ReverseGeocoder` | Coordinates to admin area | `inputColumn`, `outputColumn` |
| `GeoPointBufferCreator` | Buffer polygon around point | `column`, `radius`, `radiusUnit` |
| `GeoIPResolver` | IP address to geo info | **`inCol`** (NOT `inputColumn`), **`outColPrefix`** (NOT `outputColumn` — DSS adds `<prefix>_country`/`_region`/`_city`/etc. columns), and 10 `extract_*` boolean toggles: `extract_country`, `extract_country_code`, `extract_continent`, `extract_continent_code`, `extract_region`, `extract_city`, `extract_postal_code`, `extract_latitude`, `extract_longitude`, `extract_timezone`. Wrong field names are silently ignored — the step looks accepted but produces no extra columns. |
| `ChangeCRSProcessor` | Reproject coordinate system | `inputColumn`, `outputCRS` |

---

## GREL Geo Formulas

Use in `dku recipe add-formula` or prepare recipe filter expressions:

| Formula | Description |
|---------|-------------|
| `geoContains(wkt_polygon, geom)` | True if polygon contains the geometry |
| `geoSimplify(geom, tolerance)` | Simplify geometry (reduce point count) |
| `geoMakeValid(geom)` | Fix invalid geometries |

---

## Common Patterns

### Pattern: Store locator (find nearby points)

```bash
# 1. Create geopoints from lat/lon
dku recipe add-geopoint prep_stores --lat lat --lon lon -c store_location -P PROJ
dku recipe add-geopoint prep_customers --lat lat --lon lon -c cust_location -P PROJ

# 2. Geo join within 10km
dku recipe create-geojoin nearby \
  -i prepared_stores -i prepared_customers \
  --output-ds nearby_matches \
  --operator WITHIN_DISTANCE --distance 10000 -u meter \
  -P PROJ
```

### Pattern: Region assignment (point-in-polygon)

```bash
# Assign customers to sales regions
dku recipe create-geojoin region_assign \
  -i customers -i regions \
  --output-ds customer_regions \
  --operator CONTAINS \
  -g customer_location -g region_boundary \
  -P PROJ
```

---

## Gotchas

| Issue | Fix |
|-------|-----|
| WKT is `POINT(lon, lat)` not `POINT(lat, lon)` | Check column order — longitude first |
| All geometries must be EPSG:4326 | Use `ChangeCRSProcessor` to reproject before geo ops |
| Geo join requires geopoint/geometry columns | Use `add-geopoint` first if you only have lat/lon |
| Map charts require explicit geo column type | Columns must be typed as geopoint or geometry, not string |
| Reverse geocoding needs outbound internet | DSS must reach external geocoding services |
