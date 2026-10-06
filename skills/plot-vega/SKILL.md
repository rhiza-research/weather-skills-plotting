---
name: plot-vega
description: Render any chart or map as PNG, JPEG or self-contained HTML from a plain Vega-Lite 6 JSON spec, with weather-skills Zarrs, GeoJSON files and Natural Earth base-map layers bound in as named datasets. Use it for maps (precip grids as true-size cells, stations, contours, wind arrows, country and admin-1 outlines, faceted lead weeks, side-by-side products on their own grids), time series (one or several products, ensemble spaghetti with bands, multi-panel), bars, box plots and wind roses. The spec is standard Vega-Lite, so anything in the Vega-Lite docs works; the skill only adds data bindings under datasets, unit-aware titles, weather palettes and a map window from the data. Start with --describe and a recipe from recipes/. Aggregate and reduce upstream (aggregate-temporal, convert-to-totals, summarize-dim, clip-region): bindings select and reshape, they never average.
license: MIT
compatibility: Requires Python 3.12 and uv. Natural Earth layers are downloaded once per file (network on first use).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_vega.py *)
metadata:
  version: "0.0.1"
  catalog-group: figure
---

# plot-vega

**The spec is a Vega-Lite 6.4 spec.** Not a dialect and not a wrapper: the
JSON you pass is the JSON the [Vega-Lite docs](https://vega.github.io/vega-lite/docs/)
describe, and it is rendered by the reference Vega-Lite compiler. Every mark,
encoding channel, transform, scale, axis, legend, `config`, `params`, `facet`,
`repeat`, `layer` and `concat` works exactly as documented there. This file
and `references/` cover the weather-specific parts and the recipes that are
known to look right; **when you want something they do not show, write the
Vega-Lite you would write anywhere else.** The [Vega-Lite examples
gallery](https://vega.github.io/vega-lite/examples/) is a valid source of
recipes. `--dump-spec` output pastes straight into the
[Vega editor](https://vega.github.io/editor/).

The skill adds exactly three things on top of Vega-Lite:

1. **Data bindings.** An entry under the top-level `datasets` may be a
   binding object instead of a list of rows: `{"zarr": NAME, "fields": {...}}`
   turns a Zarr input into tidy rows, `{"naturalearth": "borders"}` loads a
   base-map layer, `{"geojson": NAME}` loads a GeoJSON input. They are replaced
   by plain rows before Vega-Lite sees the spec. Layers read them with
   `"data": {"name": "..."}`, which is ordinary Vega-Lite.
2. **Defaults for keys you leave out**, derived from the bound data: the
   classed precipitation palette, `long_name [units]` titles, the map window
   (`projection.fit`) and a clip box for base-map layers. A key you write is
   never changed. Every default is printed as `default <json path> <- <value>`.
3. **Two render patches**: legends for threshold scales are drawn as one
   equal-size swatch per class, and grid cells get a hairline stroke in their
   own colour so abutting cells show no white seams.

`usermeta` switches them off (`{"usermeta": {"defaults": false}}`); see
**Defaults**. Vega-Lite itself ignores `usermeta`.

## Workflow

1. **Prepare the data upstream.** The bindings select and reshape; they never
   average, sum or regrid. Typical chains:
   - weekly area-mean series: fetch → `clip-region` → `summarize-dim --dim latitude --dim longitude --method mean --lat-weighted` → `aggregate-temporal --period "7 day"` → `convert-to-totals`;
   - a precipitation map: fetch → `aggregate-temporal` → `convert-to-totals` (the figure should show period totals in mm, not rates);
   - an ensemble-mean map: `summarize-dim --dim number` first, or keep `number` as a column and aggregate in the spec.
2. **Describe the inputs**: `--describe -i NAME=PATH ...` prints each input's
   dims, coords (range and step), variables with `long_name`, `units` and
   `aggregation_period`, and the derived field sources you can bind.
3. **Start from a recipe.** Copy the closest file from
   `${CLAUDE_SKILL_DIR}/recipes/` (index below; `references/recipes.md` has each
   with its `-i` names), rename the binding inputs and `fields` sources to
   match your Zarr, and change titles.
4. **Check the binding before rendering** (optional, fast):
   `--describe -i ... --spec spec.json` prints the rows each binding produces
   and every default that would apply.
5. **Render once** and read stdout: `bound NAME: N rows (columns)` lines,
   `default ...` lines, `plot hash`, and `data: not null (...)`.
6. **Look at the PNG** (or run `inspect-figure`) before changing anything.
   A changed `plot hash` only proves the pixels changed.
7. **Iterate on the spec**, not on flags. There are no styling flags.

## Command line

```bash
# Inspect inputs (no spec needed)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_vega.py --describe -i obs=/tmp/chirps_week.zarr

# Render
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_vega.py \
    -i obs=/tmp/chirps_week.zarr -i stations=/tmp/tahmo_week.zarr \
    --spec ${CLAUDE_SKILL_DIR}/recipes/map_heatmap_stations.json -o /tmp/map.png

# The final Vega-Lite (bindings resolved to rows, every default written out)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_vega.py -i obs=/tmp/chirps_week.zarr \
    --spec spec.json --dump-spec /tmp/final.vl.json --dump-spec-rows 5
```

| Flag | Meaning |
| --- | --- |
| `-i`, `--input NAME=PATH` | Repeatable. A Zarr directory, or a `.geojson`/`.json` file (e.g. from `resolve-region --geojson`). `NAME` (letters, digits, `_`, `-`; starts with a letter or `_`) is what bindings refer to: `{"zarr": "obs"}`, `{"geojson": "region"}`. A single bare `PATH` is named `data`. |
| `--spec` | The Vega-Lite spec: inline JSON, a path to a JSON file, or `-` for stdin. Required except with `--describe`. |
| `-o`, `--output` | `.png`, `.jpg`/`.jpeg`, or `.html`/`.htm` (one self-contained file with the Vega runtime inlined; open it in a browser for tooltips and zoom). |
| `--scale` | Pixel ratio for PNG/JPEG. Default 2: a 600-px-wide view gives a 1200-px image. Size the chart with `width`/`height` in the spec, not with this. |
| `--describe` | Print the inputs; with `--spec`, also the bound rows and defaults. Renders nothing. |
| `--dump-spec [PATH]` | Write the final Vega-Lite to `PATH` (bare or `-`: stdout) and skip rendering. Binding and default lines go to stderr. |
| `--dump-spec-rows N` | With `--dump-spec`, keep only the first `N` rows per dataset so the dump is readable. |
| `--max-rows N` | Total bound-row limit (default 500000; a warning prints above 150000). |

## Anatomy of a spec

A map: one Zarr grid drawn as true-size cells, with borders on top.

```json
{
  "title": "CHIRPS weekly total",
  "width": 400, "height": 480,
  "projection": {"type": "equirectangular"},
  "datasets": {
    "obs": {"zarr": "obs", "sel": {"time": "2026-10-01"},
            "fields": {"lon": "longitude.lo", "lon2": "longitude.hi",
                       "lat": "latitude.lo", "lat2": "latitude.hi",
                       "precip": "precip"}},
    "borders": {"naturalearth": "borders", "scale": "10m"}
  },
  "layer": [
    {"data": {"name": "obs"},
     "mark": {"type": "rect", "clip": true},
     "encoding": {
       "longitude": {"field": "lon", "type": "quantitative"},
       "latitude": {"field": "lat", "type": "quantitative"},
       "longitude2": {"field": "lon2"}, "latitude2": {"field": "lat2"},
       "color": {"field": "precip", "type": "quantitative"}}},
    {"data": {"name": "borders"},
     "mark": {"type": "geoshape", "filled": false, "stroke": "#222", "clip": true}}
  ]
}
```

Nothing here sets a colour scale, a legend title, a map window or a clip box
for the borders: those are the defaults. Run with `-i obs=PATH`.

A time series: one weekly area-mean series as a line.

```json
{
  "title": "Weekly precipitation, Ghana average",
  "width": 640, "height": 260,
  "datasets": {"weekly": {"zarr": "weekly", "fields": {"week": "time", "precip": "precipitation_surface"}}},
  "data": {"name": "weekly"},
  "mark": {"type": "line", "point": true},
  "encoding": {
    "x": {"field": "week", "type": "temporal", "title": null, "axis": {"format": "%b %Y"}},
    "y": {"field": "precip", "type": "quantitative"}
  }
}
```

The y title (`Total precipitation [mm]`) comes from the variable.

## Bindings

Full reference: `references/bindings.md`.

| Binding | Produces | Keys |
| --- | --- | --- |
| `{"zarr": NAME, "fields": {...}}` | Tidy rows, one per combination of the dims you list | `fields` (**required**: column → dim, coord, variable or derived source), `sel`, `isel`, `bbox` `[N, W, S, E]`, `dropna` (default `true`), `cell_overlap` |
| `{"zarr": NAME, "contours": {...}}` | GeoJSON contour bands (`filled: true`) or isolines, for a `geoshape` mark | `contours.variable`, `contours.levels`, `contours.filled`, plus `sel`, `isel`, `bbox` |
| `{"naturalearth": LAYER}` | Natural Earth features clipped to the data | `scale` (`10m`, `50m` default, `110m`), `bbox`, `properties` (default `["name"]`) |
| `{"geojson": NAME}` | The features of a `-i NAME=file.geojson` input | `bbox` |
| a list of rows | Passed through untouched (plain Vega-Lite) | |

- `fields` sources: any dim (`time`, `step`, `number`, `latitude`), any coord
  (`station_name`), any data variable, and the derived sources
  `<dim>.lo` / `<dim>.hi` (cell edges, for `rect` maps) and `valid_time`
  (`time + step` for forecasts).
- **Every dim with more than one value must be a column or be selected away**
  with `sel`/`isel`; otherwise the binding fails and says which dims are left.
  Size-1 dims are dropped silently.
- `sel` takes labels (scalars pick the nearest value on numeric and time dims;
  lists pick several; `{"start", "stop", "step"}` is a slice). Lead times are
  written `"7D"` or `"14 days"`, dates `"2026-10-01"`. `isel` takes positions
  (`{"latitude": {"step": 3}}` thins a grid).
- Datetimes arrive as **epoch milliseconds (UTC)**: use `"type": "temporal"`.
  Timedeltas (`step`) arrive as **float days**: `datum.lead_days / 7` is the lead week.
- Natural Earth layers: `countries`, `borders`, `coastline`, `lakes`, `rivers`,
  `admin1`, `ocean`, `land`.

## Defaults

Full reference, with how to see and override each one: `references/defaults.md`.

| Default | Applies when | Value |
| --- | --- | --- |
| Colour scale | A `color`/`fill`/`stroke` field is a bound precipitation, SPI or percent-of-normal variable, `type` is `quantitative`, and the scale sets none of `type`, `scheme`, `range`, `domain`, `domainMid`, `domainMin`, `domainMax` | The classed weather palette for that variable (precip totals windowed by `aggregation_period`, anomalies diverging), as a Vega-Lite `threshold` scale |
| Palette name as `scale.scheme` | The scheme is one of the weather palette names below | That palette as a `threshold` scale |
| Title | An `x`, `y`, `color`, `fill`, `stroke`, `size`, `opacity`, `theta` or `radius` field is a bound variable and has no `title` | `long_name [units]`, e.g. `Total precipitation [mm]`, `2 metre temperature [°C]` |
| Map window | A `projection` sets none of `fit`, `scale`, `translate` | `fit` to the extent of the Zarr data drawn in that view |
| Base-map clip | A `naturalearth`/`geojson` binding has no `bbox` | The combined extent of all Zarr bindings (+1° pad) |
| Classed legend | Any `threshold` colour scale | One square per class labelled with its range |
| Cell seams | `rect` marks filled from a scale with no stroke | `stroke` = fill, width 0.5 |

"Bound variable" means a column whose source is a data variable and that no
transform has recomputed. Anything computed in the spec (wind speed from u/v,
an `aggregate` output) has no units to go on: set its scale and title yourself.

Switch off: `usermeta.defaults: false` (everything except seam sealing),
`usermeta.classed_legend: false`, `usermeta.seal_cells: false`. To change a
single default, write that key; to see them all as explicit JSON, use `--dump-spec`.

## Palettes

Weather palettes, usable as `"scale": {"scheme": NAME}` on any quantitative colour field:

| Name | What |
| --- | --- |
| `default_precip` | Precip totals: white/beige below 5 mm, then greens, blues, purples. Window from `aggregation_period`: under 2 days 0–50 mm, under 10 days 0–200, under 40 days 0–400, longer 0–1000 (none: weekly) |
| `default_precip_anom` | Precip anomalies, diverging brown (dry) to green/blue (wet): ±50, ±200, ±300, ±500 mm by the same windows |
| `ppt_daily`, `ppt_week`, `ppt_month`, `ppt_season` | A fixed totals window |
| `ppt_anom_daily`, `ppt_anom_week`, `ppt_anom_month`, `ppt_anom_season` | A fixed anomaly window |
| `ppt_short`, `ppt_total`, `chirps_short`, `chirps_total` | CHC classic rainbow totals legends |
| `ppt_poa`, `ppt_spp`, `spi` | Percent of normal, seasonal performance probability, SPI |

The automatic default picks `spi` for SPI variables, `ppt_poa` for percent of
normal, the anomaly window for precip whose name or `long_name` contains
"anomal" (or that has negative values), and the totals window otherwise.
Name a palette explicitly when that detection is wrong (an anomaly that lost
its name after `difference`, an all-positive anomaly, a bias-corrected total
with negatives).

Any [Vega scheme](https://vega.github.io/vega/docs/schemes/) also works
(`viridis`, `blues`, `yellowgreen`, `redblue`, `brownbluegreen`, ...); add
`"domainMid": 0` for a diverging scheme centred on zero. A custom classed
palette is plain Vega-Lite and still gets the classed legend:
`{"type": "threshold", "domain": [edges...], "range": [under, class colours..., over]}`
(the range has one more colour than the domain).

## Recipes

Each file in `${CLAUDE_SKILL_DIR}/recipes/` is a complete spec whose
`description` names the inputs it expects. All of them render as-is against
inputs of that shape (they are the skill's tests). Details and `-i` lines:
`references/recipes.md`.

| Recipe | Picture |
| --- | --- |
| `map_heatmap_stations` | Grid cells + lakes, coast, borders + station dots and labels on one shared legend |
| `map_country_admin1` | One country outlined (Natural Earth filter on ISO code) with admin-1 lines; no GeoJSON needed |
| `map_region_outline` | A grid with a `-i region=file.geojson` boundary on top |
| `map_forecast_leads_facet` | One map per lead week (facet on `step`), legend underneath |
| `map_side_by_side_grids` | Two products side by side, each on its own grid, cropped to the same box, one legend |
| `map_anomaly_diverging` | Classed anomaly palette beside a continuous diverging scheme |
| `map_contours` | Filled contour bands + isolines from a `contours` binding |
| `map_quiver_wind` | Wind speed cells + direction arrows from a thinned binding |
| `timeseries_weekly_line` | One weekly series, line + points, dashed mean with label |
| `timeseries_two_products` | Two products (IMERG, CHIRPS) on one axis with a legend |
| `timeseries_ensemble_spaghetti` | Members, 10–90% band, mean, climatology |
| `timeseries_multi_panel` | Stacked panels: members and mean over anomaly bars (lookup join) |
| `bar_weekly_totals` | Weekly totals as bars spanning their own week |
| `bar_model_comparison` | Grouped bars by model and lead, value labels |
| `box_mediogram` | Box/whisker per lead week from ensemble quantiles, climatology dot |
| `windrose` | Direction sectors stacked by speed class, from u/v |

## Rules that save a re-render

Map specifics are in `references/maps.md`, chart specifics in `references/charts.md`.

- **Always set `type`** on every field encoding (`quantitative`, `temporal`,
  `nominal`, `ordinal`). Vega-Lite treats a field with no type as nominal:
  a numeric axis becomes hundreds of category ticks and a precipitation
  colour becomes a categorical legend, with no error.
- **Every map layer gets `"clip": true`** on its mark; otherwise stations,
  labels and base-map lines draw outside the map.
- **Line-only Natural Earth layers need `"filled": false`** (`coastline`,
  `borders`, `admin1`, `rivers`, and `countries` when you want outlines).
- **Grids are `rect` marks with `<dim>.lo`/`.hi` edges** on
  `longitude`/`longitude2`/`latitude`/`latitude2`; this draws each cell at its
  true size on any grid spacing. Station points are `circle` marks on
  `longitude`/`latitude`.
- **`projection` goes on each panel**, not on an `hconcat`/`vconcat` parent
  (that is a schema error). In a `facet`, it goes inside `spec`.
- **Bars from `x` to `x2` need `"y2": {"datum": 0}`**, or they float.
- **Bins are labelled at their start** (`aggregate-temporal` output). For a
  week end, compute it: `{"calculate": "timeOffset('day', datum.week, 7)", "as": "week_end"}`.
- **A legend for layers that are not a field** comes from a constant colour:
  `"color": {"datum": "CHIRPS"}` on each layer, with the colours in a shared
  top-level `color.scale.range` (see `timeseries_two_products`).
- **Two layers on one colour field share one legend only if their scales are
  identical.** Defaults give matching variables the same scale; if you set a
  scale on one layer, set the same one on the other.
- **Large grids are slow**: every row is a mark. Crop with the binding's
  `bbox`, thin with `isel`, or coarsen upstream; over 150000 rows prints a
  warning and over 500000 fails unless `--max-rows` is raised.

## Errors

Errors exit 2 and name the JSON path. Fix the spec and render again.

| Message starts with | Meaning |
| --- | --- |
| `datasets.X: dims {...} are not columns in fields and have more than one value` | Add the dim to `fields`, `sel`/`isel` one value, or reduce it upstream |
| `datasets.X.fields.col: 'src' is not a dim, coord, or variable` | Lists the input's dims, coords and variables; run `--describe` |
| `datasets.X.sel.dim ... matches nothing` / `selects no values` | Gives the coordinate's range |
| `datasets.X.bbox ... contains no data` | The box misses the grid, or is not `[N, W, S, E]` |
| `datasets.X.zarr 'n' is not an input` | The binding names an input that was not passed with `-i` |
| `spec...encoding.color.field 'f' is not a column of 'X'` | Lists the columns the dataset has (including transform outputs) |
| `spec... draws a mark but has no data` | Add `"data": {"name": ...}` to the view or a parent |
| `....scale.scheme 'x' is not a palette` | Lists the weather palettes; any Vega scheme also works |
| `not valid Vega-Lite 6.4: <path>: ...` | A key or value that Vega-Lite does not have, with the allowed values where there is a short list. Check that key in the Vega-Lite docs |
| `datasets: N bound rows ... over the 500000 row limit` | Crop, thin or coarsen (or `--max-rows`) |

Data problems (unreadable input, Natural Earth download failure) exit 1.

## Output, QA and provenance

- The file at `-o`. Stdout lists `Wrote: PATH`, one `bound NAME: N rows (columns)`
  line per dataset, one `default ...` line per default applied, then for PNG/JPEG
  `plot hash: <sha256 of RGB pixels>` and `data: not null (precip 8500/8500 finite)`
  or `data: NULL`. `NULL` means every plotted variable is all-NaN after
  `sel`/`bbox`: check the selection with `--describe`.
- PNG and JPEG carry a `weather_skills_history` provenance record (and the
  provenance mark when the input chain is intact); HTML carries it in a
  `<meta>` tag. The record holds the spec as you wrote it (before binding and
  defaults) and the input names, paths and GeoJSON hashes.
- Natural Earth files (v5.1.2) are cached in `$WS_NE_CACHE`, default
  `~/.cache/weather-skills/naturalearth`. With no network, copy the
  `ne_<scale>_<layer>.geojson` files there.
- Dates render in UTC.

## When to use something else

- One obs week against week 1–4 forecasts with a hits row: `plot-verify`.
- The matplotlib/cartopy figures (`plot`): existing workflows that already
  have a `plot` spec. New figures can use either; this skill accepts any
  Vega-Lite chart type.
