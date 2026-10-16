---
name: plot
description: Render a map (heatmap, filled contour, stations, wind quiver), time series, xy scatter, or wind rose from weather-skills standard dataset Zarrs as PNG, JPG, or interactive HTML. The --spec is a standard Plotly figure JSON; dataset bindings go in each trace's meta. Side-by-side maps on different grids (CHIRPS 0.05° next to ECMWF 1.5°) are one -i per file, each on its own axes and grid; do not coarsen them onto one grid. --layer KIND:PATH stacks files on one map. --help lists the meta keys and recipes. Named places: get a bbox or polygon from resolve-region first. For precipitation totals, run aggregate-temporal (then convert-to-totals, or let plot convert: a rate with an aggregation_period is drawn as period totals, and stderr says so). The plotter selects but never averages: run summarize-dim first for an ensemble or area mean. For a lead-week verification grid, use plot-verify.
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot

Name the files on the command line. Describe the figure in `--spec`, which is a **standard Plotly figure**: `{"data": [traces], "layout": {…}}`. Every key is Plotly's own ([reference](https://plotly.com/python/reference/)), so titles, fonts, axes, colorbars, legends, annotations and shapes work exactly as they do in Plotly. The only extra piece is `meta`, Plotly's free-form field, which says which dataset a trace draws.

The output format follows the `-o` suffix: `.png`, `.jpg`, or `.html` (interactive, with hover values; works offline).

## How a spec is built

The command builds a figure from the files you name, then merges `--spec` onto it:

- `data[]` merges by `uid`. A file's uid is its NAME from `-i PATH=NAME` (or `--layer KIND:PATH=NAME`), else its position: `0`, `1`, `2`, …; `x` / `y` for `--x` / `--y`. A `data[]` entry with no `uid` merges by position, and a new `uid` adds a trace.
- `layout.annotations` and `layout.shapes` merge by `name`. Everything else in `layout` is deep-merged.
- Your values win.
- Dotted names in the tables below are nested keys: `geo.bbox` is `{"layout": {"meta": {"geo": {"bbox": […]}}}}`.

Run the same command with `--dump-spec -` in place of `-o` to print the spec it builds (traces, bindings, inputs), edit that JSON, and pass it back with `--spec`. Defaults worked out from the data (palette, colorbar label, panel titles, size) are filled in at draw time and are not in the dump; set any of them in the spec to override. A dumped spec replays on its own: the file paths are kept in `layout.meta.inputs`.

What the command builds from each file:

| File | Trace |
| --- | --- |
| lat/lon grid | `heatmap`, one panel per `time` or `step` value, titled with its date; a single map keeps the date of the time or step you picked. `meta.facet` panels another dim (`"vertical"` gives `850 hPa` panels; all-NaN panels are noted on stderr). Ensemble `number` is averaged and stderr says so; `meta.facet: "number"` maps each member. |
| `station_id` / `point_id` data | `scatter` markers at the stations, colored by value (`meta.bind: "points"`) |
| 1-D along time | `scatter` line (`meta.bind: "series"`) |
| `--x` + `--y` | `scatter` of one series against the other (`meta.bind: "pair"`) |

## Panels and layers

| Goal | How |
| --- | --- |
| Two datasets side by side, each on its own grid | Repeat `-i`. Trace `a` sits on axes `x`/`y`, trace `b` on `x2`/`y2`, and so on. Each panel keeps its own lat/lon spacing. Panels of the same quantity share one colorbar, and panels of the same region share one map window. Each input must already be one map: select or aggregate the time first. |
| Datasets drawn on top of each other | `--layer heatmap:a.zarr --layer scatter:stations.zarr --layer outline:kenya.geojson`. Every trace on the same axes stacks on one map. Layers of the same quantity share a colorbar. |
| A boundary on `-i` maps | Add `--layer outline:PATH` (or `mask:PATH`) to `-i`: it is drawn on every panel. An outline frames the map (unless `geo.bbox` is set) and turns off Natural Earth's admin-1 lines. |
| Several times or steps of one dataset | One `-i`. The trace panels its `time` / `step` dim. `layout.grid.rows` / `columns` shape the grid (default: the grid closest to a landscape page with no empty row, e.g. 10 panels → 5×2). |
| Some of the times or steps | `meta.source.isel` takes 0-based positions; `-1` is the last. One integer picks one map (`{"time": -1}` is the latest), a list keeps one panel each (`{"step": [0, 1]}` is the first two weeks). `sel` picks by label (`{"time": "2026-10-01"}`). |
| Ensemble members as panels | `meta.facet: "number"` with `meta.source.isel: {"number": [0, 1, 2, 3]}`; panels are titled `Member 0`, `Member 1`, …. Without the `isel`, every member gets a panel. |
| A station file with a `time` dim over a map | Select the day on the station trace: `{"uid": "1", "meta": {"source": {"sel": {"time": "2026-10-01"}}}}`. |
| Separate colorbars for side-by-side maps | Give one trace its own axis: `"coloraxis": "coloraxis2"`. Traces naming the same axis always share it; a station trace names it as `marker.coloraxis`. |
| Week N of a daily forecast | aggregate-temporal to weekly first (then convert-to-totals for a total), and pick the week with `meta.source.isel: {"step": 1}` (an arrows trace takes the same selection from its speed trace). A field described as "in the last 24 hours" covers the day before each step, so its step 0 is empty: day 1 is step 1. |

A trace's `name` titles its panel. A trace with several panels gets annotations named `panel-title-1`, `panel-title-2`, … (numbered from 1); rename one with `{"layout": {"annotations": [{"name": "panel-title-2", "text": "ECMWF"}]}}`. The canvas is sized from the maps: each panel is as large as its lon/lat shape allows (up to 760×560 px alone, 340×340 px in a grid), with fixed room for titles, ticks and colorbars, so there is no empty band around a map. `layout.width` / `height` fix the canvas and the maps shrink to fit; `layout.grid.xgap` / `ygap` set the gap between panels as a fraction of a panel. One colorbar stands on the right. Several stand beside the rows, or under the columns, they colour (totals row and anomalies row each get their own); otherwise they lie side by side along the bottom.

Maps are plain Plotly x/y axes in degrees (x = longitude, y = latitude), not `geo` / `map` subplots. Add markers, labels and lines as ordinary `"type": "scatter"` traces with `x` / `y` (a new `uid` adds one; it repeats on every map panel), and boxes as `layout.shapes` with `xref: "x"`, `yref: "y"`. `scattergeo` / `scattermap` are rejected.

Do not `coarsen` or `downscale` just to draw a figure. Only `difference` and `verify` need a shared grid.

## The `meta` keys

`data[].meta`:

| Key | Meaning |
| --- | --- |
| `bind` | How the arrays are filled: `field` (grid → heatmap/contour), `speed` (wind speed from u/v), `arrows` (u/v arrows), `points` (stations), `geojson` (boundary lines), `series` (1-D line or bar), `pair` (xy), `samples` (box per step), `windrose` (barpolar). The default comes from the trace type. |
| `source` | `{input, variable, isel, sel, u, v, geojson, mask_geojson, point}`. `isel` is 0-based positions (`-1` is the last), `sel` is coordinate labels. `variable` picks one field of a multi-variable file (unset: rainfall if present, and stderr names it). A dim of size 1 is dropped; any other leftover dim is an error naming the fix. The plotter never averages: for an ensemble mean or area mean, run `summarize-dim` first. `u` and `v` are found from CF `standard_name` (`eastward_wind` / `northward_wind`) or names such as `u10`/`v10`; they must be in the same input: merge separate u and v files into one Zarr first. |
| `facet` | The dim to panel (default `step` or `time`); `false` turns paneling off. |
| `along`, `along_color`, `band`, `members` | Series: one line per value of a dim (`"number"` gives ensemble spaghetti). `along_color` is `same` (default) or `cycle`. `band: [10, 90]` shades a percentile band and draws the mean as a bold line (legend: `… ensemble mean`); the members stay as faint lines unless `members: false`. |
| `align` | Series: `"dayofyear"` overlays years on one seasonal axis. |
| `pair_on`, `x`, `y` | Pair: `x` and `y` are full sources (`{input, variable, isel, sel}`), joined on `pair_on` (`time`, `year`, `index`). Leftover dims are an error, as for series. |
| `palette` | Class palette: a name (`default_precip`, `default_precip_anom`, `ppt_daily`, `ppt_week`, `ppt_month`, `ppt_season`, `ppt_anom_*`, `spi`, `ppt_poa`, …), a color list, or `{colors, bounds, under, over}`. `bounds` are class edges with one color per class, so 7 bounds take 6 colors; `under` / `over` color values outside the edges. It replaces the automatic precipitation palette. |
| `arrows` | `{step, scale}`: `step: 3` draws an arrow on every 3rd cell; `scale` is arrow length in map degrees per unit of speed (default: the strongest winds span about one arrow spacing). |

`layout.meta`:

| Key | Meaning |
| --- | --- |
| `geo.bbox` | `[N, W, S, E]` map window, or the `"N/W/S/E"` string resolve-region prints; subsets every input. There is no `geo.region`: run `resolve-region` and pass its bbox. |
| `geo.mask_geojson` | Blank map cells outside a polygon (does not draw it; add a `geojson` trace for the edge). |
| `geo.point` | `{lat, lon}` for `samples` and wind-rose traces (nearest grid cell). |
| `overlays` | Base map: `true` (default), `false`, or per layer, e.g. `{"rivers": false, "admin1": true, "borders": {"line": {"width": 2}}}`. Layers: `coastline`, `borders`, `lakes`, `rivers`, `admin1` (Natural Earth; scale follows the map span). |
| `export.scale` | PNG/JPG pixel multiplier: `{"export": {"scale": 2}}` doubles the pixels (default 1). |

To draw official national or local boundaries instead of the built-in Natural Earth lines, check whether an installed skill provides more specific region GeoJSON for the use case and add each file as `--layer outline:PATH`. An outline already turns admin-1 off; set `"overlays": {"borders": false, "coastline": false}` too if the file holds the national border.

## Colors

Precipitation totals get the nested absolute-mm class palette automatically: the same color always means the same millimetres, and the window follows `aggregation_period`. Anomalies get the diverging classes. Fields with CF `flag_values` (e.g. `verify` hits) get one class per flag, labelled with `flag_meanings` (disagree / below / hit). Temperatures get `RdYlBu_r` (blue cold, red warm). A spread (`cell_methods` with `standard_deviation`, as summarize-dim writes) gets a sequential scale, not the rainfall classes. Other fields get a sequential scale, or `RdBu_r` centred on zero when the data, or your limits, span zero.

- **A Plotly colorscale and limits:** set `colorscale`, `zmin` / `zmax` (or `marker.cmin` / `cmax` for stations) and `colorbar` on the trace. They apply to the trace's color axis. Setting limits on a class palette turns it into a continuous scale.
- **A class palette:** `meta.palette`.

`default_precip` (totals) and `default_precip_anom` (anomalies) are the palettes precipitation gets automatically, with the window picked from `aggregation_period`: under 2 days 0–50 mm (±50), under 10 days 0–200 (±200), under 40 days 0–400 (±300), longer 0–1000 (±500); weekly with no period. Name one in `meta.palette` to skip detection when an anomaly lost its precip name (e.g. after `difference`), an anomaly is all positive, a bias-corrected total has negative values, or totals and anomalies share a figure. To pin a window, name it: `ppt_daily` … `ppt_season`, `ppt_anom_daily` … `ppt_anom_season`. A `--theme-file` palette of the same name replaces the built-in one. For other named palettes (e.g. an agency's rainfall legend), check whether an installed skill provides a theme file and pass it with `--theme-file`.
- **A whole color axis:** `layout.coloraxis` (or `coloraxis2`, …), e.g. `{"layout": {"coloraxis": {"colorbar": {"title": {"text": "Rain [mm]"}}}}}`.
- **A colorbar under the maps:** `{"layout": {"coloraxis": {"colorbar": {"orientation": "h"}}}}`. The plotter makes room and places it; leave `x` / `y` unset.

The colorbar label defaults to a short form of the variable's `long_name` and units (`Precipitation [mm]`, `Temperature (2 m) [°C]`), with `anomaly` or `std. dev.` added when the field is one. Forecast panels are titled with their valid dates (`3–9 Aug '26`). Dates belong in titles.

Keep titles and colorbar labels short: a title names the subject in a few words (`CHIRPS weekly totals`), a colorbar label is the quantity and units (`Rain [mm]`). Methods, sources and caveats go in your reply, not the figure. Long text wraps and crowds side-by-side panels and colorbars.

## Command line

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i <in.zarr> [-i <in2.zarr> …] -o <out.png|.html> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer KIND:PATH [--layer …] -o <out.png> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x <x.zarr> --y <y.zarr> -o <out.png> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i <in.zarr> --dump-spec -
```

- `-i` — repeatable Zarr, as `PATH` or `PATH=NAME`; exclusive with `--x`/`--y` and with data layers (`--layer outline:` / `mask:` go with `-i`).
- `--layer KIND:PATH[=NAME]` — `heatmap`, `contour`, `scatter` (stations), `quiver` (u/v: speed plus arrows), `outline` (GeoJSON edge), `mask` (GeoJSON mask).
- `--spec` — inline JSON or a file path.
- `--dump-spec [PATH]` — print or write the merged spec and skip drawing.
- `--theme-file` — JSON/TOML `{"template": <Plotly template>, "palettes": {name: {colors, bounds}}}`. `layout.template` also accepts `weather_skills` (the default: Plotly's `seaborn` look with seaborn's colour cycle), `colorblind` (the same with seaborn's colourblind-safe cycle), or any Plotly template name, e.g. `plotly_white` or `simple_white`.

`--help` prints the full `meta` reference and copy-paste recipes.

## Examples

```bash
# Weekly CHIRPS totals, one panel per week, 2 rows
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/chirps_weekly_mm.zarr -o /tmp/chirps.png \
    --spec '{"layout": {"title": {"text": "CHIRPS weekly totals"}, "grid": {"rows": 2}}}'

# CHIRPS 0.05° beside ECMWF 1.5°, each on its own grid: named panels, Kenya window,
# one colorbar label, 2x pixels
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/chirps_week.zarr -i /tmp/ecmwf_week.zarr \
    -o /tmp/obs_vs_fc.png --spec '{
  "data": [{"uid": "0", "name": "CHIRPS 0.05°"}, {"uid": "1", "name": "ECMWF 1.5°"}],
  "layout": {"title": {"text": "Week 1"}, "coloraxis": {"colorbar": {"title": {"text": "Rain [mm]"}}},
             "meta": {"geo": {"bbox": [5, 33.5, -5, 42]}, "export": {"scale": 2}}}}'

# First two weeks of a weekly forecast in an agency legend (6 classes on 7 edges, orange above 100 mm),
# county lines on top, in the bbox resolve-region printed
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/ecmwf_weekly.zarr --layer outline:/tmp/kenya_counties.geojson \
    -o /tmp/kenya_weeks.png --spec '{
  "data": [{"uid": "0", "meta": {"source": {"isel": {"step": [0, 1]}},
    "palette": {"colors": ["#ffffff", "#d1ffbe", "#55ff00", "#73dfff", "#00a9e6", "#ffaa00"],
                "bounds": [0, 1, 10, 20, 50, 70, 100], "over": "#ff5500"}}}],
  "layout": {"title": {"text": "ECMWF weekly rainfall"}, "meta": {"geo": {"bbox": "5.41/33.91/-4.71/41.91"}}}}'

# Latest day of a daily SST anomaly, fixed ±2 range, no rivers
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/sst_anom.zarr -o /tmp/sst.png --spec '{
  "data": [{"uid": "0", "zmin": -2, "zmax": 2, "meta": {"source": {"isel": {"time": -1}}}}],
  "layout": {"meta": {"geo": {"bbox": [20, 35, -20, 75]}, "overlays": {"rivers": false}}}}'

# Filled contours, interactive
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/forecast_mm.zarr -o /tmp/fc.html \
    --spec '{"data": [{"uid": "0", "type": "contour"}]}'

# Stations and a county outline over a forecast
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o /tmp/layers.png \
    --layer heatmap:/tmp/imerg.zarr --layer scatter:/tmp/tahmo.zarr=STATIONS --layer outline:/tmp/nairobi.geojson=COUNTY \
    --spec '{"data": [{"uid": "STATIONS", "marker": {"size": 14}}, {"uid": "COUNTY", "line": {"width": 3}}]}'

# MSLP chart like a model-centre map: anomaly shading, labeled black isobars every 4 hPa,
# and H / L centres with their central pressure (from local-extrema --kind high / low).
# A contour with "coloring": "none" and a scatter with "mode": "text" add no colorbar.
# For a forecast, pick the same lead on every layer ("meta": {"source": {"isel": {"step": 40}}});
# a text trace skips centres that are NaN at that lead.
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o /tmp/mslp.png \
    --layer heatmap:/tmp/msl_anom.zarr --layer contour:/tmp/msl.zarr \
    --layer scatter:/tmp/highs.zarr --layer scatter:/tmp/lows.zarr --spec '{"data": [
  {"uid": "b", "contours": {"coloring": "none", "showlabels": true, "start": 900, "end": 1080, "size": 4}},
  {"uid": "c", "mode": "text", "texttemplate": "<b>H</b><br>%{customdata:.0f}", "textfont": {"color": "#1f4fbf", "size": 16}},
  {"uid": "d", "mode": "text", "texttemplate": "<b>L</b><br>%{customdata:.0f}", "textfont": {"color": "#c8102e", "size": 16}}]}'

# Wind speed with arrows
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/wind.zarr -o /tmp/wind.png --spec '{"data": [
  {"uid": "0", "meta": {"bind": "speed"}},
  {"uid": "arrows", "type": "scatter", "meta": {"bind": "arrows", "source": {"input": "0"}, "arrows": {"step": 3}}}]}'

# City markers and a dashed box over a map (plain scatter + a shape in lon/lat)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/rain.zarr -o /tmp/cities.png --spec '{"data": [
  {"uid": "cities", "type": "scatter", "mode": "markers+text", "x": [36.82, 39.67], "y": [-1.29, -4.04],
   "text": ["Nairobi", "Mombasa"], "textposition": "top right", "marker": {"symbol": "star", "size": 12, "color": "black"}}],
  "layout": {"shapes": [{"type": "rect", "xref": "x", "yref": "y", "x0": 33.9, "x1": 35.5, "y0": -1.5, "y1": 0.5,
   "line": {"color": "red", "dash": "dash"}}]}}'

# Wind rose
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/wind.zarr -o /tmp/rose.png --spec '{"data": [{"uid": "0", "type": "barpolar"}]}'

# Area-mean ensemble spaghetti with a 10–90% band (ens_area.zarr from summarize-dim --dim latitude --dim longitude --method mean --lat-weighted)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/ens_area.zarr -o /tmp/ens.png --spec '{"data": [{"uid": "0", "type": "scatter",
  "meta": {"bind": "series", "along": "number", "band": [10, 90]}}]}'

# September IOD against October rainfall, one point per year
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x /tmp/iod_sep.zarr --y /tmp/rain_oct.zarr -o /tmp/iod.png \
    --spec '{"data": [{"uid": "xy", "meta": {"pair_on": "year"}}], "layout": {"xaxis": {"title": {"text": "September IOD"}}}}'
```

## Output

The figure is written at `--output`. For PNG/JPG, stdout prints a pixel `plot hash` and `data: not null (…)` or `data: NULL (…)`, counting the values each input actually draws. `NULL` means everything plotted is NaN: run `inspect-zarr` on the input. Notes about choices the command made (which variable, totals conversion) go to stderr. A changed hash only proves the pixels changed. Always look at the image before choosing between layout options.

Provenance (`weather_skills_history`) is embedded in the PNG metadata or the HTML `<meta>` tag. Read it with the `provenance` skill. A PNG/JPG whose chain is complete also gets a small red seal (a ring with a star) in the bottom-right corner: the weather-skills "provenance verified" stamp. It is expected; leave it in.

Errors name the bad key and the keys allowed there. Plotly's own validator checks everything outside `meta` and suggests the closest key (`Did you mean "colorscale"?`).
