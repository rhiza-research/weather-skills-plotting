---
name: plot
description: "Draw weather-skills Zarrs as any Plotly figure: maps (heatmap, contour, stations, wind arrows), panel grids, time series, ensemble plumes and bands, day-of-year season overlays, bars, xy scatter, cross-sections, and animated maps, saved as PNG, JPG, PDF, SVG, interactive HTML, or GIF. The spec is Jsonnet that evaluates to a standard Plotly figure; strings starting with @ name the data."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG, JPG, PDF, SVG and GIF export needs Chrome (installed, or `plotly_get_chrome -y`). Self-contained; the plotting library ships in scripts/.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "1.0.10"
  catalog-group: figure
---

# plot

Draws a figure from a Jsonnet spec. The spec evaluates to a standard [Plotly figure](https://plotly.com/python/reference/) (`data`, `layout`, `frames`). Wherever Plotly expects data, write a string that starts with `@` and names it: `'@OBS.precip.isel(time=0)'`. Name every input on the command line.

## How a figure is made: spec → render → lint → bind → export

1. **Spec.** You write Jsonnet: Plotly keys for everything drawn, and an `@` reference wherever data goes (`x: '@OBS.lon'`, `z: '@OBS.precip.isel(time=0)'`). Each input is named with `-i FILE=NAME`; `std.extVar('inputs')` describes them (dims, variables, dates, bbox) for loops and titles.
2. **Render.** plot evaluates the Jsonnet into plain Plotly JSON, references still unbound. `--dump-spec -` prints this.
3. **Lint.** Before any data is read, the JSON is checked against Plotly's schema: every key that can put data on the chart must hold an `@` reference, never typed-in values. That covers data keys (`x`, `y`, `z`, `lat`, `customdata`, `values`, …), per-point lists in keys like `marker.color`, `marker.size` and `text` (one value there is styling), keys that generate a value for every point (`x0` / `dx`, `base`, error-bar `value`), the coordinates of shapes, annotations and images on a data axis (`xref: 'x'`), menu and slider `args`, frames and templates. Keys Plotly doesn't define are refused, since they can't be checked. Every problem is listed at once. A constant on a data axis (a threshold line, a date) is `--const NAME=VALUE`, written `'@const.NAME'`. Positions in `paper` or `x domain` units (titles, colorbars, panel labels) are layout, not data, and stay literal.
4. **Bind.** Each reference is resolved from its input: it selects, reshapes or labels stored values, or scales a marker's size in pixels (see `@` references below), and its shape is checked against the key.
5. **Export.** Plotly validates the figure, and it is written to each `-o` with its QA lines (see Output).

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i rain_week.zarr=OBS -i kenya.geojson=KENYA \
  --spec map.jsonnet -o map.png
```

Start from a recipe. `--recipe` lists them, `--recipe NAME` prints one to copy and edit, and `--spec NAME` runs one as is (its `// plot.py …` comment line is the command; the files are in `${CLAUDE_SKILL_DIR}/recipes/`).

| Recipe | Draws |
| --- | --- |
| `map.jsonnet` | One map: a grid on a stepped palette, a GeoJSON outline, the base map |
| `stations.jsonnet` | Station dots over a grid on one colorbar, labelled with their ids |
| `panels.jsonnet` | One map per forecast step in a grid, one colorbar, panel titles |
| `members.jsonnet` | Ensemble members in grey and the mean in bold, at the cell nearest a point |
| `band.jsonnet` | A shaded 10–90% band between two quantile lines, with observations |
| `sd_band.jsonnet` | Mean ± 1 SD as a shaded band (stacked fills), with the mean as a line |
| `seasons.jsonnet` | Past years and a forecast plume on one day-of-year axis |
| `wind.jsonnet` | Wind speed shading with quiver arrows as long as the wind is strong (wind-speed-direction `--arrow-length`) |
| `wind_markers.jsonnet` | Wind arrows as Plotly markers sized in pixels by speed (`@…speed * k`), with no extra data step |
| `animation.jsonnet` | A map played through time: HTML with play / slider, or a looping GIF |
| `cross_section.jsonnet` | A field over longitude and pressure, 1000 hPa at the bottom |
| `bars.jsonnet` | Horizontal bars per county from a name coordinate |
| `scatter_xy.jsonnet` | One variable against another, with year labels and a threshold line |
| `verify_grid.jsonnet` | Observation and each lead's forecast on one colorbar, verify hits maps underneath |
| `mediogram.jsonnet` | Forecast members vs model climate as boxes per lead at a point, with the forecast mean |
| `windrose.jsonnet` | Wind observations on polar axes by the direction they blow from, colored by speed |
| `mslp.jsonnet` | Labelled isobars every 4 hPa with H / L and central pressure from local-extrema |

### Arguments
- `-i`, `--input` — `PATH=NAME`, repeat. A Zarr, or a GeoJSON (`.geojson` / `.json`) of outlines. `NAME` is a letter or `_`, then letters, digits and `_` (`OBS`, `fc_week1`); it is how the spec refers to the file. Readable legend text goes in a trace's `"name"`, not here.
- `--spec` — a `.jsonnet` / `.json` file, a recipe name (`map`), or the Jsonnet text itself.
- `--recipe [NAME]` — list the recipes, or print one's Jsonnet; draws nothing.
- `--const NAME=VALUE` — a constant to place on a data axis as `'@const.NAME'`: a threshold line (`--const el_nino=0.5`), a date. Numbers or text; repeat.
- `--dpi N` — pixel density of PNG, JPG and GIF output. The layout is in CSS pixels at 96 dpi (the default); `192` doubles the pixels at the same layout, `300` is print quality. `layout.width` / `height` set the layout itself.
- `-o`, `--output` — `.png`, `.jpg`, `.pdf`, `.svg`, `.html`, or `.gif` (plays the spec's `frames`). Repeat to write several.
- `--dump-spec` — print (`-`) or save (a path) the evaluated spec, `@` strings unresolved, and draw nothing.
- `--ext-str KEY=VALUE` — read in the spec as `std.extVar('KEY')`; repeat.

## The spec

It is ordinary Jsonnet. Use `local` variables for anything repeated, so long strings (selections, colors) are written once:

```jsonnet
local ws = import 'ws.libsonnet';               // helpers, below
local inputs = std.extVar('inputs');           // what each input holds
local day = '.isel(time=0)';
{
  data: [
    { type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip' + day, coloraxis: 'coloraxis' },
  ],
  layout: ws.map(inputs.OBS.bbox) + {
    title: { text: 'Rainfall %s' % inputs.OBS.coords.time[0] },
    coloraxis: ws.stepped(ws.palettes.ppt_daily),
  },
}
```

**Changing part of a helper's output.** With `+`, a field you name replaces the helper's field entirely; with `+:` it is merged in. `ws.map(b)` sets `margin: {l: 50, r: 150, t: 70, b: 70}`:

```jsonnet
ws.map(b) + { margin: { l: 110 } }    // margin becomes {l: 110}: r, t, b are lost and the colorbar is cut off
ws.map(b) + { margin+: { l: 110 } }   // margin becomes {l: 110, r: 150, t: 70, b: 70}: only l changes
```

Use `+:` the same way for `xaxis+:`, `coloraxis+:`, and `annotations+:` (which adds to the list instead of replacing it).

**`std.extVar('inputs')`** describes each input, read from its metadata without loading data: `dims` (sizes), `vars` (each one's `dims`, `units`, `long_name`), `coords` (values of 1-D coordinates up to 400 long, and scalar ones: dates as `2026-10-01`, or `2026-10-30T12:00:00` when not midnight; leads as days, `0.125` for 3 h; members, station ids; `valid_time` when the file has it), `attrs`, and `bbox` (`{n, w, s, e}`, from lat / lon coordinates; a grid across the dateline gets `e` past 180, e.g. 150 to 210). Use it for loop bounds, titles and map windows; `ws.date(t)` turns a date into `26 Oct 2026`. A GeoJSON input has `bbox`. To see it all: `--spec "std.extVar('inputs')" --dump-spec -` with your `-i` inputs.

### `@` references
A string that starts with `@` is replaced by the data it names; the whole string is the reference, so a reference can't sit inside other text (titles take their dates and names from `inputs`). A string that starts with `@@` is the literal text after the first `@`.

| Form | Gives |
| --- | --- |
| `@OBS.precip`, `@OBS.time`, `@OBS.county` | A variable or coordinate |
| `@OBS.lat`, `@OBS.lon` | The latitude / longitude coordinate, whatever the file calls it |
| `.isel(time=0)`, `.isel(time=-1)`, `.isel(time=slice(0, 7))` | Pick by position (`slice(None, None, 3)`: every 3rd) |
| `.sel(time='2026-10-01')`, `.sel(lat=-1.3, lon=36.8, method='nearest')`, `.sel(station_id=['A', 'B'])` | Pick by value |
| `.dropna('station_id')` | Keep the positions along a dim that have a value (this map's local-extrema centres) |
| `.lon`, `.lat`, `.time`, any coordinate, after a selection | That coordinate of what is left: `@HI.msl.isel(time=0).dropna('station_id').lon` |
| `.squeeze()`, `.transpose('vertical', 'lon')` | Drop size-1 dims, set dim order (pick every other dim first) |
| `.lon360()`, `.lon180()` | A field whose window crosses the edge of its longitudes, drawn in one piece. A file stored as -180 to 180 jumps from 180 back to -180 at the dateline, so a Pacific map (170°E to 170°W) would split into two strips at the sides; `.lon360()` relabels the longitudes 0 to 360 and puts the columns in order. A file stored as 0 to 360 does the same at the prime meridian (Africa from 340 to 40); `.lon180()` relabels them -180 to 180. Use it on the field and on its longitudes: `z: '@X.sst.isel(time=0).lon360()'`, `x: '@X.sst.isel(time=0).lon360().lon'`. `inputs.X.bbox` already gives the unbroken window, and `ws.map` / `ws.grid` label a window past 180° as 170°E, 180°, 170°W |
| `.flat()`, `.flat('lon')`, `.flat('step')` | A 2-D selection as one value per cell, and a dim's coordinate for each value (leads in days): grid cells as scatter points, or every member with its lead for one box per lead |
| `.dt.dayofyear`, `.dt.year`, `.dt.month`, `.dt.day`, `.dt.hour`, `.dt.days`, `.dt.strftime('%d %b')` | Time labels (`.dt.days` of a lead time) |
| `.attrs.units` | A text attribute |
| `… * 2`, `… / 3 + 4`, `… * const.k` | A size in pixels from the data: + − × ÷ by a number or `@const` value, with data on one side only. Only on `marker.size`, `marker.standoff`, `marker.line.width`, `textfont.size` (arrows sized by wind speed, dots by rainfall) |
| `.min()`, `.max()`, `.quantile(0.98)` | One number for a scale only: `zmin`, `zmax`, `zmid`, `cmin`, `cmax`, `cmid`, an axis `range`, `tickvals` |
| `@KENYA.x`, `@KENYA.y` (or `.lon`, `.lat`) | A GeoJSON input's lines and rings, gaps between parts |
| `@NE.coastline_50m.clip(n, w, s, e).x` | Built-in Natural Earth lines: `coastline`, `borders`, `disputed`, `lakes`, `rivers` at `10m` / `50m` / `110m`, `admin1` at `10m` |

Shapes: `z` is 2-D (a lat/lon grid is drawn with rows as latitudes, and needs `x: '@NAME.lon', y: '@NAME.lat'` beside it); `customdata` 1-D or 2-D; everything else one value or 1-D. A trace's `x` and `y` (not a gridded one's) must pair up: the same length, and from two files the same time (or other) values; otherwise it's an error suggesting `merge`. Traces on one `coloraxis` holding different units print a warning. A dim of length 1 (the one time of a period total) is dropped when there are too many; any other leftover dim is an error naming it: pick a value with `isel` / `sel`, or draw one trace per value with a Jsonnet loop (`for m in std.range(0, inputs.ENS.dims.number - 1)`).

References select and label stored values; they never compute, except a size in pixels (the arithmetic row above), which changes how big a marker is on screen, never what is drawn. Arithmetic, averages and smoothing come from data skills first, and the error says which: `summarize-dim` (mean, quantiles over members), `aggregate-temporal` (rolling, resampling), `unit-convert`, `difference`, `coarsen` / `downscale`, `clip-region` (masks), `step-to-time` (valid dates), `wind-speed-direction` (speed and direction from u / v, and with `--arrow-length` quiver arrows as line segments). A mean ± SD band is Plotly stacking: mean − SD from `difference`, then the SD stacked on it twice (`--recipe sd_band`).

### `ws.libsonnet`
`local ws = import 'ws.libsonnet';` gives plain Plotly JSON; change any part with `+`. Imports are found by name in the skill's library (`ws.libsonnet`, `palettes.libsonnet`, `themes/…`), its recipes, beside the spec file, and in the working folder, so a palettes file written there (`local mine = import 'my_palettes.libsonnet';`) needs no flag.

- `ws.map(bbox, width=760, pad=0.03)` — one map's axes (equal degrees, range from `bbox` widened by `pad`), a canvas sized to it, and the legend in a row under the map.
- `ws.pad(bbox, frac=0.03)` — `bbox` widened on every side by `frac` of its larger span. `inputs.NAME.bbox` runs between the outermost cell centres, so `ws.map`, `ws.grid` and `ws.basemap` pad it by 3% so edge cells and outlines aren't cut; `pad=0` keeps the box exact.
- `ws.grid(bbox, rows, cols, panel=340, gap=0.04, pad=0.03, empty=[])` — axes for maps in a grid, filled row by row. `empty` lists panels with no map: they are hidden, and tick labels go on the lowest filled panel of each column and the leftmost of each row. Panels showing different regions: set `xaxisN+: {range: […], showticklabels: true}` (and `yaxisN+:`) from `ws.pad(their bbox)`. `ws.rowTitle(i, text)` labels the row that starts at panel `i`. `ws.axes(i)` gives panel `i`'s `xaxis` / `yaxis` (`x`, `x2`, …) to add to a trace; `ws.panelTitle(i, text)` an annotation above it (add titles with `annotations+:` after `ws.classBar`). `ws.axes` and `ws.panelTitle` work for chart panels too; lay those out with Plotly's own `layout.grid: {rows, columns, pattern: 'independent'}`.
- `ws.basemap(bbox, i=0, coastline=true, borders=true, disputed=true, lakes=true, rivers=true, admin1='auto', style={}, pad=0.03)` — base-map lines on panel `i`, clipped to the same padded box as `ws.map` / `ws.grid`. Every layer is on unless switched off by name: `admin1` (`'auto'`: drawn on maps up to 20° across; `true` / `false` forces it), `rivers`, `lakes` (always drawn opaque over the data unless `lakes=false`), `borders` (agreed international boundaries), `disputed` (every other land line, dashed) and `coastline`, drawn in that order. "No disputed borders" is `ws.basemap(bbox, disputed=false)`; fewer lines on small panels, `rivers=false, admin1=false`. `style={admin1: {line: {color: 'white'}}}` restyles a layer by the same names. Land and sea are not filled. A GeoJSON input draws boundaries of your own.
- `ws.classBar(palette, title='', axis='coloraxis', x=1.03, y=0.05, len=0.85, width=0.03, format='%g')` — for a class palette: the `coloraxis` with color steps at the class bounds, and a colorbar with one equal-height band per class, labelled at the bounds (or by the palette's `labels`), under / over as triangles. It is drawn as layout shapes and annotations, so write your own as `annotations+: [...]` after it. `y` (the bottom of the bands) and `len` place it, as fractions of the plotting area, when a figure has two: e.g. `y=0.55, len=0.4` and `y=0.05, len=0.4`; leave room for the under / over triangles and the title between them. Keep `title` short (`mm`, `m/s`): it sits above the bar.
- `ws.stepped(palette)` — the coloraxis object itself, with Plotly's own colorbar: `coloraxis: ws.stepped(p)` (or `coloraxis2:`). Use it for continuous palettes (no `bounds`), with `cmin` / `cmax` / `cmid` added by `+`.
- `ws.palettes.NAME` — `{colors, bounds}`: rainfall totals `ppt_daily` (0–50 mm), `ppt_week` (0–200, also a dekad), `ppt_month` (0–400), `ppt_season` (0–1000), `ppt_total` (0–2500); anomalies `ppt_anom_daily` … `ppt_anom_season` (±50 / ±200 / ±300 / ±500); `ppt_poa` (% of normal), `spi`, the masters they are cut from `ppt_master`, `ppt_anom_master`; `ppt_spp`; verify maps `hits` (classes with labels); continuous (no bounds, for `ws.stepped`): `bias`, `precip_bias`, `mae`, `wind_rose`, `colorblind`, `rocket`. Your own: `{colors: [...], bounds: [...]}`, one color per class, or under + classes + over; `labels: [...]` names the classes.
- `ws.date(t, year=true)` — `'2026-10-26'` → `26 Oct 2026`; a time not at midnight adds `12 UTC`.
- `ws.dayOfYearTicks` — `xaxis` ticks at the 1st of each month for a `.dt.dayofyear` axis (counted in a non-leap year; after 28 Feb a leap year sits a day later).
- `ws.player(names, duration=500)` — play / pause buttons and a slider for frames named `names`; a `.gif` plays at the same `duration` (ms).
- `ws.template` — the house colorway (no grey, kept for ensemble members), as `layout.template`. Without it the plot area is Plotly's default grey-blue.
- `import 'themes/tropical_tidbits.libsonnet'` — Tropical Tidbits palettes: `tt_precip_rate` (mm/h), `tt_precip_total`, `tt_pwat` (mm), `tt_wind` (m/s), `tt_z500` (dam).

## Notes
- A season across New Year (Oct–Feb) on one axis: `x: '@Y.time.dt.strftime("%d %b")'` with `xaxis: {type: 'category', categoryorder: 'array', categoryarray: '@LEAP.time.dt.strftime("%d %b")'}`, the order taken from one input that covers the season in a leap year.
- A second y axis (`overlaying: 'y'`) syncs its ticks to the first by default; set `tickmode: 'auto'` on it for round numbers.
- The base map downloads Natural Earth shapefiles on first use (cartopy, network needed); later runs reuse them.
- Titles don't wrap: break a long one with `<br>`, or put the detail in `title.subtitle`.
- A log axis (pressure) labels Plotly's minor ticks too; set `tickvals` to the levels (`tickvals: '@RH.vertical'`).
- Values are drawn in the file's own units (K stays K, Pa stays Pa): run unit-convert for °C or hPa, and set palette bounds and contour levels in those units.
- A forecast's `step` is a lead time. Run step-to-time to draw it by valid date beside observations, or use `.dt.days` for lead days.
- Animations: `frames[k].data` replaces the traces listed in `frames[k].traces` (by position in `data`). Keep the base map out of the frames: it stays on every frame. A scatter trace in the frames must be `scattergl`: an SVG `scatter` there blanks the heatmap on every other paint, so the map flashes. For moving wind arrows use the `wind` recipe's lines quiver (already `scattergl`), not `wind_markers` (`scattergl` has no `marker.standoff`, so its heads would sit mid-shaft).
- A still image takes at most 100 panels; play more as frames.
- Errors come from Jsonnet (syntax, unknown field), from the reference checks (which data, which dim, which skill), or from Plotly itself, naming the trace and its type (`data[3].line: a heatmap has no property 'line'`), with what to do for the usual mix-ups.

## Output
The figure at each `-o`. Every output prints `plot hash:` (of the pixels for PNG / JPG / GIF, of the figure JSON for PDF / SVG / HTML) and `data: not null | NULL` over the plotted traces, frames included; a trace that is all NaN gets its own line. A GIF also prints its frame count and size, with a warning above 8 MB, which many chat clients and slide tools won't show inline; an animated HTML prints its frame count and figure size, with a warning above 50 MB. The provenance (`weather_skills_history`, with the evaluated spec) is embedded in the file; read it with the provenance skill. A PNG, JPG, GIF, SVG or PDF whose history is complete carries a small red seal in its bottom-right corner.
