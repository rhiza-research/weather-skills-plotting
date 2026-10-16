---
name: plot
description: "Draw weather-skills Zarrs as maps (heatmap, contour, stations, wind arrows), time series, xy scatter plots, or wind roses, saved as PNG, JPG, or interactive HTML. Titles, colors, panels, and layout are set with a standard Plotly figure JSON. For a forecast verification grid use plot-verify; for an animation use plot-video."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot

Builds a Plotly figure from the files you name, merges your `--spec` onto it, and writes the image.

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i A.zarr [-i B.zarr ...] -o OUT.png|.jpg|.html [--spec JSON] [--theme-file FILE]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer KIND:PATH [--layer KIND:PATH ...] -o OUT.png [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x X.zarr --y Y.zarr -o OUT.png [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i A.zarr --dump-spec -
```

### Arguments
- `--input`, `-i` — input Zarr; repeat for side-by-side panels, each on its own grid. Trace ids are `a`, `b`, … in order.
- `--layer` — `KIND:PATH` drawn on one shared map; repeat to stack. Kinds: `heatmap`, `contour`, `scatter` (stations), `quiver` (u/v), `outline` (GeoJSON), `mask` (GeoJSON). `outline` / `mask` also combine with `-i`; data layers do not.
- `--x`, `--y` — two series Zarrs for an xy scatter (ids `x`, `y`).
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — JSON/TOML `{template, palettes: {name: {colors, bounds}}}`.
- `--dump-spec` — print (`-`) or write (a path) the merged spec and skip drawing.
- `--output`, `-o` — `.png`, `.jpg`, or `.html` (interactive, offline).

### The spec
- `data[]` merges onto the built traces by `uid`; `layout.annotations` / `shapes` by `name`; everything else deep-merges. Plotly keys work as in [Plotly](https://plotly.com/python/reference/).
- `data[].meta` binds data: `source.isel` / `source.sel` pick times, steps, or members (`{"time": -1}` is the latest); `facet` panels a dim; `palette` sets class colors.
- `layout.meta.geo.bbox` (`[N, W, S, E]`) sets the map window.
- `--help` lists every `meta` key and copy-paste recipes. Start from `--dump-spec -`, not guesses.

### Output
The figure at `-o`. PNG/JPG print a `plot hash` and `data: not null` or `data: NULL` (everything NaN: check the input with inspect-zarr). Choices the plotter made go to stderr. Look at the image before choosing between layouts.

### Notes
- Every dim other than lat/lon and the panel dim must be selected (`isel` / `sel`) or reduced first with summarize-dim.
- Precip rates with an `aggregation_period` are drawn as period totals (mm).

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_week.zarr -i ecmwf_week.zarr -o obs_vs_fc.png --spec '{
  "data": [{"uid": "a", "name": "CHIRPS"}, {"uid": "b", "name": "ECMWF", "meta": {"source": {"isel": {"step": 0}}}}],
  "layout": {"title": {"text": "Week 1 rainfall"}, "meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}'
```
CHIRPS and ECMWF week-1 totals side by side over Kenya, each on its own grid, sharing one colorbar.

## Details

### What each file becomes

| File | Trace |
| --- | --- |
| lat/lon grid | `heatmap`, one panel per `time` / `step` value, titled with its date. `meta.facet: "number"` or `"vertical"` panels that dim instead. |
| `station_id` / `point_id` | `scatter` markers colored by value |
| 1-D along time | line (`meta.bind: "series"`) |
| `--x` + `--y` | one series against the other, joined on `meta.pair_on` |

### Panels and layers
- Side-by-side `-i` traces sit on axes `x`/`y`, `x2`/`y2`, …. Panels of one quantity share a colorbar; give one `"coloraxis": "coloraxis2"` to split it.
- Traces on the same axes stack as layers; layers of one quantity share a colorbar.
- `layout.grid.rows` / `columns` shape a multi-panel trace (default: the most landscape grid with no empty row). `xgap` / `ygap` are fractions of a panel.
- Panel titles are annotations `panel-title-1`, `panel-title-2`, …; a trace's `name` titles its panel.
- Maps are plain x/y axes in degrees. Add markers and lines as `scatter` traces with `x` / `y`, boxes as `layout.shapes` with `xref: "x"`. `scattergeo` / `scattermap` are rejected.
- An `outline` layer frames the map unless `geo.bbox` is set, and turns off Natural Earth admin-1 lines. For official boundaries, add a region GeoJSON as `--layer outline:PATH`.
- Canvas size follows the maps (up to 760×560 px alone, 340×340 px per grid panel). `layout.width` / `height` fix it.

### Colors
- Precip totals get the absolute-mm class palette `default_precip`, anomalies `default_precip_anom`; the window follows `aggregation_period` (<2 d 0–50 mm, <10 d 0–200, <40 d 0–400, longer 0–1000; anomalies ±50/±200/±300/±500). Name one in `meta.palette` when detection would miss, e.g. an anomaly from `difference`. Fixed windows: `ppt_daily` … `ppt_season`, `ppt_anom_*`.
- CF `flag_values` fields (verify hits) get one class per flag. Temperatures get `RdYlBu_r`; fields spanning zero get `RdBu_r`; others a sequential scale.
- `zmin` / `zmax` / `colorscale` on a trace give a continuous scale. `{"coloraxis": {"colorbar": {"orientation": "h"}}}` puts the colorbar under the maps.
- Colorbar labels default to `long_name [units]`; forecast panels are titled with valid dates. Keep titles short.

### Provenance
`weather_skills_history` is embedded in PNG metadata or the HTML `<meta>` tag (read it with the `provenance` skill). A PNG/JPG with a complete chain carries a small red seal bottom-right; leave it in.

### More examples
```bash
# Stations and a county outline over IMERG
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o layers.png \
  --layer heatmap:imerg.zarr --layer scatter:tahmo.zarr --layer outline:nairobi.geojson \
  --spec '{"data": [{"uid": "b", "marker": {"size": 14}}]}'
# Ensemble spaghetti with a 10–90% band (area mean from summarize-dim)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i ens_area.zarr -o ens.png \
  --spec '{"data": [{"uid": "a", "meta": {"bind": "series", "along": "number", "band": [10, 90]}}]}'
# September IOD against October rainfall, one point per year
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x iod_sep.zarr --y rain_oct.zarr -o iod.png \
  --spec '{"data": [{"uid": "xy", "meta": {"pair_on": "year"}}]}'
```
