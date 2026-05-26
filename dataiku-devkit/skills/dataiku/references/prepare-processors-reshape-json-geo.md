# Prepare Processors: Reshape, JSON, Arrays, Geo, Enrichment

Processor details for reshape, JSON/array handling, geospatial enrichment, and Prepare-side joins.

### MultiColumnFold

**When:** Unpivot wide-to-long. Prefer over `pd.melt()`. Stock DSS — works on every instance.
**CLI shortcut:** `dku recipe add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ` (emits this type with `foldRemoveFoldedColumns: true`)

| Param | Required | Description |
|-------|----------|-------------|
| `columns` | Yes | Array of column names to fold |
| `foldNameColumn` | Yes | Output column for original column names |
| `foldValueColumn` | Yes | Output column for values |
| `foldRemoveFoldedColumns` | No | `true` to drop the folded source columns (pd.melt semantic); `false`/omit to keep them |

```json
{"columns": ["jan", "feb", "mar"], "foldNameColumn": "month", "foldValueColumn": "sales", "foldRemoveFoldedColumns": true}
```

### MultiColumnByPrefixFold

**When:** Same as `MultiColumnFold`, but the columns to fold are selected by a regex on the column name. Stock DSS.
**CLI shortcut:** `dku recipe add-fold RECIPE --pattern ".*_2025" --key-column year --value-column value -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `columnNamePattern` | Yes | Regex matching source column names |
| `columnNameColumn` | Yes | Output column for original column names |
| `columnContentColumn` | Yes | Output column for values |
| `foldRemoveFoldedColumns` | No | `true` to drop matched source columns |

```json
{"columnNamePattern": "score_.*", "columnNameColumn": "metric", "columnContentColumn": "value", "foldRemoveFoldedColumns": true}
```

> **Plugin variants:** `FoldColumnsByName` and `FoldColumnsByPattern` exist as plugin processors with similar semantics but different param names (`keyColumn`/`valueColumn` instead of `foldNameColumn`/`foldValueColumn`). Prefer the stock processors above — the plugin versions fail with `UnavailableTypeException` when the plugin is not installed.

---

### JSONFlattener

**When:** Flatten JSON object/array columns into separate columns.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Column containing JSON |
| `flattenArrays` | Yes | Also flatten arrays |
| `maxDepth` | Yes | Max nesting depth to flatten |
| `nullAsEmpty` | Yes | Treat null as empty string |
| `prefixOutputs` | Yes | Prefix output columns with path |
| `separator` | Yes | Separator between nested keys (e.g. `"_"`) |

```json
{"inCol": "metadata", "flattenArrays": false, "maxDepth": 10, "nullAsEmpty": true, "prefixOutputs": true, "separator": "_"}
```

---

### MemoryEquiJoiner

**When:** Lookup-style equi-join inside a Prepare recipe — pulls a small `rightInput` dataset into memory and joins on `leftCol = rightCol`. Replaces a separate Join recipe when the right side is < ~100K rows. Optional Levenshtein-based fuzziness.

| Param | Required | Description |
|-------|----------|-------------|
| `leftCol` | Yes | Column from the Prepare-recipe input |
| `rightCol` | Yes | Column from `rightInput` |
| `rightInput` | Yes | Name of the small lookup dataset (must already exist) |
| `copyColumns` | Yes | Array of column names from `rightInput` to copy into the output |
| `copyPrefix` | No | Prefix added to copied column names (avoids collisions) |
| `fuzzy` | No | `true` enables Levenshtein matching |
| `maxLevenshtein` | No | Max edit distance when `fuzzy: true` |
| `normalize`, `stem`, `clearStopWords`, `sortAlphabetically`, `language`, `forceRawLevenshteinEngine` | No | Fuzzy-mode tuning (text normalization, language model) |

```json
{
  "leftCol": "country_code",
  "rightCol": "iso2",
  "rightInput": "country_lookup",
  "copyColumns": ["country_name", "region"],
  "copyPrefix": "lookup_"
}
```

### Unfold

**When:** Long → wide spread of a repeated value into N suffixed columns. Distinct from `Pivot` (no aggregation, no key column) and `SplitUnfold` (no separator splitting).

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Source column to unfold |
| `prefix` | No | Output column prefix (defaults to `<column>_`) |
| `limit` | No | Max number of output columns. Required guard against unbounded fan-out |
| `overflowAction` | No | `ERROR` (default — fail at build) or `TRUNCATE` (silently drop overflow values) |

```json
{"column": "trucks_needed", "prefix": "truck_", "limit": 10, "overflowAction": "ERROR"}
```

### GeometryInfoExtractor

**When:** Extract geometry metadata (centroid GeoPoint, area) from a WKT or `the_geom` column. Pairs with `GeoPointCreator` / `GeoDistanceProcessor` / `CityLevelReverseGeocoder`.

| Param | Required | Description |
|-------|----------|-------------|
| `inputCol` | Yes | Geometry column (WKT or DSS `geometry` type) |
| `centroidCol` | No | Output column name for the centroid GeoPoint |
| `areaCol` | No | Output column name for the area (square units of the geometry's CRS) |

```json
{"inputCol": "the_geom", "centroidCol": "centroid", "areaCol": "area_m2"}
```

### CityLevelReverseGeocoder

**When:** Resolve admin-hierarchy levels (country / region / city / …) from a GeoPoint without hitting an external geocoding service. Distinct from forward `Geocoder` (address → point) and from the `forward_geocoding` plugin recipe.

| Param | Required | Description |
|-------|----------|-------------|
| `inputCol` | Yes | GeoPoint column |
| `l1OutCol` … `l8OutCol` | No | Output columns for admin levels 1–8. Common bindings: `l4OutCol="country"`, `l8OutCol="city"`. Omit unwanted levels |

```json
{"inputCol": "centroid", "l4OutCol": "country", "l6OutCol": "region", "l8OutCol": "city"}
```

### ZipCodeGeocoder

**When:** Cheap geocoding for postal-code-only data — emits a GeoPoint from a `(country, ZIP)` pair without hitting the full address geocoder.

| Param | Required | Description |
|-------|----------|-------------|
| `countryCol` | Yes | ISO country code column |
| `zipCodeCol` | Yes | Postal code column |
| `outputCol` | Yes | Output GeoPoint column |

```json
{"countryCol": "country", "zipCodeCol": "postal_code", "outputCol": "centroid"}
```

### ArraySortProcessor

**When:** Sort the contents of an array column.

| Param | Required | Description |
|-------|----------|-------------|
| `input` | Yes | Array column to sort |
| `sortingType` | No | `NUM` (numeric) or `ALPHANUM` (string). Default: ALPHANUM |
| `descending` | No | `true` for descending order |

```json
{"input": "proba_array", "sortingType": "NUM", "descending": true}
```

> **Wrong-param trap:** Older docs claim `column` / `order` — those names are silently dropped. Use `input` / `sortingType` / `descending`.

### ArrayUnfold

**When:** Explode an array column into one row per element (like `df.explode()`).

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Array column to unfold |
| `keepEmptyArrays` | No | If `true`, keep rows whose array was empty (with null in the unfolded column) |
| `delete` | No | If `true`, drop the original array column from the output |
| `countVal` | No | If `true`, emit a `<column>_count` column with the original array length (fifth param, observed in live recipes; legacy `appendCount` is silently ignored) |

```json
{"column": "tags", "keepEmptyArrays": false, "delete": true, "countVal": true}
```
