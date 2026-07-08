# Alteryx Spatial Tools → Dataiku

DSS has more visual geospatial capability than is obvious — try the visual path before Python. Covers CreatePoints / SpatialMatch / Distance / FindNearest / Buffer / PolyBuild / TradeArea, the three geometry-input readers (shapefile, `.yxdb` SpatialObj, embedded GeoJSON), and the Python escape hatches (coverage %, focal smoothing, hole-filling, route length, point-to-line distance, DMS parsing).

**Contents:** Spatial tool→recipe table · Extend a line (bearing projection) · Shapefile length/area · Make Grid focal smoothing · County/trade-area coverage · Fill polygon holes · PolyBuild + SpatialInfo · PolyBuild → exact GeoJSON · Point-to-polyline nearest distance · Fixed-width DMS parsing.

**GeoPoint columns need `set-schema` to type `geopoint`/`geometry`** or downstream GeoJoin warns "no geospatial columns" → 0 matches. **Syncing geopoint columns to PostgreSQL maps them to `geography`** — fails on a non-PostGIS instance (`type "geography" does not exist`); drop the geopoints before the sync and keep lon/lat/distance numerics.

| Alteryx tool | Dataiku answer |
|---|---|
| `CreatePoints` (lat/lon→point) | `dku recipe add-geopoint --lat <c> --lon <c> --output-column geopoint`, **then `set-schema` to `geopoint`** (`add-geopoint` writes WKT `POINT(...)` that infers as `string`). Inverse: `Extract lat/lon from GeoPoint` |
| `SpatialMatch` (point-in-polygon; `Within`) | **`dku recipe create-geojoin --operator CONTAINS -g <polygon_geom> -g <point_geom> --join-type INNER`** (left=polygons → "polygon CONTAINS point"). Visual — NOT shapely `sjoin`. Polygon type `geometry`, point `geopoint`. DSS `CONTAINS` == geopandas `within`. `Intersects` → `--operator INTERSECTS`. Filters + tags points with polygon attrs |
| `Distance` (point-to-point) | Prepare `Compute distance between two points` (Haversine). Driving/walking → **GeoRouter plugin** |
| `Distance` to **polyline/polygon** (`ReturnNearest`, nearest-edge) | **Pure-Python haversine — NO geo env.** Densify each segment, take min great-circle dist. See § Point-to-polyline nearest distance |
| `Distance` with bearing OR any spatial-angle (`ASIN/ATAN` over `ST_Distance`) | **SQL recipe — NOT visual** (GREL lacks `sin/cos/asin/atan2/radians`; `add-geodistance` returns no bearing). Sync to SQL. **Bearing (compass, N=0 cw):** `degrees(atan2(sin(radians(lon2-lon1))*cos(radians(lat2)), cos(radians(lat1))*sin(radians(lat2)) - sin(radians(lat1))*cos(radians(lat2))*cos(radians(lon2-lon1)))) mod 360`. The triangle/CrossTab "build pt C + 3× ST_Distance + ASIN" construction is dead — collapses to `degrees(asin(opp/hyp))` (opp=meridian leg, hyp=direct haversine). Pivot the two labelled points side-by-side with `MAX(CASE WHEN Label='A'…)`. Spheroid offset within geoid tolerance = match |
| `FindNearest` — **check `<MaxDistanceUnits>` FIRST** | `Miles`/`Km`/`Meters` = straight-line → haversine/GeoJoin below. `DriveTime`/`Distance` + `<DriveTimeDataSet>` (e.g. `TeleAtlas_US.Peak`) = road-network over a proprietary graph → **GeoRouter plugin**/routing API; absent either it is a **block**. Do NOT substitute straight-line (drive-time kNN reorders vs great-circle) |
| `FindNearest` (straight-line kNN) | **GeoJoin** `within distance` (`--max-matches` caps but does NOT sort by proximity), then Prepare `geoDistance` + Window (partition left key, order distance ASC, `rowNumber`) postFilter `rn==1`. SQL haversine alt below |
| `FindNearest` — **few FIXED targets (≤~5) → ONE Prepare, no join** | On the target row: `add-geopoint`, add each universe point as constant geopoints (`add-formula` literal lat/lon → `add-geopoint`), `add-geodistance --unit MILES` → `d_1…d_K`; `nearest=min(...)`; arg-min via nested `if`. Collapses `CreatePoints×2+Join+FindNearest+Sort` → 1 recipe |
| `FindNearest` — SQL alt | Sync to SQL, one `sql_query` with haversine CTE + CROSS JOIN + `ROW_NUMBER() OVER (PARTITION BY left_key ORDER BY dist)=1`. Crux: `2*3958.8*asin(sqrt(pow(sin(radians(lat2-lat1)/2),2)+cos(radians(lat1))*cos(radians(lat2))*pow(sin(radians(lon2-lon1)/2),2)))`. ~0.06% spheroid offset |
| `Buffer` | Prepare `Create area around geopoint` / `geoBuffer` GREL. Isochrone → GeoRouter |
| `Generalize`/`Smooth` | `geoSimplify` GREL |
| `SpatialInfo` (area/length/centroid/bbox) | `geoEnvelope` (bbox); Prepare geo-extract. **To match `ST_Area(geom,"SqMi")` use geodesic area** — `pyproj.Geod(ellps="WGS84").geometry_area_perimeter(geom)` (m², `abs`), NOT shapely `.area` (degrees² — meaningless). 1 sq mi = 2589988.110336 m² |
| `ST_Length(geom,"Miles")` on an **existing** Polyline | **Geodesic** — `Geod(ellps="WGS84").geometry_length(geom)` (m), `/1609.344`. NOT shapely `.length`. Point-sequence with no geometry yet → prefer visual `geoDistance(lag)`-sum (§ PolyBuild + SpatialInfo) |
| **Extend a line by N units at both ends** (`SpatialInfo(EndPoints)→TradeArea→Smooth→PolySplit→Distance→Sort DESC→Sample 1→ST_CreateLine`) | = **bearing projection.** Recognition cue: a `Buffer`/`TradeArea` circle immediately `PolySplit`-to-points + `Distance` + `Sort DESC` + `Sample 1` is never a real buffer — it's arg-max "farthest circle vertex". One pure-stdlib Python recipe; block condition + mechanics: § Extend a line below |
| `Summarize(SpatialObjCombine)` dissolving **Polylines** by group | `shapely.ops.unary_union` then `Geod.geometry_length`; `linemerge` for one connected line. **BUT if the only consumer is a total `ST_Length`/`ST_Area` → skip shapely:** combine+measure is additive = `Group sum` of the precomputed `Shape_len`/`Shape_area` `.dbf` attribute (§ Shapefile length/area). `unary_union` only for dedup-on-overlap or the merged geometry itself |
| `SpatialMatch` (contains/intersects/touches) | `geoWithin`/`geoContains` GREL (simple); GeoJoin (one recipe per relation) |
| `HeatMap`/`Binned Geo` | DSS Charts native |
| `PolyBuild` (point sequence→polygon/line) | **Exact GeoJSON/WKT coords → SQL `string_agg(coord ORDER BY seq)`, NOT Python** (Group `concat` can't order; SQL is byte-exact, no geo env). See § PolyBuild → exact GeoJSON. Use `shapely.LineString` only when the geometry feeds a downstream geometric op. **Typical downstream metric (`SpatialInfo.LengthMi`)** → visual `lag`+`geoDistance`+`Group sum` (§ PolyBuild + SpatialInfo) |
| `Spatial process` (union/intersection/…) | Python (`shapely` boolean ops) |
| `Trade area` — **check `<Units>` FIRST** | (1) `<Units>Minutes` + `<DriveTimeDataSet>` = drive-time isochrone over a proprietary graph → GeoRouter (rarely installed, won't match TeleAtlas); when the key is geometry-derived (overlap sq-mi) → **block**. (2) Fixed-radius circle (`<Radii>15`, Miles, no DriveTimeDataSet) = geodesic `Buffer`: visual `geoBuffer`; for area-accurate matching use a **geodesic** circle (`Geod.fwd` at N azimuths — planar `shapely.buffer` in lon/lat is distorted). See § County/trade-area coverage |
| `MapInput` (user draws shape) | User-provided WKT/GeoJSON dataset; no UI-drawing replacement (runtime-interactive geometry = block) |
| `Make Grid` | Python, but **a regular lattice needs NO shapely** — cells are a `(Column,Row)` integer grid; focal/neighbourhood ops are grid-index arithmetic. Shapely only if cell **polygons** feed a geometric op. See § Make Grid focal smoothing |
| `FindNearest(HowMany=8)` **+ `Unique(Direction)`** | **Recognition cue: FOCAL smoothing, not kNN.** `Direction` = 8 compass sectors; `Unique(Direction)` keeps nearest per direction → on a regular grid = the **3×3 Moore neighbourhood**. Grid-index focal averaging, not a kNN GeoJoin (§ Make Grid focal smoothing) |
| `PolySplit(SplitTo=Region)` [+ `Summarize` SpatialObjCombine per key] = **fill holes** | No GREL/visual "remove holes" → **one small Python recipe** (json only, NOT shapely — § Fill polygon holes) |

**Reading geometry IN — 3 input shapes, 3 readers** (depends on how geometry ships):
- **External ESRI shapefile** (`DbFileInput` `.shp`) — a `.yxzp` ships these under `_externals/<n>/` as `.shp` + mandatory sidecars `.shx`/`.dbf`/`.prj`. `geopandas.read_file("…/NAME.shp")` (auto-picks same-basename sidecars), `gdf.geometry.wkt` → DSS geo column (reproject to EPSG:4326 first if `.prj` isn't WGS84). Needs the geo code env.
- **`.yxdb` SpatialObj BLOB** → `tools-io-apps-ml.md` § YXDB files (`scripts/yxdb_read.py`, no geopandas).
- **Embedded GeoJSON in a `TextInput` `<c>` cell** → `shapely.geometry.shape(json.loads(cell))` (text content; `value=` attr empty). See § County coverage.

**Block decision for all-spatial flows.** 1–2 genuine-Python spatial tools (PolyBuild/SpatialProcess/MakeGrid) → collapse that segment into one Python recipe (`shapely`/`geopandas`); everything else has a visual path. All-geometry "coverage" flows (`CreatePoints→TradeArea→SpatialMatch→Intersection→ST_Area→pct` + a dissolve branch) → **one** `shapely`+`pyproj` recipe (§ County/trade-area coverage).

### Extend a line by N units (bearing projection)

One Python recipe, **pure stdlib**: WGS84 Vincenty inverse S→E for the bearing, then Vincenty direct from S on `bearing+180` for `N·1609.344` m. **Block if the answer key ships 6-decimal extended coords** — the macro's endpoint is a vertex of a discretized buffer circle, not the true great-circle continuation (lat matches ~4-5dp, lon/length diverge; a near-horizontal line lands ~800 ft off). If only an approximate length is consumed, `Geod.fwd` is within ~0.16%.

### Shapefile length/area Summarize → Group sum (NO geopandas)

A `.yxwz` spatial wizard whose deliverable is a per-group **total length/area** finishes with ZERO geopandas when shapefiles ship: `SpatialObjCombine + ST_Length`/`ST_Area` is **additive**, so it collapses to `create-stack` (Union of N years) → `create-group -k <key> --agg <len>:sum` → Prepare unit-convert (`/1609.344`). Two enablers:
- A shapefile's `.dbf` already carries per-segment length (`Shape_len`/`Shape_STLe`); when the `.prj` is a projected length-accurate CRS (e.g. `NAD_1983_UTM_Zone_13N` = EPSG:26913, units = Meter) it's already metres — don't reproject. Extract `(<key>, Shape_len)` to CSV with a pure-python DBF reader (**field type at descriptor byte +11, length at +16; field lengths must sum to `reclen`−1 or your offsets are wrong**).
- No answer key (output is a wizard PDF) → validate by artifact + shape (recompute the aggregate with throwaway pandas, diff). Only true geometry transforms (dissolve-with-dedup, intersection, buffer, raw reprojection) need geopandas.

### Make Grid focal smoothing (regular-lattice fill — NO shapely)

**Recognition cue:** `MakeGrid → RegEx GridName into Column/Row → … → FindNearest(HowMany=N) → Unique(Direction) → Summarize(Avg)` = 3×3 Moore neighbourhood + focal mean. Every cell is a `(Column,Row)` integer pair → grid-index arithmetic, no geo env. Melt to long `(Column,Row,PixelValue)` and one Python recipe:

```python
NCOL, NROW = df.Column.max()+1, df.Row.max()+1
grid = {(r.Column, r.Row): r.PixelValue for r in df.itertuples(index=False)}
def rhu(x):  # Alteryx Round() is half-UP; Python round() is banker's (semantics.md § Rounding)
    from decimal import Decimal, ROUND_HALF_UP
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
for (c, r0), v in grid.items():
    if v != 0: continue
    nb = [grid[(c+dc, r0+dr)] for dc in (-1,0,1) for dr in (-1,0,1)
          if (dc or dr) and 0 <= c+dc < NCOL and 0 <= r0+dr < NROW and grid[(c+dc, r0+dr)] != 0]
    out[(c, r0)] = rhu(sum(nb)/len(nb)) if nb else 0
```

Two exact-match traps: (1) **edge cells get fewer neighbours** — `Unique(Direction)` keeps one-per-direction, so a top-row cell averages 5 not 8 (a haversine-kNN repro misses exactly the edge cells). (2) **round-half-up, not banker's** — `.5` ties flip by 1 under Python `round()`. Coordinates/centroids are red herrings — result depends only on grid topology.

### County / trade-area coverage (the all-spatial Python collapse)

All-geometry "coverage" archetype (trade-area vs polygons; territory/telco coverage %). No visual path → one `shapely` + `pyproj.Geod(ellps="WGS84")` recipe. Mapping: `CreatePoints`→`Point(lon,lat)`; `TradeArea(Radii,Miles)`→geodesic circle `Polygon([geod.fwd(lon,lat,360*i/n,R)[:2] for i in range(n)])` (`R=mi*1609.344`, `n≈720`); `SpatialMatch(Intersects)`→`.intersects` filter; `SpatialProcess(Intersection)`→`a.intersection(b)`; `SpatialObjCombine`→`unary_union`; `ST_Area([g],"SqMi")`→`abs(geod.geometry_area_perimeter(g)[0])/2589988.110336`.

Gotchas:
- **Geodesic, not planar, everywhere** — buffer via `geod.fwd`, area via `geometry_area_perimeter`. `shapely.buffer`/`.area` (lon/lat degrees) wrong by large factors; geodesic lands <0.01% off.
- **Invalid input polygons throw** `GEOSException: side location conflict` — wrap every input in `make_valid()` (or `.buffer(0)`) before any boolean op.
- **Embedded `.yxmd` spatial data is GeoJSON text** in `<c>` content (`value=` empty) — `shapely.geometry.shape(json.loads(cell))`.
- **Validation is tolerance-based** — pct within ~0.1 on large overlaps; tiny slivers drift ~0.25 pct (vertex discretization) = match.
- **Geo code env, container-mode NONE** — env setup commands (`dku code-env set-packages` + `recipe set-env`): `tools-predictive-ml.md` § ARIMA code-env.

### Fill polygon holes (`PolySplit` Region + `SpatialObjCombine`)

"Fill in the spatial object" archetype. One tiny Python recipe — **no shapely, just `json`** (2 tools→1):

```python
def signed_area(ring):                         # shoelace; sign = winding order
    return -sum((ring[i+1][0]-ring[i][0])*(ring[i+1][1]+ring[i][1])
                for i in range(len(ring)-1)) / 2.0
def fill_holes(geojson_str):
    g = json.loads(geojson_str)
    if g["type"] == "Polygon":
        g["coordinates"] = [r for r in g["coordinates"] if signed_area(r) < 0]
    elif g["type"] == "MultiPolygon":
        g["coordinates"] = [p for p in ([r for r in part if signed_area(r) < 0]
                                         for part in g["coordinates"]) if p]
    return json.dumps(g)
```

**Critical: Alteryx distinguishes exterior rings from holes by WINDING ORDER, not position.** Do NOT assume `coordinates[0]`=exterior, `[1:]`=holes — one part packs exteriors AND holes flat. Exteriors have **negative** `signed_area`, holes positive → keep `signed_area < 0`. "Keep `coordinates[0]`" silently corrupts any multi-region part.

**"Coverage smoothing" variant** (`PolySplit(Region) → SpatialInfo(AreaMi) → Filter(!IsHole & AreaSqMi>=N) → SpatialObjCombine`): same ring-split + a per-ring **geodesic area threshold** dropping small slivers/islands (one shapely+pyproj recipe). Keep ring iff `signed_area < 0` AND `abs(Geod.polygon_area_perimeter(lons,lats)[0])/2589988.110336 >= N`; `unary_union(make_valid(Polygon(ring))…)` dissolves survivors. Filtering holes (not subtracting) FILLS them; the area filter smooths. Decode the `.yxdb` SpatialObj BLOB to per-ring POLYGON WKT (`tools-io-apps-ml.md` § YXDB files) and upload. A dissolved WKT cell can exceed the CSV reader's 131072-byte per-field limit — `dku dataset head` errors on it (`overview.md` § TextInput extraction, mega-field).

### PolyBuild + SpatialInfo (sequence → length)

`PolyBuild(SequencePolyline) → SpatialInfo(LengthMi)` (total route length per group) — DSS resolves it WITHOUT building the LineString: per-leg `geoDistance` + sum (5 visual recipes, all push down: Prepare `point_wkt` → Window `lag` → Prepare filter-first + `add-geodistance` → Group sum → Sort). Non-obvious bits:
- **Use WKT, not GeoJSON** — `geoDistance`/`add-geodistance` accept WKT `POINT(lon lat)`; GeoJSON Point strings return empty with no warning. Column need not be re-typed.
- DSS strips embedded `"` from CSV uploads, so regex-extract on de-quoted text: `match(Centroid, /.*\[\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*\].*/)[0|1]`.
- Window output is always `{column}_lag` regardless of the 3rd `--compute` segment (`../../dku-cli/references/visual-recipe-payloads.md` § Window).
- **GREL `geoDistance()` rounds to 2dp; `add-geodistance` is full-precision, DIFFERENT spheroid math.** On a multi-leg trip GREL runs ~+0.06% high, `add-geodistance` ~−0.15% low. **Use `add-geodistance` for trip/route distance** (per-leg errors accumulate); GREL is fine for ad-hoc per-row compares. Both differ from Alteryx (different ellipsoid) — document the offset, treat as match.

### PolyBuild → exact GeoJSON LineString via SQL `string_agg` (no shapely, no geo env)

When the answer key is the **built geometry as exact coordinates**, the migration is **pure SQL ordered string aggregation**, not shapely. Group `concat` can't order; `string_agg(expr, ', ' ORDER BY seq)` builds the exact string byte-exact in-DB. Archetype: a track cut into a line per attribute-run (`MultiRowFormula segment-id + carry → Summarize → poly_build_macro`). One `sql_query`:

1. **Run-length segment id** (consecutive-same-value islands):
   ```sql
   SUM(CASE WHEN "STORMTYPE" IS DISTINCT FROM LAG("STORMTYPE") OVER (ORDER BY "DTG")
            THEN 1 ELSE 0 END) OVER (ORDER BY "DTG" ROWS UNBOUNDED PRECEDING) AS seg
   ```
2. **Look-ahead bridge** — adjacent map segments share an endpoint → each segment's line includes the **first point of the next** (geometry + per-seg averages). `UNION ALL` a bridge row (first point of seg `S` re-tagged to `S-1` with `ord` sorting after all of `S-1`). Drop this CTE if continuous/closed shapes aren't needed.
3. **Build the GeoJSON string** with `string_agg … ORDER BY` + `to_char` for 6-decimal coords:
   ```sql
   '{ "type": "LineString", "coordinates": [ ' ||
     string_agg('[ ' || to_char("LON"::numeric,'FM999990.000000') || ', ' ||
                        to_char("LAT"::numeric,'FM999990.000000') || ' ]', ', ' ORDER BY ord) ||
   ' ] }' AS "SpatialObj_Built"
   ```
   `FM999990.000000` strips left padding, keeps exactly 6 decimals, prints a leading `0` for `|x|<1`; `-` is free. `NULL` `STORMTYPE` on bridge rows recovered with `MAX(...)`. Validate geometry by parsing both sides' coord arrays as floats (average column won't string-match). Standard `sql_query` mechanics — `../../dku-cli/playbooks/tabular-flow.md` § SQL recipe.

### Point-to-polyline nearest distance (`Distance` ReturnNearest → built line)

Measure how far an external point is from the nearest line, and which line. **No visual/GREL path** — `geoDistance` is point-to-point; nearest-edge needs the line interior → ONE Python recipe, **no geo env** (pure-Python haversine):

```python
import math
R = 3958.7613  # mean Earth radius, miles
def hav(lo1, la1, lo2, la2):
    p1, p2 = math.radians(la1), math.radians(la2)
    a = math.sin(math.radians(la2-la1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lo2-lo1)/2)**2
    return 2 * R * math.asin(math.sqrt(a))
def nearest_to_polyline(px, py, pts, steps=200):       # densify each segment so the nearest
    best = float('inf')                                 # point can fall BETWEEN vertices
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        for k in range(steps + 1):
            t = k / steps
            best = min(best, hav(px, py, x1+(x2-x1)*t, y1+(y2-y1)*t))
    return best
# lines = {name: [(lon,lat),...] in PolyBuild sequence order}; pick min over names
```

- **Densify segments** — `min` over vertices only overstates (true nearest is usually mid-edge); 200 steps/edge is plenty at city scale.
- **PolyBuild sequence = input read order** — don't re-sort.
- **`SpatialMatch(Intersects)` against a US-nation shapefile is often dead** — it only clips the path to land; if candidates already lie near the point, distance is unchanged. Confirm before reproducing the shapefile load.
- Geoid tolerance ~0.05–0.1%; sub-percent miss = match, label must be exact.

### Fixed-width DMS report parsing (eclipse / ephemeris / survey tables)

Some `TextInput`s carry a fixed-width report with coordinates in `DD MM.mH` form (`39 59.7N` = 39°59.7′N). Parse in the recipe:

```python
dms = re.compile(r'(\d+)\s+(\d+\.\d+)([NSEW])')          # "39 59.7N", "171 44.9W"
def dec(d, m, h):
    v = int(d) + float(m)/60.0
    return -v if h in ('S', 'W') else v
# header/ruler/blank/footer rows have <6 coord tokens → skip rows with len(dms.findall(line)) < 6
```

- **Token-count filter beats row-index filter** — keep rows with ≥N coord tokens; no hardcoded line numbers.
- **`DD MM.mH` is degrees + decimal-minutes + hemisphere** (`deg + min/60`, negate W/S) — do NOT treat `59.7` as fractional degree.
- Landing such a report as one column: tab separator + `quoteChar:""` upload-prep — `overview.md` § TextInput extraction (fixed-width / line-wrapped rules).
