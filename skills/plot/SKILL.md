---
name: plot
description: "Draw weather-skills Zarrs as maps (heatmap, contour, stations, wind arrows), time series, xy scatter plots, or wind roses, saved as PNG, JPG, or interactive HTML. Titles, colors, panels, and layout are set with a standard Plotly figure JSON."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot

Draws one or more Zarrs as a figure. Name the files on the command line; set titles, colors, and layout in `--spec`.

## Usage

```bash
# One map (or one panel per time / step)
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i rain.zarr -o rain.png
# Maps side by side, each on its own grid
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps.zarr=OBS -i ecmwf.zarr=FC -o compare.png
# Layers on one map, bottom first
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --layer heatmap:rain.zarr --layer scatter:stations.zarr --layer outline:kenya.geojson -o map.png
# One series against another
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x iod.zarr --y rain.zarr -o iod_vs_rain.png
```

The plot type follows the data: a lat/lon grid is a colored map, stations are colored markers, a 1-D series is a line.

### Arguments
- `--input`, `-i` — Zarr to draw, as `PATH` or `PATH=NAME`; repeat for side-by-side panels.
- `--layer` — `KIND:PATH` or `KIND:PATH=NAME` to stack on one map; repeat. Kinds: `heatmap`, `contour`, `scatter` (stations), `quiver` (wind u/v), `outline` and `mask` (GeoJSON). `outline` and `mask` also work with `-i`.
- `--x`, `--y` — two series for an xy scatter.
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — house style: a Plotly `template` (fonts, background, colors) and named `palettes` for `meta.palette`.
- `--dump-spec` — print (`-`) or save (a path) the spec the tool would draw, without drawing.
- `--output`, `-o` — `.png`, `.jpg`, or `.html` (interactive).

### Customizing with `--spec`
The tool picks sensible defaults; `--spec` changes them. It takes [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`, and you write only the parts you want to change.

Each input file is one entry in `data`. Name it on the command line (`-i ecmwf.zarr=FC`), then put that name in `"uid"` to say which file a change applies to. Unnamed files are `"0"`, `"1"`, … in the order you passed them; `--x` / `--y` make one entry, `"xy"`.

| To | `--spec` |
| --- | --- |
| Set the title | `{"layout": {"title": {"text": "Week 1"}}}` |
| Title a panel | `{"data": [{"uid": "OBS", "name": "CHIRPS"}]}` |
| Pick one step | `{"data": [{"uid": "FC", "meta": {"source": {"isel": {"step": 0}}}}]}` |
| Set the color range | `{"data": [{"uid": "0", "zmin": 0, "zmax": 100}]}` |
| Set the map window | `{"layout": {"meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}` |
| Draw contours | `{"data": [{"uid": "0", "type": "contour"}]}` |

`isel` counts from 0 (`-1` is the last); `sel` picks by label (`{"time": "2026-10-01"}`). `bbox` is `[N, W, S, E]`. `--help` lists every option with recipes; `--dump-spec -` shows the spec for your files, ready to edit.

### Output
The figure at `-o`. PNG/JPG also print `data: not null` or `data: NULL`; `NULL` means every value drawn is NaN.

### Notes
- A map shows one value per cell. Pick one value of any extra dim (ensemble `number`, `vertical`) with `isel` / `sel`, panel it with `"meta": {"facet": "number"}`, or average it first with summarize-dim.
- Precip rates with an `aggregation_period` are drawn as period totals (mm).

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i chirps_week.zarr=OBS -i ecmwf_week.zarr=FC -o obs_vs_fc.png --spec '{
  "data": [{"uid": "OBS", "name": "CHIRPS"}, {"uid": "FC", "name": "ECMWF", "meta": {"source": {"isel": {"step": 0}}}}],
  "layout": {"title": {"text": "Week 1 rainfall"}, "meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}'
```
CHIRPS and ECMWF week-1 rainfall side by side over Kenya, each on its own grid, with one shared colorbar.

## Details

### Panels and layers
- A file with several times or steps gets one panel each, titled with its date. `layout.grid.rows` / `columns` set the grid; `xgap` / `ygap` the spacing, as a fraction of a panel.
- Panels showing the same quantity share one colorbar. To split one off: `{"data": [{"uid": "FC", "coloraxis": "coloraxis2"}]}`.
- Panel titles are annotations named `panel-title-1`, `panel-title-2`, …; rename one with `{"layout": {"annotations": [{"name": "panel-title-2", "text": "ECMWF"}]}}`.
- Maps use plain x/y axes in degrees (x = longitude). Add points or lines as `scatter` traces with `x` / `y`, and boxes as `layout.shapes` with `xref: "x"`, `yref: "y"`.
- An `outline` layer frames the map unless `geo.bbox` is set, and hides the built-in admin-1 lines. Use it to draw official boundaries.
- The canvas fits the maps (up to 760×560 px for one map, 340×340 px per panel in a grid). `layout.width` / `height` fix it.

### Colors
- Precip totals use the mm class palette `default_precip`; anomalies use `default_precip_anom`. The range follows `aggregation_period`: under 2 days 0–50 mm, under 10 days 0–200, under 40 days 0–400, longer 0–1000 (anomalies ±50 / ±200 / ±300 / ±500).
- Set a palette with `"meta": {"palette": NAME}`: `default_precip`, `default_precip_anom`, `ppt_daily` … `ppt_season`, `ppt_anom_*`, `spi`, or your own `{colors, bounds}`.
- Temperatures use `RdYlBu_r`; fields spanning zero use `RdBu_r`; flag fields (verify hits) get one color per flag.
- `{"layout": {"coloraxis": {"colorbar": {"orientation": "h"}}}}` puts the colorbar under the maps.
- A `--theme-file` palette named like a built-in one replaces it. Without `--theme-file`, `$WEATHER_SKILLS_PLOT_THEME` or `~/.config/weather-skills/plot.json|toml` is used if present.

### Provenance
The file's history (`weather_skills_history`) is embedded in the PNG metadata or HTML `<meta>` tag; read it with the `provenance` skill. A PNG/JPG with a complete history carries a small red seal in the bottom-right corner.

### More examples
```bash
# Stations over IMERG, inside a county outline
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -o nairobi.png \
  --layer heatmap:imerg.zarr --layer scatter:tahmo.zarr=STATIONS --layer outline:nairobi.geojson \
  --spec '{"data": [{"uid": "STATIONS", "marker": {"size": 14}}]}'
# Ensemble members as lines with a 10–90% band
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i ens_area_mean.zarr -o ens.png \
  --spec '{"data": [{"uid": "0", "meta": {"bind": "series", "along": "number", "band": [10, 90]}}]}'
# September IOD against October rainfall, one point per year
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py --x iod_sep.zarr --y rain_oct.zarr -o iod.png \
  --spec '{"data": [{"uid": "xy", "meta": {"pair_on": "year"}}]}'
```
