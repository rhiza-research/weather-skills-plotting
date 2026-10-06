# Data bindings

A Vega-Lite top-level spec may carry a `datasets` object of name → rows, and
any view reads one with `"data": {"name": NAME}`. That is standard Vega-Lite.
This skill lets a `datasets` entry be a **binding object** instead of rows.
Before validation, every binding is replaced by the rows it produces, so the
compiler only ever sees standard Vega-Lite. A plain list of rows is passed through
untouched, and inline `"data": {"values": [...]}` in a view also works as usual.

A binding has exactly one of the keys `zarr`, `geojson` or `naturalearth`.
Unknown keys are errors that list the keys the binding accepts.

```json
"datasets": {
  "obs":      {"zarr": "obs", "fields": {"lon": "longitude.lo", "lon2": "longitude.hi",
                                         "lat": "latitude.lo",  "lat2": "latitude.hi",
                                         "precip": "precip"}},
  "stations": {"zarr": "stations", "fields": {"lon": "longitude", "lat": "latitude",
                                              "name": "station_name", "precip": "precip"}},
  "bands":    {"zarr": "fcst", "sel": {"step": "7D"},
               "contours": {"variable": "tp", "levels": [0, 5, 10, 20, 50, 100], "filled": true}},
  "borders":  {"naturalearth": "borders", "scale": "10m"},
  "region":   {"geojson": "region"},
  "labels":   [{"lon": 36.8, "lat": -1.3, "text": "Nairobi"}]
}
```

The dataset name (the key under `datasets`) and the input name (`-i NAME=PATH`)
are separate. One input can feed several datasets: a full grid for cells and
a thinned copy for arrows, or one variable each from the same Zarr.

## `zarr`: tidy rows from a Zarr input

| Key | Meaning |
| --- | --- |
| `zarr` | Input name from `-i NAME=PATH`. |
| `fields` | **Required.** Object of output column → source. Column names are yours; the field names in encodings refer to them. At least one source must be a data variable. |
| `sel` | Label selection, `{dim: value}`. See **Selecting**. |
| `isel` | Positional selection, `{dim: index}`, same forms as `sel`. |
| `bbox` | `[N, W, S, E]` crop in degrees, applied before `sel`. On a grid it slices latitude and longitude, in either latitude order; on stations it keeps the points inside. Because the default map window is the data's extent, **this is the way to set the map window.** |
| `dropna` | Default `true`: drop rows where every variable column is NaN (ocean cells of land-only products, missing station values). `false` keeps them. |
| `cell_overlap` | Fraction (e.g. `0.25`) that widens `.lo`/`.hi` edges. Rarely needed: seam sealing already hides antialiasing gaps. |

### Field sources

| Source | Column value |
| --- | --- |
| A data variable (`precip`, `tp`, `t2m`) | The values. Units are not converted: the variable's `units` attr only feeds the default title. |
| A dim (`time`, `step`, `number`, `latitude`, `station_id`, `model`) | The coordinate value of each row. Listing a dim makes it a column: rows are the cartesian product of the listed dims. |
| A non-dim coord (`station_name`, or `latitude` on a `station_id` dataset) | The coordinate value; the dims it sits on become row dims. |
| `<dim>.lo`, `<dim>.hi` | Lower / upper cell edge of a numeric 1-D dim: midpoints between centres, the end cells mirrored. Use with `rect` on `longitude`, `longitude2`, `latitude`, `latitude2`. Works on any spacing and either latitude order. |
| `valid_time` | `time + step` (forecast init plus lead) as a datetime. |

How the values are encoded:

- **Datetimes are epoch milliseconds, UTC** (2026-01-06 is `1767657600000.0`). Encode them with
  `"type": "temporal"`; in expressions they are numbers that the date
  functions accept (`timeOffset('day', datum.week, 7)`, `year(datum.time)`,
  `timeFormat(datum.time, '%d %b')`). A `lookup` between two bindings on a
  time column matches exactly, which ISO strings would not do reliably.
- **Timedeltas are float days**: a `step` of 7 days is `7.0`, so
  `"'Week ' + (datum.lead_days / 7)"` labels lead weeks.
- Strings, ints and floats pass through. NaN becomes `null`.

### Every dim must be accounted for

After `bbox`, `sel` and `isel`, each dim that still has more than one value
must be the source of a column (or under a listed coord). Otherwise the binding fails:

```text
datasets.f: dims {'step': 4} are not columns in fields and have more than one value. Add each one to fields, pick one value with sel/isel, or reduce it upstream (summarize-dim, aggregate-temporal). Nothing is averaged for you.
```

Size-1 dims (a single `time`, a scalar init) are dropped silently. Bindings
never average: an ensemble mean is either `summarize-dim --dim number`
upstream, or `number` as a column plus a Vega-Lite `aggregate` in the spec
(see the spaghetti recipe).

### Selecting

| Form | Example | Meaning |
| --- | --- | --- |
| Scalar | `{"step": "7D"}`, `{"time": "2026-10-01"}`, `{"latitude": -1.3}` | One value. On numeric and time dims, the **nearest** value. On string dims (`model`), exact. |
| List | `{"step": ["7D", "14D"]}`, `{"model": ["ECMWF", "UKMO"]}` | Several values, exact labels. The dim stays, so it must be a column. |
| Slice | `{"time": {"start": "2026-06-01", "stop": "2026-09-30"}}` | Inclusive label range. `step` is a stride in positions. |
| `isel` | `{"number": 0}`, `{"latitude": {"step": 3}, "longitude": {"step": 3}}` | Positions; the slice form thins a grid. |

Lead times accept anything `pandas.to_timedelta` reads: `"7D"`, `"7 days"`,
`"168h"`. Dates accept ISO strings. A selection that matches nothing fails
and prints the coordinate's range.

### Extent

Each Zarr binding records the box its rows cover: the outer cell edges
when the binding has `.lo`/`.hi` columns, the point coordinates otherwise.
The map defaults (`projection.fit`, base-map clipping) use the union of these.

### Size

Every row is a mark drawn one by one. A 0.05° CHIRPS grid over Kenya is
about 34000 cells and renders in a few seconds; Africa at 0.05° is millions.
Crop with `bbox`, thin with `isel`, or coarsen upstream. Totals over 150000
rows print a warning; over 500000 fail unless `--max-rows N` is passed.

## `contours`: filled bands or isolines

Vega-Lite has no contour mark. A `zarr` binding with a `contours` block
traces a 2-D latitude × longitude field with contourpy and produces GeoJSON
features for a `geoshape` mark.

| Key | Meaning |
| --- | --- |
| `contours.variable` | The data variable to trace. |
| `contours.levels` | List of numbers. Isolines: one line feature per level. Filled: one band per consecutive pair (at least two levels). |
| `contours.filled` | `true` for bands, default `false` for lines. |
| `sel`, `isel`, `bbox` | As above; after them the field must be 2-D. |

Band features carry `properties.lo`, `properties.hi` and `properties.mid`;
line features carry `properties.level`. These are in the variable's units,
so `"color": {"field": "properties.mid", "type": "quantitative"}` gets the
variable's default palette and title. Contours stop at the outermost cell
centres. Use levels that match the palette's class edges so each band is one colour.

## `naturalearth`: base-map layers

| Key | Meaning |
| --- | --- |
| `naturalearth` | `countries` (polygons, with `ADM0_A3`, `ISO_A3`, `NAME`, ...), `borders` (land boundary lines), `coastline`, `lakes` (polygons), `rivers` (lines), `admin1` (first-level boundary lines), `ocean`, `land`. |
| `scale` | `10m` (detailed, for a country or smaller), `50m` (default, regional), `110m` (continental). |
| `bbox` | `[N, W, S, E]` clip box (+1° pad). Default: the extent of all Zarr bindings. |
| `properties` | Property names to keep, matched case-insensitively, kept under their original case. Default `["name"]`. Ask for what you filter or label on, e.g. `["ADM0_A3", "NAME"]` for `"filter": "datum.properties.ADM0_A3 == 'KEN'"`. |

Files come from natural-earth-vector v5.1.2, downloaded once each into
`$WS_NE_CACHE` (default `~/.cache/weather-skills/naturalearth`). Clipping to
the data keeps a 10m layer to a few kilobytes. Polygons are re-oriented for
d3 (see `maps.md`).

Draw them with `geoshape`. Line layers need `"filled": false`.

## `geojson`: your own vectors

`{"geojson": "region"}` loads `-i region=/tmp/kenya.geojson`: a
FeatureCollection, a single Feature, or a bare geometry. Feature properties
are kept as-is (`datum.properties.<key>`). `bbox` works and has the same
default as `naturalearth`. Typical sources are `resolve-region --geojson`,
a watershed or a custom box.

## Plain rows

A list of objects passes through unchanged:
`"cities": [{"lon": 36.82, "lat": -1.29, "name": "Nairobi"}]`. Inline
`"data": {"values": [...]}`, `"data": {"sequence": ...}` and Vega-Lite
generators also work. Avoid `"data": {"url": ...}`: it bypasses the defaults
and the field checks, and the file is not recorded in provenance. Pass the
file with `-i` and bind it instead.
