---
name: plot
description: "Draw weather-skills Zarrs as maps (heatmap, contour, stations, wind arrows), time series, xy scatter plots, wind roses, forecast verification grids (obs, lead-week forecasts and their hits / bias / MAE maps), ECMWF-style mediograms (forecast vs model-climate ensembles at a point), or animated maps through time, saved as PNG, JPG, PDF, SVG, interactive HTML, or GIF. Titles, colors, panels, and layout are set with a standard Plotly figure JSON."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG, JPG, PDF and SVG export needs Chrome (installed, or `plotly_get_chrome -y`). Self-contained; the plotting library ships in scripts/.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "1.0.10"
  catalog-group: figure
---

# plot

Draws one or more Zarrs as a figure. Name the files on the command line; change titles, colors and layout with `--spec`, a standard Plotly figure JSON.

## Usage

```bash
# One map (one panel per time or step)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i rain.zarr -o rain.png
# Maps side by side, each on its own grid (each file one time or step)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_week.zarr=OBS -i ecmwf_w1.zarr=FC -o compare.png
# Area means as lines on one time axis
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_area.zarr -i imerg_area.zarr -o rain.png
# Layers on one map, bottom first
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer heatmap:rain.zarr --layer scatter:stations.zarr --layer outline:kenya.geojson -o map.png
# One variable against another
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i iod_rain.zarr -o iod_vs_rain.png --spec '{"data": [{"uid": "0", "meta": {"x": "dmi", "y": "precip"}}]}'
# Verification grid: obs, then each lead's forecast and verify map
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --obs chirps_week.zarr --forecast ecmwf_w1.zarr --verify verify_w1.zarr --forecast ecmwf_w2.zarr --verify verify_w2.zarr -o verify.png
# Mediogram: forecast ensemble vs model climate at one point
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --mediogram -i forecast.zarr -i mclimate.zarr -o mediogram.png --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}'
# A map animated through time: interactive HTML, or a looping .gif
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --animate --layer heatmap:rain_daily.zarr --layer contour:msl_daily.zarr --layer outline:kenya.geojson -o rain.html
```

The data picks the plot: a lat/lon grid is a colored map, stations are colored markers (one station over time is a line), and 1-D series are lines on one time axis. `--obs`/`--forecast`/`--verify`, `--mediogram` and `--animate` are the special figures; use one at a time.

### Arguments
- `-i`, `--input` — a Zarr to draw, or a GeoJSON (`.geojson`, `.json`) to outline on every map; `PATH` or `PATH=UID`. Repeat for side-by-side maps or more lines.
- `--layer` — `KIND:PATH[=UID]`, stacked on one map, bottom first. Kinds: `heatmap`, `contour` (labeled black lines; `"contours": {"coloring": "fill"}` fills it), `scatter` (stations; local-extrema highs / lows print as H / L), `quiver` (wind u/v: a speed field `UID` and arrows `UID-arrows`), `outline` and `mask` (GeoJSON). `outline`, `mask` and `scatter` layers also go with `-i` inputs and are drawn on every map.
- `--obs`, `--forecast`, `--verify` — verification grid (below).
- `--mediogram` — forecast vs model climate at one point; `-i` twice (below).
- `--animate` — play a map's times or steps as frames; `-o` must be `.html` or `.gif` (below).
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — a house style file, or a shipped theme by name (`tropical_tidbits`). See Colors.
- `--dump-spec` — print (`-`) or save (a path) the spec without drawing.
- `-o`, `--output` — `.png`, `.jpg`, `.pdf`, `.svg` (vector, text stays text), `.html`, or `.gif` (`--animate` only). Repeat for several formats.

## Customizing with `--spec`

`--spec` is [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`. Write only what you change; it is merged onto the figure the command builds. Run `--dump-spec -` to see that figure, and `--help` for every key.

**Each input is one trace, found by its `uid`.** The uid is the name after `=` (`-i ecmwf.zarr=FC` → `"uid": "FC"`), else the input's position counting every `-i`, then every `--layer`, from `"0"`. A name is letters, digits and `_` only. Legend text goes in the trace's `"name"` (any characters), and a panel title in a `panel-title-N` annotation. With named inputs, a position uid such as `"0"` stops and lists the real uids.

**What each trace draws is in its `meta`.** Name the variable or coordinate that fills each Plotly attribute:

| Trace | `meta` |
| --- | --- |
| map (heatmap, contour) | `"z": "precip"` |
| stations | `"x": "longitude", "y": "latitude", "marker": {"color": "precip"}` |
| line | `"x": "time", "y": "precip"` (a forecast: `"x": "step"`) |
| one variable against another | `"x": "dmi", "y": "precip"`; a name coordinate (`county`) makes a category axis |
| cross-section | `"x": "longitude", "y": "vertical", "z": "r", "source": {"sel": {"latitude": -1}}` on a heatmap or contour |

Every other key is Plotly's own, in its usual place: `zmin`, `colorscale` and `showscale` on a heatmap; `marker.size`, `marker.line` and `marker.showscale` on stations; `line` on a line. The trace's own `marker.color` is a color such as `"red"`, never a variable.

**Restyle or replace.** A trace with an input's uid restyles that input, and only the keys you write change. A trace with a new uid that reads data (it sets `meta.x` / `y` / `z` / `marker.color`, or a non-GeoJSON `meta.source`) is drawn *instead of* the `-i` inputs; any `-i` input it should keep needs its own entry by uid. Outlines and `--layer` traces are always kept. A new trace reads the input named in `meta.source.input` (needed when there are several). A new uid that reads no data (city markers, a box) just adds a plain Plotly trace.

```bash
# Named lines: legend names and colors
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_area.zarr=CHIRPS -i imerg_area.zarr=IMERG -o rain.png --spec '{"data": [
  {"uid": "CHIRPS", "line": {"color": "black"}}, {"uid": "IMERG", "name": "IMERG Late", "line": {"dash": "dash"}}]}'
# Named layers
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer heatmap:rain.zarr=RAIN --layer contour:msl.zarr=MSLP -o map.png --spec '{"data": [
  {"uid": "RAIN", "zmin": 0, "zmax": 50}, {"uid": "MSLP", "contours": {"size": 2}}]}'
# Bars per county, one panel each
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i west.zarr=West -i east.zarr=East -o counties.png --spec '{"data": [
  {"uid": "West", "type": "bar", "meta": {"x": "county", "y": "precip"}},
  {"uid": "East", "type": "bar", "meta": {"x": "county", "y": "precip"}, "xaxis": "x2", "yaxis": "y2"}],
  "layout": {"xaxis": {"domain": [0, 0.46]}, "xaxis2": {"domain": [0.54, 1]}, "yaxis2": {"anchor": "x2"}}}'
```

Common edits, for `-i ecmwf.zarr=FC`:

| To | `--spec` |
| --- | --- |
| Set the title | `{"layout": {"title": {"text": "Week 1", "subtitle": {"text": "16–22 Oct"}}}}` |
| Title panel 2 | `{"layout": {"annotations": [{"name": "panel-title-2", "text": "ECMWF"}]}}` |
| Pick one step | `{"data": [{"uid": "FC", "meta": {"source": {"isel": {"step": 0}}}}]}` |
| Pick the variable | `{"data": [{"uid": "FC", "meta": {"z": "tp"}}]}` |
| Set the color range | `{"data": [{"uid": "FC", "zmin": 0, "zmax": 100}]}` |
| Set the map window | `{"layout": {"meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}` (`[N, W, S, E]`) |
| Draw contours | `{"data": [{"uid": "FC", "type": "contour"}]}` |

`isel` counts from 0 (`-1` is the last); `sel` picks by label, the nearest one for numbers and dates.

### Before you plot
- **One variable per trace.** A file with several data variables needs the trace to name one (`meta.z`, `meta.y` or `meta.marker.color`); inspect-zarr lists them. Grids and lines stop rather than guess; stations draw as plain dots with a note.
- **One value per cell or point.** Pick every extra dim (`number`, `vertical`) with `isel` / `sel`, panel it with `"meta": {"facet": "number"}`, draw it as lines with `along`, or average it first with summarize-dim.
- **Units are the file's.** K stays K and Pa stays Pa (run unit-convert for °C or hPa), so `zmin`, contour levels and palette edges are in the file's units. A precip rate draws as a rate; for totals in mm run aggregate-temporal, then convert-to-totals.

### Output
The figure at each `-o`. Images also print a `plot hash` and `data: not null` (or `NULL` when every value drawn is NaN). The file's history is embedded in its metadata; read it with the provenance skill.

## Maps and panels
- A file with several times or steps draws one panel per value, titled with its date; a still image takes at most 100. `layout.grid.rows` / `columns` set the grid and `xgap` / `ygap` the spacing.
- Side-by-side inputs are maps `xy`, `x2y2`, `x3y3`, … in input order. They fill the grid left to right, then row by row. To place them yourself, list each cell's map in `layout.grid.subplots`, row by row, `""` for an empty cell: `{"layout": {"grid": {"subplots": [["xy", "x3y3", "x5y5"], ["x2y2", "x4y4", ""]]}}}` puts inputs 1–2 down the first column.
- Panel N is the one on axes `xN` / `yN`, and its title is the annotation `panel-title-N` (give only `name` and `text`; it keeps its place). Unnamed side-by-side files are titled with their file name (`wk1/KMSA downscaled.zarr` → `KMSA downscaled`) and their dates, so naming files for their panels saves writing annotations.
- A file with several steps is one map per step only on its own. Beside other maps, pass it once per step and pick the step on each: `-i daily.zarr -i daily.zarr -i total.zarr --spec '{"data": [{"uid": "0", "meta": {"source": {"isel": {"step": 0}}}}, {"uid": "1", "meta": {"source": {"isel": {"step": 1}}}}]}'`.
- Maps of the same variable kind and units share one colorbar. `"coloraxis": "coloraxis2"` on a trace splits it off; the same `coloraxis` on two traces joins them. Maps of the same window keep tick labels on the outer panels only.
- Outlines and station layers are drawn on every map; one restyle by uid styles them everywhere. Stations have no legend entry until `"showlegend": true`. On a single map an outline also frames the map unless `geo.bbox` is set.
- Map axes are plain x/y in degrees (x = longitude). Add points with a plain `scatter` trace and Plotly's own `x` / `y` arrays, and boxes with `layout.shapes` (`xref: "x"`, `yref: "y"`).
- Cross-sections (a field over two dims that are not a lat/lon grid) are charts; pick every other dim first. A pressure axis puts 1000 hPa at the bottom.
- The canvas is sized from the maps. Leave `layout.width` / `height` unset unless you need a fixed size.

## Lines
- Each 1-D input is one line on one shared axis (up to 26), named after its file or station id; `"name"` renames it. One line shows a legend entry only once the spec gives it a `"name"`. A forecast line (`"x": "step"`) runs along its valid dates.
- Each line uses only its own `meta`: set `y`, `along`, `band` or `align` on every line that needs it.
- `"along": "number"` draws one line per member under one legend entry (`"along_color": "cycle"` gives each its own). `"along": "station_id"` draws one line per station, each its own color.
- `"band": [10, 90]` with `along` shades that percentile range (`[0, 100]` is min–max) and draws the mean bold; `"members": false` hides the members. Its parts are styled by uid: `UID` the mean, `UID-members` the members, `UID-band` the shading: `{"data": [{"uid": "FC", "line": {"color": "red", "width": 4}, "meta": {"along": "number", "band": [0, 100]}}, {"uid": "FC-members", "line": {"color": "grey"}, "opacity": 0.3}, {"uid": "FC-band", "name": "Range"}]}`.
- Members with a bold mean and no shading: average them first (summarize-dim `--dim number --method mean`), then draw both files: `-i ens.zarr=ENS -i mean.zarr=MEAN --spec '{"data": [{"uid": "ENS", "line": {"color": "grey", "width": 0.7}, "meta": {"x": "step", "y": "tp", "along": "number"}}, {"uid": "MEAN", "line": {"color": "red", "width": 4}, "meta": {"x": "step", "y": "tp"}}]}'`.
- `"align": "dayofyear"` puts every year on one calendar: one file per year, each one season, `align` on each line. It needs a `time` axis: run step-to-time on a forecast first, then align it like the others. Aligned and unaligned lines on one axis is an error: they share no dates.
- Two variables of one file: one trace each, both reading the input: `{"data": [{"uid": "P", "meta": {"source": {"input": "0"}, "x": "time", "y": "precip"}}, {"uid": "T", "yaxis": "y2", "meta": {"source": {"input": "0"}, "x": "time", "y": "t2m"}}], "layout": {"yaxis2": {"overlaying": "y", "side": "right"}}}`.
- `"type": "bar"` draws bars (with `along`, one series per value). Lines with different units, or no dates in common, warn and still draw.

## Colors
- Precip gets the mm class palettes, with a range from `aggregation_period`: under 2 days 0–50 mm, up to 10 days 0–200, under 40 days 0–400, longer 0–1000 (anomalies ±50 / ±200 / ±300 / ±500). Temperatures get `RdYlBu_r`, fields spanning zero `RdBu_r`, flag fields one color per flag.
- Set one with `"meta": {"palette": NAME}`: `ppt_daily`, `ppt_week`, `ppt_month`, `ppt_season`, `ppt_anom_daily` … `ppt_anom_season`, `spi`, a theme's palette, or your own `{"colors": [...], "bounds": [...]}` (one color per pair of edges).
- `{"layout": {"coloraxis": {"colorbar": {"orientation": "h"}}}}` puts the colorbar under the maps.
- A theme file sets a house style for every plot: Plotly `template`, `palettes`, per-field `defaults`, element `styles` and base-map `overlays`. Copy `scripts/weather_skills_plotting/themes/default.json` to start one; `themes/README.md` explains each key. `--theme-file tropical_tidbits` adds Tropical Tidbits palettes (`tt_wind`, `tt_precip_total`, `tt_precip_rate`, `tt_pwat`, `tt_z500`). Without `--theme-file`, `$WEATHER_SKILLS_PLOT_THEME` or `~/.config/weather-skills/plot.json|toml` is used if present.

## Verification grid
`--obs OBS --forecast W1 --verify V1 --forecast W2 --verify V2 …` draws, for one verifying week, the observation and one column per forecast lead on one color scale, with each lead's verify map (hits, bias or MAE from the verify skill) below.
- Inputs: each holds one time, the verifying week (a forecast with `step` needs step-to-time, then select), on one shared grid (coarsen the obs onto the forecast). Draw an ensemble as its mean (summarize-dim first). All `--verify` files use one metric.
- Traces: `"obs"`, `"forecast1"` …, `"verify1"` …; column titles `panel-title-1` (obs), `panel-title-2` (week 1), …; the metric label `row-label-metric`. Obs and forecasts share `coloraxis`, verify maps `coloraxis2`.
- The default title is the week's dates; a `layout.title` replaces it, so include the week in yours.

## Mediogram
`--mediogram -i FORECAST -i MCLIMATE` draws, at `layout.meta.geo.point` (required), a box of the forecast ensemble beside a box of the model climate for each lead (up to 15), with a line through the forecast mean.
- Inputs: both need `number`, `step` and latitude/longitude. The model climate is the same system's reforecasts of past years (members, not a mean/std climatology); a past init of the same system is a rough stand-in, so say so in the title.
- Traces: `"forecast"`, `"mclimate"` and `"forecast-mean"`; pick leads with the same `meta.source.isel` on all three.

## Animation
`--animate` plays any map through its times or steps: one `-i` Zarr, or a `--layer` stack, plus outlines. `-o out.html` is a self-contained interactive map with play / pause and a slider; `-o out.gif` loops. Every frame shares one color scale, and the spec, theme and layers work as on a still map.
- Every dim other than the map's and the animated one must be picked first; `{"data": [{"uid": "0", "meta": {"facet": "number"}}]}` animates another dim. Layers must cover the same times.
- Speed: `{"layout": {"meta": {"animation": {"duration": 300}}}}` (ms per frame, default 500).
- Size grows with frames × cells and warns above 50 MB; pick fewer frames (`"isel": {"step": {"start": 0, "stop": 12}}`) or a smaller `bbox`.

## More examples
```bash
# Stations over IMERG inside an outline
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o nairobi.png \
  --layer heatmap:imerg.zarr --layer scatter:tahmo.zarr=STATIONS --layer outline:nairobi.geojson \
  --spec '{"data": [{"uid": "STATIONS", "marker": {"size": 14}}]}'
# MSLP chart: anomaly shading, isobars every 4 hPa, H / L from local-extrema (msl in hPa)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o mslp.png \
  --layer heatmap:msl_anom.zarr --layer contour:msl.zarr=MSLP \
  --layer scatter:highs.zarr --layer scatter:lows.zarr
# Tropical Tidbits look: MSLP and precipitable water (--help RECIPES has more)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o tt_pwat.png --theme-file tropical_tidbits \
  --layer heatmap:pwat.zarr=PWAT --layer contour:msl.zarr=MSLP --spec '{"data": [
  {"uid": "PWAT", "meta": {"palette": "tt_pwat"}},
  {"uid": "MSLP", "contours": {"coloring": "none", "showlabels": true, "start": 900, "end": 1080, "size": 2}}]}'
# Ensemble members with a 10–90% band
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i ens_area_mean.zarr -o ens.png \
  --spec '{"data": [{"uid": "0", "meta": {"along": "number", "band": [10, 90]}}]}'
# Daily rain as bars, climatology as a dashed line
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i obs_area.zarr=OBS -i clim_area.zarr=CLIM -o obs_vs_clim.png \
  --spec '{"data": [{"uid": "OBS", "name": "CHIRPS", "type": "bar"}, {"uid": "CLIM", "name": "Climatology", "line": {"dash": "dash"}}]}'
# Three OND seasons on one calendar
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_ond_2023.zarr -i chirps_ond_2024.zarr -i chirps_ond_2025.zarr -o ond.png \
  --spec '{"data": [{"uid": "0", "meta": {"align": "dayofyear"}}, {"uid": "1", "meta": {"align": "dayofyear"}}, {"uid": "2", "meta": {"align": "dayofyear"}}]}'
```
