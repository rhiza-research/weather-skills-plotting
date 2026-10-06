---
name: plot
description: Render a map (heatmap, filled contour, stations, wind quiver), time series, xy scatter, or wind rose from weather-skills standard dataset Zarrs as PNG, JPG, or interactive HTML. The --spec is a standard Plotly figure JSON; dataset bindings go in each trace's meta. Side-by-side maps on different grids (CHIRPS 0.05° next to ECMWF 1.5°) are one -i per file, each on its own axes and grid; do not coarsen them onto one grid. --layer KIND:PATH stacks files on one map. --help lists the meta keys and recipes. Named places: get a bbox or polygon from resolve-region first. For precipitation, run aggregate-temporal then convert-to-totals first. For a lead-week verification grid, use plot-verify.
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

- `data[]` merges by `uid`. Files are `a`, `b`, `c`, … in `-i` / `--layer` order, and `x` / `y` for `--x` / `--y`. A `data[]` entry with no `uid` merges by position, and a new `uid` adds a trace.
- `layout.annotations` and `layout.shapes` merge by `name`. Everything else in `layout` is deep-merged.
- Your values win.

Run the same command with `--dump-spec -` in place of `-o` to print the figure it would draw, edit that JSON, and pass it back with `--spec`. A dumped spec replays on its own: the file paths are kept in `layout.meta.inputs`.

What the command builds from each file:

| File | Trace |
| --- | --- |
| lat/lon grid | `heatmap`, one panel per `time` or `step` value (ensemble `number` is averaged) |
| `station_id` / `point_id` data | `scatter` markers at the stations, colored by value (`meta.bind: "points"`) |
| 1-D along time | `scatter` line (`meta.bind: "series"`) |
| `--x` + `--y` | `scatter` of one series against the other (`meta.bind: "pair"`) |

## Panels and layers

| Goal | How |
| --- | --- |
| Two datasets side by side, each on its own grid | Repeat `-i`. Trace `a` sits on axes `x`/`y`, trace `b` on `x2`/`y2`, and so on. Each panel keeps its own lat/lon spacing and gets its own colorbar. Each input must already be one map: select or aggregate the time first. |
| Datasets drawn on top of each other | `--layer heatmap:a.zarr --layer scatter:stations.zarr --layer outline:kenya.geojson`. Every trace on the same axes stacks on one map. Same-variable layers share a colorbar. |
| Several times or steps of one dataset | One `-i`. The trace panels its `time` / `step` dim. `layout.grid.rows` / `columns` shape the grid (default up to 4 columns). |
| One colorbar for side-by-side maps | Point both traces at the same axis: `"coloraxis": "coloraxis"`. |

Panel titles are annotations named `panel-title-1`, `panel-title-2`, …. Rename one with `{"layout": {"annotations": [{"name": "panel-title-2", "text": "ECMWF"}]}}`. Panel and colorbar spacing is computed for you. `layout.grid.xgap` / `ygap` add extra space, as a fraction of a panel. `layout.width` / `height` set the canvas size.

Do not `coarsen` or `downscale` just to draw a figure. Only `difference` and `verify` need a shared grid.

## The `meta` keys

`data[].meta`:

| Key | Meaning |
| --- | --- |
| `bind` | How the arrays are filled: `field` (grid → heatmap/contour), `speed` (wind speed from u/v), `arrows` (u/v arrows), `points` (stations), `geojson` (boundary lines), `series` (1-D line or bar), `pair` (xy), `samples` (box per step), `windrose` (barpolar). The default comes from the trace type. |
| `source` | `{input, variable, isel, sel, reduce, u, v, geojson, mask_geojson, point}`. `reduce` lists dims to average. **Nothing is averaged silently**: a leftover dim is an error naming the fix. |
| `facet` | The dim to panel (default `step` or `time`); `false` turns paneling off. |
| `along`, `along_color`, `band` | Series: one line per value of a dim (`"number"` gives ensemble spaghetti). `along_color` is `same` (default) or `cycle`. `band: [10, 90]` shades a percentile band around the mean. |
| `align` | Series: `"dayofyear"` overlays years on one seasonal axis. |
| `pair_on`, `x`, `y` | Pair: the two sources and how they join (`time`, `year`, `index`). |
| `palette` | Class palette: a name (`ppt_daily`, `ppt_week`, `ppt_month`, `ppt_season`, `ppt_anom_*`, `spi`, `ppt_poa`, …), a color list, or `{colors, bounds, under, over}`. |
| `arrows` | `{step, scale}`: thin to every Nth cell; degrees of arrow per unit of speed. |

`layout.meta`:

| Key | Meaning |
| --- | --- |
| `geo.bbox` | `[N, W, S, E]` map window; subsets every input. There is no `geo.region`: run `resolve-region` and pass its bbox. |
| `geo.mask_geojson` | Blank map cells outside a polygon (does not draw it; add a `geojson` trace for the edge). |
| `geo.point` | `{lat, lon}` for `samples` traces. |
| `overlays` | Base map: `true` (default), `false`, or per layer, e.g. `{"rivers": false, "admin1": true, "borders": {"line": {"width": 2}}}`. Layers: `coastline`, `borders`, `lakes`, `rivers`, `admin1` (Natural Earth; scale follows the map span). |
| `export.scale` | PNG/JPG pixel multiplier (default 2). |

## Colors

Precipitation totals get the nested absolute-mm class palette automatically: the same color always means the same millimetres, and the window follows `aggregation_period`. Anomalies get the diverging classes. Fields with CF `flag_values` (e.g. `verify` hits) get one class per flag, labelled with `flag_meanings` (disagree / below / hit). Other fields get a sequential scale, or `RdBu_r` centred on zero when the data spans zero.

- **A Plotly colorscale and limits:** set `colorscale`, `zmin` / `zmax` (or `marker.cmin` / `cmax` for stations) and `colorbar` on the trace. They apply to the trace's color axis. Setting limits on a class palette turns it into a continuous scale.
- **A class palette:** `meta.palette`.
- **A whole color axis:** `layout.coloraxis` (or `coloraxis2`, …), e.g. `{"layout": {"coloraxis": {"colorbar": {"title": {"text": "Rain [mm]"}}}}}`.

The colorbar label defaults to the variable's `long_name` and short units (`Total precipitation [mm]`). Dates belong in titles.

## Command line

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i <in.zarr> [-i <in2.zarr> …] -o <out.png|.html> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer KIND:PATH [--layer …] -o <out.png> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x <x.zarr> --y <y.zarr> -o <out.png> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i <in.zarr> --dump-spec -
```

- `-i` — repeatable Zarr; exclusive with `--layer` and `--x`/`--y`.
- `--layer KIND:PATH` — `heatmap`, `contour`, `scatter` (stations), `quiver` (u/v: speed plus arrows), `outline` (GeoJSON edge), `mask` (GeoJSON mask).
- `--spec` — inline JSON or a file path.
- `--dump-spec [PATH]` — print or write the merged spec and skip drawing.
- `--theme-file` — JSON/TOML `{"template": <Plotly template>, "palettes": {name: {colors, bounds}}}`. `layout.template` also accepts `weather_skills` (default), `colorblind`, or any Plotly template name.

`--help` prints the full `meta` reference and copy-paste recipes.

## Examples

```bash
# Weekly CHIRPS totals, one panel per week, 2 rows
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/chirps_weekly_mm.zarr -o /tmp/chirps.png \
    --spec '{"layout": {"title": {"text": "CHIRPS weekly totals"}, "grid": {"rows": 2}}}'

# CHIRPS 0.05° beside ECMWF 1.5°, each on its own grid, Kenya window, named panels
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/chirps_week.zarr -i /tmp/ecmwf_week.zarr \
    -o /tmp/obs_vs_fc.png --spec '{
  "data": [{"uid": "a", "name": "CHIRPS 0.05°"}, {"uid": "b", "name": "ECMWF 1.5°"}],
  "layout": {"title": {"text": "Week 1"}, "meta": {"geo": {"bbox": [5, 33.5, -5, 42]}}}}'

# Filled contours, interactive
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/forecast_mm.zarr -o /tmp/fc.html \
    --spec '{"data": [{"uid": "a", "type": "contour"}]}'

# Stations and a county outline over a forecast
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o /tmp/layers.png \
    --layer heatmap:/tmp/imerg.zarr --layer scatter:/tmp/tahmo.zarr --layer outline:/tmp/nairobi.geojson \
    --spec '{"data": [{"uid": "b", "marker": {"size": 14}}, {"uid": "c", "line": {"width": 3}}]}'

# Wind speed with arrows
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/wind.zarr -o /tmp/wind.png --spec '{"data": [
  {"uid": "a", "meta": {"bind": "speed"}},
  {"uid": "arrows", "type": "scatter", "meta": {"bind": "arrows", "source": {"input": "a"}}}]}'

# Wind rose
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/wind.zarr -o /tmp/rose.png --spec '{"data": [{"uid": "a", "type": "barpolar"}]}'

# Area-mean ensemble spaghetti with a 10–90% band
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i /tmp/ens.zarr -o /tmp/ens.png --spec '{"data": [{"uid": "a", "type": "scatter",
  "meta": {"bind": "series", "along": "number", "band": [10, 90], "source": {"reduce": ["latitude", "longitude"]}}}]}'

# September IOD against October rainfall, one point per year
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x /tmp/iod_sep.zarr --y /tmp/rain_oct.zarr -o /tmp/iod.png \
    --spec '{"data": [{"uid": "xy", "meta": {"pair_on": "year"}}], "layout": {"xaxis": {"title": {"text": "September IOD"}}}}'
```

## Output

The figure is written at `--output`. For PNG/JPG, stdout prints a pixel `plot hash` and `data: not null (…)` or `data: NULL (…)`. `NULL` means every plotted variable is all-NaN: run `inspect-zarr` on the input. A changed hash only proves the pixels changed. Always look at the image before choosing between layout options.

Provenance (`weather_skills_history`) is embedded in the PNG metadata or the HTML `<meta>` tag. Read it with the `provenance` skill.

Errors name the bad key and the keys allowed there. Plotly's own validator checks everything outside `meta` and suggests the closest key (`Did you mean "colorscale"?`).
