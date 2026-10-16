---
name: plot-verify
description: "Draw a forecast verification grid for one week, saved as PNG, JPG, or interactive HTML: the observation and the week-1 … week-N forecasts side by side on one color scale, with each lead's score map (hits, bias, or MAE from the verify skill) underneath. Use to show how a forecast's skill changes with lead time for one verifying week."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify.py *)
metadata:
  version: "0.0.3"
  catalog-group: figure
---

# plot-verify

Draws the observation, the forecasts at each lead, and their verify maps for one week as a grid of maps.

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify.py --obs chirps_week.zarr \
  --forecast ecmwf_week1.zarr --verify verify_w1.zarr \
  --forecast ecmwf_week2.zarr --verify verify_w2.zarr -o verify.png
```

Row 1 is the observation, then one column per `--forecast`. Row 2 has each forecast's verify map under it, and the metric name under the observation. With one `--forecast` the figure is one row: observation, forecast, verify map.

### Arguments
- `--obs` — observation Zarr for the verifying week.
- `--forecast` — forecast Zarr for that week at one lead; repeat, week-1 first. Columns follow this order. An ensemble is drawn as its mean: run summarize-dim `--dim number --method mean` first (verify averages members itself).
- `--verify` — the verify skill's output for each `--forecast`, in the same order. All must use one metric: `hits`, `bias`, or `mae`.
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — house style: a Plotly `template` (fonts, background, colors) and named `palettes`.
- `--dump-spec` — print (`-`) or save (a path) the spec, without drawing.
- `--output`, `-o` — `.png`, `.jpg`, or `.html`.

### Prepare the inputs
- `--obs` and each `--forecast` hold one time: the verifying week. Run select on that week first; a forecast with a `step` axis needs step-to-time before that.
- Obs and forecasts share one grid: coarsen the obs onto the forecast with `--reference-grid`.
- For rainfall, run aggregate-temporal, then convert-to-totals, before verify.

### Customizing with `--spec`
`--spec` takes [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`; write only the parts you want to change. Each map is one entry in `data`, with `"uid"` `"obs"`, `"forecast1"` … `"forecastN"`, and `"verify1"` … `"verifyN"`. Column titles are annotations named `panel-title-1` (obs), `panel-title-2` (week 1), …; the metric label is `row-label-metric`. Obs and forecasts share `coloraxis`; the verify maps share `coloraxis2`.

| To | `--spec` |
| --- | --- |
| Set the title (week dates are added) | `{"layout": {"title": {"text": "Kenya rainfall"}}}` |
| Rename a column | `{"layout": {"annotations": [{"name": "panel-title-2", "text": "Init 29 Sep"}]}}` |
| Forecast variable named differently | `{"data": [{"uid": "forecast1", "meta": {"source": {"variable": "tp"}}}]}` |
| Set the map window | `{"layout": {"meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}` |
| Set the field color range | `{"layout": {"coloraxis": {"cmin": 0, "cmax": 100}}}` |

`bbox` is `[N, W, S, E]`. `--help` lists every option; `--dump-spec -` shows the spec for your files.

### Output
The figure at `-o`. Each lead's score summary goes to stderr. PNG/JPG also print `data: not null` or `data: NULL`; `NULL` means every value drawn is NaN.

### Notes
- The week's dates (`5–11 Oct '26`) are added to the title from any input that still has a `time` coordinate. When none has one, put the week in the title yourself.

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify.py --obs chirps_week.zarr \
  --forecast ecmwf_week1.zarr --verify verify_w1.zarr --forecast ecmwf_week2.zarr --verify verify_w2.zarr \
  --forecast ecmwf_week3.zarr --verify verify_w3.zarr --forecast ecmwf_week4.zarr --verify verify_w4.zarr \
  -o verify_week.png --spec '{"layout": {"title": {"text": "Kenya weekly rainfall"}, "meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}'
```
CHIRPS for one week next to the ECMWF week-1 to week-4 forecasts of it, with each lead's bias map below, over Kenya.

## Details

### Colors
- Obs and forecasts share one scale. Rainfall uses the mm class palette for the longest aggregation period among them.
- Hits: three classes, disagree / below / hit; the colorbar title gives the event threshold.
- Bias: centred on zero, reaching the 98th percentile of |bias| across all leads. Rainfall runs brown (forecast too dry) to green (too wet); other fields blue to red.
- MAE: white through warm colors from zero.

### Titles and variables
- Keep titles short; the grid has many panels and two colorbars.
- Forecasts use the obs variable name when they have it, else their own main variable.

### Provenance
The file's history (`weather_skills_history`) is embedded in the PNG metadata or HTML `<meta>` tag; read it with the `provenance` skill.
