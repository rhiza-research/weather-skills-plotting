---
name: plot
description: "Draw weather-skills Zarrs as maps (heatmap, contour, stations, wind arrows), time series, xy scatter plots, wind roses, forecast verification grids (obs, lead-week forecasts and their hits / bias / MAE maps), ECMWF-style mediograms (forecast vs model-climate ensembles at a point), or animated maps through time, saved as PNG, JPG, interactive HTML, or GIF. Titles, colors, panels, and layout are set with a standard Plotly figure JSON."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`). Self-contained; the plotting library ships in scripts/.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "1.0.5"
  catalog-group: figure
---

# plot

Draws one or more Zarrs as a figure. Name the files on the command line; set titles, colors, and layout in `--spec`.

**A plot is a standard Plotly figure spec, plus one custom piece: data bindings that put real data from your files into it.** `plot` builds a default spec from your inputs, one trace per file, then merges your `--spec` on top: keys you set replace the default, keys you leave out keep it. `--dump-spec -` prints that merged spec without the data arrays, so you can see exactly what will be drawn, edit it, and pass it back as `--spec`.

Always write standard Plotly: every key means what the [Plotly reference](https://plotly.com/python/reference/) says. Use the `meta` key, Plotly's own slot for custom data, to control how real data goes into the plot. A trace's `meta` holds its data binding: which variable to draw (`source.variable`), which slice (`source.isel` / `source.sel`), which variables go on each axis (`x`, `y`), and which dim becomes panels or lines (`facet`, `along`). See **Data bindings** for every `meta` key.

`meta` only binds data; it does not change it. Prepare the data with the data skills first: clip-region to cut a region or mask outside a polygon, point-value to sample a point, summarize-dim for means and percentiles. The map window is Plotly's own `xaxis.range` / `yaxis.range` (x is longitude).

## Usage

```bash
# One map (or one panel per time / step)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i rain.zarr -o rain.png
# Maps side by side, each on its own grid
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps.zarr=OBS -i ecmwf.zarr=FC -o compare.png
# Area means or stations as lines on one time axis
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_area.zarr -i imerg_area.zarr -o rain.png
# Layers on one map, bottom first
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer heatmap:rain.zarr --layer scatter:stations.zarr --layer outline:kenya.geojson -o map.png
# One variable against another
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i iod_rain.zarr -o iod_vs_rain.png --spec '{"data": [{"uid": "0", "meta": {"x": "dmi", "y": "precip"}}]}'
# Verification grid: obs, then each lead's forecast and verify map
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --obs chirps_week.zarr --forecast ecmwf_w1.zarr --verify verify_w1.zarr --forecast ecmwf_w2.zarr --verify verify_w2.zarr -o verify.png
# Mediogram: forecast ensemble vs model climate at one point (point-value outputs)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --mediogram -i forecast_nairobi.zarr -i mclimate_nairobi.zarr -o mediogram.png
# Any map animated through time, as interactive HTML: here rain under isobars, inside an outline
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --animate --layer heatmap:rain_daily.zarr --layer contour:msl_daily.zarr --layer outline:kenya.geojson -o rain.html
# The same animation as a looping GIF, for slides or chat
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --animate -i rain_daily.zarr -o rain.gif
```

The plot type follows the data: a lat/lon grid is a colored map, stations are colored markers, 1-D series are lines on one time axis. `meta.x` / `meta.y` scatter two variables or coordinates; a name coordinate such as `county` becomes a category axis (a dot chart: `"meta": {"x": "precip_7d", "y": "county"}`). `--obs`/`--forecast`/`--verify` and `--mediogram` pick the two special figures (sections below); `--animate` plays any map through time instead of drawing side-by-side panels. Use one of the three at a time.

### Arguments
- `--input`, `-i` — Zarr to draw, as `PATH` or `PATH=UID`; repeat for side-by-side maps or more lines. `UID` (letters, digits, `_`, e.g. `WRF`) is the trace's `"uid"` in `--spec`; legend text goes in that trace's `"name"`, panel titles in a `panel-title-N` annotation.
- `--layer` — `KIND:PATH` or `KIND:PATH=UID` to stack on one map; repeat. Kinds: `heatmap`, `contour` (over a heatmap: labeled black lines, every 4 hPa for sea-level pressure; `"contours": {"coloring": "fill"}` fills it), `scatter` (stations; `"mode": "markers+text"` labels each with its `name` coordinate, else its id; local-extrema highs / lows print as a blue H / red L over the central value, restyled by a trace with that layer's uid), `quiver` (wind u/v: a speed field UID and arrows UID-arrows, each picking its own `isel` / `sel`), `outline` (GeoJSON). `outline` layers also combine with `-i` inputs (`-i grid.zarr --layer outline:counties.geojson`); `-i` itself takes Zarr paths only.
- `--obs`, `--forecast`, `--verify` — verification grid: the observation for one week, then each lead's forecast (repeat, week-1 first) and its verify-skill output (once per `--forecast`, same order). See **Verification grid**.
- `--mediogram` — forecast vs model climate at one point; pass `-i` twice (forecast, then m-climate), each a point-value output. See **Mediogram**.
- `--animate` — the same map, with its times or steps played as frames; takes the same `-i` / `--layer` inputs. `-o` must end in `.html` or `.gif`. See **Animation**.
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — house style: Plotly `template`, `palettes`, per-field `defaults`, element `styles`, base-map `overlays` (see Colors); or a shipped theme by name, e.g. `tropical_tidbits`.
- `--scale` — PNG/JPG/GIF pixel multiplier (default 1): `2` doubles the resolution, not the layout.
- `--dump-spec` — print (`-`) or save (a path) the spec, without drawing.
- `--output`, `-o` — `.png`, `.jpg`, `.html`, or `.gif` (`--animate` only).

### Customizing with `--spec`
`--spec` changes the defaults. It takes standard [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`; write only the parts you change. Data bindings go in `meta` (see **Data bindings**).

Each input file is one entry in `data`. Name it on the command line (`-i ecmwf.zarr=FC`) and put that name in `"uid"`. Unnamed files are `"0"`, `"1"`, … in order.

A trace's `uid` is its file's UID when one is given, else its position: `-i a.zarr=West` is `"uid": "West"`, and `"0"` then matches nothing (plot stops). Copy uids from the `-i` line, or run `--dump-spec -` to see them. UID is an id (letters, digits, `_`); it is also the default legend and panel text until the trace sets `"name"` (legend text such as `"TAHMO (automatic)"`) or a `panel-title-N` annotation its title.

```bash
# Two named files, restyled by name: bars per county, one panel each
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i west.zarr=West -i east.zarr=East -o counties.png --spec '{"data": [
  {"uid": "West", "type": "bar", "meta": {"x": "county", "y": "precip"}},
  {"uid": "East", "type": "bar", "meta": {"x": "county", "y": "precip"}, "xaxis": "x2", "yaxis": "y2"}],
  "layout": {"xaxis": {"domain": [0, 0.46]}, "xaxis2": {"domain": [0.54, 1]}, "yaxis2": {"anchor": "x2"}}}'
# Named lines: legend names and colors
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_area.zarr=CHIRPS -i imerg_area.zarr=IMERG -o rain.png --spec '{"data": [
  {"uid": "CHIRPS", "line": {"color": "black"}}, {"uid": "IMERG", "name": "IMERG Late", "line": {"dash": "dash"}}]}'
# Named layers: the uid is the UID after the path
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer heatmap:rain.zarr=RAIN --layer contour:msl.zarr=MSLP -o map.png --spec '{"data": [
  {"uid": "RAIN", "zmin": 0, "zmax": 50}, {"uid": "MSLP", "contours": {"size": 2}}]}'
```

Every row below assumes `-i ecmwf.zarr=FC`.

| To | `--spec` |
| --- | --- |
| Set the title | `{"layout": {"title": {"text": "Week 1"}}}` |
| Add a second title line | `{"layout": {"title": {"text": "ECMWF rainfall", "subtitle": {"text": "Week 1: 16–22 Oct"}}}}` or `<br>` in `text` |
| Title a panel | `{"layout": {"annotations": [{"name": "panel-title-2", "text": "ECMWF"}]}}` |
| Pick one step | `{"data": [{"uid": "FC", "meta": {"source": {"isel": {"step": 0}}}}]}` |
| Pick the variable to draw | `{"data": [{"uid": "FC", "meta": {"source": {"variable": "iod_mode_index"}}}]}` |
| Set the color range | `{"data": [{"uid": "FC", "zmin": 0, "zmax": 100}]}` |
| Set the map window | `{"layout": {"xaxis": {"range": [33.5, 42.5]}, "yaxis": {"range": [-5, 5.5]}}}` |
| Draw contours | `{"data": [{"uid": "FC", "type": "contour"}]}` |

`isel` counts from 0 (`-1` is the last); `sel` picks by label. On a map `xaxis` is longitude and `yaxis` latitude; side-by-side maps have their own `xaxis2` / `yaxis2`, …. `--help` lists every option; `--dump-spec -` shows the spec for your files.

### Data bindings
`meta` is the only part of the spec that is not plain Plotly. It binds a trace to its data: which file, variable and slice fill it, and which dims become panels or lines. Plot stops on a `meta` key it does not know, and a removed key's error names what does the job now.

A trace finds its file by `uid`: the UID after `=` on the command line, else the file's position.

```bash
# uid "OBS" is chirps.zarr, uid "FC" is ecmwf.zarr
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps.zarr=OBS -i ecmwf.zarr=FC -o compare.png --spec '{"data": [
  {"uid": "OBS", "name": "CHIRPS"},
  {"uid": "FC", "name": "ECMWF week 1", "meta": {"source": {"isel": {"step": 0}}}}]}'
```
`"name"` is ordinary Plotly legend text; `meta` is the binding.

Every trace `meta` key, with an example (`{"data": [{"uid": "FC", "meta": EXAMPLE}]}`):

| Key | Binds | Example |
| --- | --- | --- |
| `source.variable` | The data variable to draw; required when the file holds more than one. | `{"source": {"variable": "tp"}}` |
| `source.isel` | A slice by position, from 0 (`-1` is the last). One integer draws one value; a list keeps the dim, one panel each; a range `{"start", "stop", "step"}` takes every Nth. | `{"source": {"isel": {"step": [0, 1]}}}` |
| `source.sel` | A slice by label, nearest for numbers and dates. | `{"source": {"sel": {"time": "2026-09-21"}}}` |
| `source.input` | The input that fills the trace (its UID, else its position). `plot` sets it from `-i` / `--layer`; set it to draw another input. | `{"source": {"input": "OBS"}}` |
| `source.u` / `source.v` | Wind components, when they are not found by name. | `{"source": {"u": "u100", "v": "v100"}}` |
| `source.geojson` | An outline trace's GeoJSON file (`--layer outline:` sets it). | `{"bind": "geojson", "source": {"geojson": "tana.geojson"}}` |
| `x` / `y` | Variables, or a name coordinate such as `county`, drawn one against the other. | `{"x": "dmi", "y": "precip"}` |
| `facet` | The dim drawn as one panel per value (default `step` or `time`); `false` for none. | `{"facet": "number"}` |
| `along` | The dim drawn as one trace per value, uid `UID-DIM-VALUE`: lines share one color and one legend entry, bars get a color each. A data entry with a member's uid styles that member. | `{"along": "number"}`, then `{"uid": "FC-number-0", "line": {"color": "red"}}` |
| `align` | `dayofyear` puts every year on one seasonal axis. | `{"align": "dayofyear"}` |
| `palette` | Color classes for the field (see **Colors**). The one `meta` key that styles rather than binds. | `{"palette": "ppt_week"}` |
| `arrows` | Wind arrow length, in map degrees per unit of speed (default: the 95th-percentile speed spans about one arrow spacing). Fewer arrows: thin the grid with `source.isel` range steps. | `{"arrows": {"scale": 0.05}}` |
| `bind` | How the data fills the trace (`field`, `speed`, `arrows`, `points`, `geojson`, `series`, `xy`, `samples`, `windrose`). `plot` picks it from the data and trace type; `--help` BINDS lists them. | `{"bind": "speed"}` |

`layout.meta` holds only what `--dump-spec` writes so a spec can be replayed: `inputs` (`{id: path}`), `version` and `skill`. Leave them as dumped.

Done elsewhere, not in `meta`:

| To | Use |
| --- | --- |
| Cut the data to a region, or blank cells outside a polygon | clip-region before plotting |
| Zoom the map | Plotly `xaxis.range` / `yaxis.range` on each panel's axes (x is longitude). For H / L marks, run local-extrema on the wider field and zoom with the ranges: a field clipped first has too little room around its centres to find them |
| Sample a point (mediogram, wind rose) | point-value before plotting |
| Percentile band | summarize-dim `--method quantile`, then Plotly `"fill": "tonexty"` (see **Lines over time**) |
| Hide or restyle base-map layers | a data entry with the layer's uid: `{"uid": "rivers", "visible": false}` (uids `coastline`, `borders`, `disputed`, `lakes`, `rivers`, `admin1`) |
| Animation speed | Plotly `layout.updatemenus` / `sliders` (see **Animation**) |
| Higher-resolution PNG/JPG | `--scale 2` |

### Output
The figure at `-o`. PNG/JPG also print `data: NULL` when every value drawn is NaN.

### Notes
- A file with more than one data variable needs `meta.source.variable` set to the one to draw. Plot stops rather than guess; inspect-zarr lists the variables.
- A map shows one value per cell: pick one value of any extra dim (`number`, `vertical`) with `isel` / `sel`, panel it with `"meta": {"facet": "number"}`, or average it first with summarize-dim.
- Plot draws the values in the file, in its units (K stays K, Pa stays Pa; run unit-convert for °C or hPa), so `zmin`, contour levels and palette edges are in those units. A precip rate stays a rate (mm/day); for period totals (mm) run aggregate-temporal, then convert-to-totals.

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_week_kenya.zarr=CHIRPS -i ecmwf_week_kenya.zarr=ECMWF -o obs_vs_fc.png --spec '{
  "data": [{"uid": "ECMWF", "meta": {"source": {"isel": {"step": 0}}}}],
  "layout": {"title": {"text": "Week 1 rainfall"}}}'
```
CHIRPS and ECMWF week-1 rainfall side by side over Kenya (both cut to Kenya with clip-region first), each on its own grid, with one shared colorbar.

## Details

### Panels and layers
- A file with several times or steps gets one panel each, titled with its date. `layout.grid.rows` / `columns` set the grid; `xgap` / `ygap` the spacing, as a fraction of a panel. A still image takes at most 100 panels and stops with an error past that: pick times with `meta.source.isel` / `sel` (or the select skill), aggregate first, or use `--animate`, which has no limit.
- Panels showing the same quantity share one colorbar. To split one off: `{"data": [{"uid": "FC", "coloraxis": "coloraxis2"}]}`.
- Panel titles are annotations named `panel-title-1`, `panel-title-2`, …; set one's text with `{"layout": {"annotations": [{"name": "panel-title-2", "text": "GEFS · hit 78% · BER 15%"}]}}`. The text takes any characters, and `<br>` for a second line. Side-by-side files default to their `-i` UID (else the file name) as the title, but UID is an id of letters, digits and `_`: put title text in the annotation, not in UID.
- Maps use plain x/y axes in degrees (x = longitude). Add points or lines as `scatter` traces with `x` / `y`, and boxes as `layout.shapes` with `xref: "x"`, `yref: "y"`.
- An `outline` layer frames the map unless the axes' `range` is set, and hides the built-in admin-1 lines (unless a `{"uid": "admin1"}` entry asks for them). Use it to draw official boundaries.
- The base-map layers are traces with uids `coastline`, `borders`, `disputed` (dashed: disputed and indefinite lines), `lakes`, `rivers` and `admin1`, drawn on every panel: `{"data": [{"uid": "rivers", "visible": false}, {"uid": "borders", "line": {"width": 2}}]}`. Naming `admin1` draws county / province lines on a map too large to show them by default.
- The canvas fits the maps (up to 760×560 px for one map, 340×340 px per panel in a grid). `layout.width` / `height` fix it.

### Lines over time
- A series runs along `time`, or for a forecast along its valid date (init time + `step`). Every other dim must go: pick one value with `isel` / `sel`, draw one line per value with `"along": "number"` (or `"station_id"`: a station file is a map until you pick or `along` its stations), or average it first with summarize-dim (for an area mean, `--dim latitude --dim longitude --method mean --lat-weighted`).
- Each 1-D file is one line on one shared axis (up to 26 files). The legend names it after its file, or its station id; `"name"` renames it. With two or more lines the legend sits in rows above the plot; one line has none.
- Each line uses only its own settings, as in Plotly: set `along`, `align` or `source.variable` (see **Data bindings**) on every line that needs it.
- `"along": "number"` draws one trace per member, uid `UID-number-0`, `UID-number-1`, …, in one color under one legend entry. Style a member by its uid: `{"uid": "FC-number-0", "name": "Control", "showlegend": true, "line": {"color": "red"}}`. With `"type": "bar"`, `along` gives one bar series per value, each its own color.
- A percentile band is two lines Plotly fills between. Run summarize-dim `--dim number --method quantile -q 0.1 -q 0.9`, pass the result twice, and fill the upper line down to the lower: `-i q.zarr=LOW -i q.zarr=HIGH --spec '{"data": [{"uid": "LOW", "mode": "lines", "line": {"width": 0}, "showlegend": false, "meta": {"source": {"sel": {"quantile": 0.1}}}}, {"uid": "HIGH", "name": "10–90%", "mode": "lines", "fill": "tonexty", "line": {"width": 0}, "meta": {"source": {"sel": {"quantile": 0.9}}}}]}'`. LOW must come before HIGH. Add the ensemble mean (summarize-dim `--method mean`) as a third `-i`.
- Two variables of one file are two `-i` of the same path, each with its own `"meta": {"source": {"variable": …}}`.
- One panel per line, as in Plotly: put each line on its own axes and lay them out with a grid: `{"data": [{"uid": "1", "xaxis": "x2", "yaxis": "y2"}], "layout": {"grid": {"rows": 2, "columns": 1, "pattern": "coupled"}}}`. A right-hand axis: `{"data": [{"uid": "1", "yaxis": "y2"}], "layout": {"yaxis2": {"overlaying": "y", "side": "right"}}}`.
- Lines on one axis with different units, or with no dates in common, print a warning and still draw.
- `"align": "dayofyear"` on each line puts every year on one calendar, labelled `1 Oct`, `15 Nov`, … (29 Feb joins 28 Feb). Pass one file per year, each a single season; a season across New Year (DJF) puts Jan–Feb at the left.
- The y-axis label is the variable's `long_name` and units. A rainfall axis does not go below zero.

### Colors
- Precip totals use the mm class palette `default_precip`; anomalies use `default_precip_anom`. The range follows `aggregation_period`: under 2 days 0–50 mm, up to 10 days (a dekad) 0–200, under 40 days 0–400, longer 0–1000 (anomalies ±50 / ±200 / ±300 / ±500).
- Set a palette with `"meta": {"palette": NAME}`: `default_precip`, `default_precip_anom`, `ppt_daily` … `ppt_season`, `ppt_anom_*`, `spi`, a shipped theme's palette (below), or your own `{colors, bounds}`.
- Shipped themes add palettes, loaded by name with `--theme-file NAME` (`--help` THEMES lists each one's palettes):
  - `tropical_tidbits`: Tropical Tidbits model-chart colors. `tt_wind` (wind speed, m/s), `tt_precip_total` (mm), `tt_precip_rate` (mm/h), `tt_pwat` (mm), `tt_z500` (dam). With this theme, wind speed gets `tt_wind` and precip gets `tt_precip_total` without naming a palette.
- Temperatures use `RdYlBu_r`; fields spanning zero use `RdBu_r`; flag fields (verify hits) get one color per flag.
- `{"layout": {"coloraxis": {"colorbar": {"orientation": "h"}}}}` puts the colorbar under the maps.
- The standard look is one theme file, `scripts/weather_skills_plotting/themes/default.json` in this skill; `themes/README.md` beside it explains each key. A `--theme-file` is JSON/TOML with any of its five keys, layered on top of it — copy `default.json` to start one:
  - `template`: a Plotly template (fonts, colorway, backgrounds).
  - `palettes`: `{name: {colors, bounds}}` for `meta.palette`; a name like a built-in one replaces it.
  - `defaults`: what a field gets when the spec names no palette, per kind: `precip`, `precip_anomaly`, `precip_poa`, `spi`, `wind_speed`, `diverging`, `sea_level_pressure`, `temperature`, `sequential`. A value is a palette (name, color list or `{colors, bounds}`) or a Plotly colorscale name.
  - `styles`: Plotly settings per drawn element, e.g. `isobars`, `highs` / `lows` (H / L text), `arrows`; anything the spec sets on a trace wins.
  - `overlays`: line styles per base-map layer, e.g. `{"borders": {"line": {"color": "#333333"}}}`; lakes are filled, so their color is `{"lakes": {"fillcolor": "…"}}`.
- Without `--theme-file`, `$WEATHER_SKILLS_PLOT_THEME` or `~/.config/weather-skills/plot.json|toml` is used if present.

### Verification grid
`--obs OBS --forecast W1 --verify V1 --forecast W2 --verify V2 …` draws, for one verifying week, the observation and one column per forecast lead on one color scale, with each lead's verify map (hits, bias, or MAE from the verify skill) underneath and the metric named under the observation. One `--forecast` gives one row: observation, forecast, verify map.
- Prepare: `--obs` and each `--forecast` hold one time, the verifying week (select it first; a forecast with a `step` axis needs step-to-time before that). Obs and forecasts share one grid: coarsen the obs onto the forecast with `--reference-grid`. An ensemble forecast is drawn as its mean: run summarize-dim `--dim number --method mean` first. For rainfall, run aggregate-temporal, then convert-to-totals, before verify. All `--verify` files use one metric.
- Traces: `"obs"`, `"forecast1"` … `"forecastN"`, `"verify1"` … `"verifyN"`; column titles `panel-title-1` (obs), `panel-title-2` (week 1), …; the metric label `row-label-metric`. Obs and forecasts share `coloraxis`, verify maps `coloraxis2` (`{"layout": {"coloraxis2": {"cmin": -20, "cmax": 20}}}`). Name the variable on each input that holds several: `{"data": [{"uid": "forecast1", "meta": {"source": {"variable": "tp"}}}]}`.
- Colors: hits are disagree / below / hit, with the event threshold in the colorbar title; bias is centred on zero to the 98th percentile of |bias| (rainfall brown = too dry, green = too wet); MAE runs white to warm. Each lead's score summary goes to stderr.
- The default title is the week's dates (`5–11 Oct '26`), from any input that still has a `time` coordinate. A `layout.title` replaces it as given, so include the week in your own title.

### Mediogram
`--mediogram -i FORECAST -i MCLIMATE` draws a blue box of the forecast ensemble next to a red box of the model climate for each lead, with a black line through the forecast mean, for up to 15 leads both files have.
- Inputs: each is one point, from point-value (`--point LAT,LON`) on the forecast and on the m-climate grid; both need ensemble members (`number`) and leads (`step`). The m-climate is the same system's reforecasts of past years for the same leads (individual members; a mean/std climatology is not one). No fetcher here supplies reforecasts; a past init of the same system is a rough stand-in, so say so in the title. For rainfall totals, run aggregate-temporal then convert-to-totals on both first.
- Traces: `"forecast"`, `"mclimate"` (box) and `"forecast-mean"` (line). Pick leads with the same `meta.source.isel` `{"step": [0, 2, 4]}` on all three; set `meta.source.variable` on each trace whose file holds more than one variable. The default title names the quantity, the grid cell point-value used, and the init date; a `layout.title` replaces it as given.
- Boxes span the 25th–75th percentile with the median; whiskers reach 1.5 × the box height. With the forecast's init `time` the x-axis shows valid dates ("Week starting" for weekly totals).

### Animation
Add `--animate` to any map command (`-i GRID`, or a `--layer` stack of heatmap, contour, stations, wind arrows and outlines) and write `-o out.html`: a self-contained interactive map (plotly.js embedded, works offline) with one frame per time or step, play / pause and a slider, every frame on one color scale and titled with its time. Each frame is the map `plot` draws for that time, so the spec, theme and layers work as on a still map.
- The base map (coastlines, borders with disputed lines dashed, lakes, rivers; admin-1 lines on small boxes) is the still map's and stays on every frame. Add boundaries with `--layer outline:region.geojson` (resolve-region writes one); cut the data to the region with clip-region first.
- Every dim other than the map's own and the animated one must go (`isel` / `sel`, or summarize-dim); `{"data": [{"uid": "0", "meta": {"facet": "number"}}]}` animates another dim. Layers must cover the same times. It plays one map: stack inputs with `--layer`, not several `-i`. Time series and other non-map plots don't animate.
- Speed: 500 ms per frame by default. Your own Plotly `layout.updatemenus` / `sliders` replace the default controls, frame duration included: `{"layout": {"updatemenus": [{"type": "buttons", "buttons": [{"label": "Play", "method": "animate", "args": [null, {"frame": {"duration": 300}}]}]}]}}`.
- GIF: `-o out.gif` writes the frames as a looping GIF, with no play / pause or slider, at the Play button's speed: 500 ms per frame, or the `frame.duration` of an `updatemenus` Play button in the spec (as above). Each frame is drawn like a PNG (`--scale` sets pixel density); GIFs hold 256 colors per frame, so smooth color scales band slightly. Repeat `-o` for both (`-o rain.html -o rain.gif`).
- Size grows with frames × cells; stderr gives the frame count and data size and warns above 50 MB. Pick fewer frames (`{"step": {"start": 0, "stop": 12}}`) or clip-region the input to a smaller area.

### Provenance
The file's history (`weather_skills_history`) is embedded in the PNG / GIF metadata or HTML `<meta>` tag; read it with the `provenance` skill. A PNG/JPG/GIF with a complete history carries a small red seal in the bottom-right corner.

### More examples
```bash
# Stations over IMERG, inside a county outline
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o nairobi.png \
  --layer heatmap:imerg.zarr --layer scatter:tahmo.zarr=STATIONS --layer outline:nairobi.geojson \
  --spec '{"data": [{"uid": "STATIONS", "marker": {"size": 14}}]}'
# MSLP chart: anomaly shading, labeled black isobars every 4 hPa, and H / L with the
# central pressure (highs / lows from local-extrema; --radius 7 marks a Tropical Tidbits-style
# set of centres, 15 or more misses most of them). For a forecast, pick the same step
# on every layer with "meta": {"source": {"isel": {"step": N}}}. Pressure is drawn in the
# file's units: run unit-convert on msl (ERA5 stores Pa) for labels in hPa.
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o mslp.png \
  --layer heatmap:msl_anom.zarr --layer contour:msl.zarr=MSLP \
  --layer scatter:highs.zarr --layer scatter:lows.zarr
# Tropical Tidbits look: --theme-file tropical_tidbits adds TT's palettes (tt_precip_rate in
# mm/h, tt_precip_total, tt_pwat, tt_wind, tt_z500 in dam). --help RECIPES has MSLP & precip,
# MSLP & 10 m wind, total precip, MSLP & PWAT, and 500 mb height & MSLP. Palettes and levels
# are in those units, so unit-convert the inputs to them first (msl to hPa).
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o tt_pwat.png --theme-file tropical_tidbits \
  --layer heatmap:pwat.zarr=PWAT --layer contour:msl.zarr=MSLP --spec '{"data": [
  {"uid": "PWAT", "meta": {"palette": "tt_pwat"}},
  {"uid": "MSLP", "contours": {"coloring": "none", "showlabels": true, "start": 900, "end": 1080, "size": 2}}]}'
# Ensemble members as lines, with a 10–90% band from summarize-dim --method quantile -q 0.1 -q 0.9
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i ens_q.zarr=LOW -i ens_q.zarr=HIGH -i ens_area_mean.zarr=ENS -o ens.png \
  --spec '{"data": [
  {"uid": "LOW", "mode": "lines", "line": {"width": 0}, "showlegend": false, "meta": {"source": {"sel": {"quantile": 0.1}}}},
  {"uid": "HIGH", "name": "10–90%", "mode": "lines", "fill": "tonexty", "line": {"width": 0}, "meta": {"source": {"sel": {"quantile": 0.9}}}},
  {"uid": "ENS", "name": "Members", "meta": {"along": "number"}}]}'
# Daily CHIRPS as bars, climatology as a dashed line
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i obs_area.zarr=OBS -i clim_area.zarr=CLIM -o obs_vs_clim.png \
  --spec '{"data": [{"uid": "OBS", "name": "CHIRPS", "type": "bar"}, {"uid": "CLIM", "name": "Climatology", "line": {"dash": "dash"}}]}'
# Three OND seasons on one calendar
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_ond_2023.zarr -i chirps_ond_2024.zarr -i chirps_ond_2025.zarr -o ond.png \
  --spec '{"data": [{"uid": "0", "meta": {"align": "dayofyear"}}, {"uid": "1", "meta": {"align": "dayofyear"}}, {"uid": "2", "meta": {"align": "dayofyear"}}]}'
```
