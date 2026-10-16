---
name: plot-timeseries
description: "Draw weather-skills Zarrs as lines or bars on one time axis, saved as PNG, JPG, or interactive HTML: area means, station records, or every ensemble member with a percentile band. Use to compare series over time, such as observed rainfall against a forecast or climatology, or several years on one seasonal calendar."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot-timeseries

Draws one series per Zarr on a shared time axis. Name the files on the command line; set titles, colors, and layout in `--spec`.

## Usage

```bash
# One line per file
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i chirps_area.zarr=CHIRPS -i imerg_area.zarr=IMERG -o rain.png
# Every ensemble member, with the 10–90% range shaded and the mean drawn bold
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i ecmwf_ens_area.zarr -o ens.html --spec '{"data": [{"uid": "0", "meta": {"along": "number", "band": [10, 90]}}]}'
```

A series runs along `time`, or for a forecast along its valid date (init time + `step`). The legend names each series after its file, or its station id.

### Arguments
- `--input`, `-i` — Zarr to draw, as `PATH` or `PATH=NAME`; repeat once per series, in legend order (up to 26).
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — house style: a Plotly `template` (fonts, background, colors) and named `palettes`.
- `--dump-spec` — print (`-`) or save (a path) the spec, without drawing.
- `--output`, `-o` — `.png`, `.jpg`, or `.html`.

### Customizing with `--spec`
`--spec` takes [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`; write only the parts you want to change. Each input file is one entry in `data`. Name it on the command line (`-i obs.zarr=OBS`) and put that name in `"uid"`; unnamed files are `"0"`, `"1"`, … in order. Settings under `meta` on the first entry apply to every series that does not set its own.

| To | `--spec` |
| --- | --- |
| Rename a series | `{"data": [{"uid": "0", "name": "CHIRPS"}]}` |
| Draw bars | `{"data": [{"uid": "0", "type": "bar"}]}` (`"layout": {"barmode": "stack"}` stacks them) |
| Pick one member | `{"data": [{"uid": "0", "meta": {"source": {"isel": {"number": 0}}}}]}` |
| One panel per series | `{"layout": {"grid": {"rows": 2, "columns": 1, "pattern": "coupled"}}}` |
| Right-hand y-axis | `{"data": [{"uid": "1", "yaxis": "y2"}], "layout": {"yaxis2": {"overlaying": "y", "side": "right"}}}` |
| Years on one calendar (one `-i` per year) | `{"data": [{"uid": "0", "meta": {"align": "dayofyear"}}]}` |
| Title and y label | `{"layout": {"title": {"text": "Nairobi"}, "yaxis": {"title": {"text": "Rain [mm]"}}}}` |

`isel` counts from 0 (`-1` is the last); `sel` picks by label, nearest (`{"latitude": -1.3}`). `--help` lists every option with recipes; `--dump-spec -` shows the spec for your files.

### Output
The figure at `-o`. PNG/JPG also print `data: not null` or `data: NULL`; `NULL` means every value drawn is NaN.

### Notes
- Every dim other than `time` / `step` must go: pick one value with `isel` / `sel`, draw one line per value with `"along": "number"`, or average it first with summarize-dim (for an area mean, `--dim latitude --dim longitude --method mean --lat-weighted`). A leftover dim is an error that names the fix.
- Precip rates with an `aggregation_period` are drawn as period totals (mm). If only some series on an axis have one, all stay rates (mm/day).
- Series on one axis with different units, or with no dates in common, print a warning and still draw.

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i obs_area.zarr=OBS -i clim_area.zarr=CLIM -o obs_vs_clim.png --spec '{
  "data": [{"uid": "OBS", "name": "CHIRPS", "type": "bar"}, {"uid": "CLIM", "name": "Climatology", "line": {"dash": "dash"}}],
  "layout": {"title": {"text": "September rainfall"}}}'
```
Daily CHIRPS rainfall as bars with the climatology as a dashed line.

## Details

### Ensembles and stations
- `"along": "number"` draws one line per member in one color under one legend entry; `"along_color": "cycle"` gives each its own color and entry. `"band": [10, 90]` shades that percentile range and draws the mean bold over faint members; `"members": false` hides the members.
- `along` passes only to series that have that dim, so a climatology line next to an ensemble stays a single line. Set a key to `null` on a later series to drop an inherited value.
- With `"type": "bar"`, `along` gives one bar series per value, such as one per `station_id`.
- Two variables of one file are two `-i` of the same path, each with its own `"meta": {"source": {"variable": …}}`.

### Seasonal overlays
`"align": "dayofyear"` moves every series onto one calendar, labelled `1 Oct`, `15 Nov`, …, so dates line up across leap years (29 Feb joins 28 Feb). Pass one file per year, each a single season. A season that crosses New Year, such as DJF, puts Jan–Feb at the left of the axis and Dec at the right.

### Look
- With two or more legend entries the legend sits in rows above the plot, in input order; one plain series has none.
- The y-axis label is the variable's `long_name` and units. A rainfall axis does not go below zero.
- Keep the title to a few words and axis labels to the quantity and units; methods and sources go in your reply.
- The file's history (`weather_skills_history`) is embedded in the PNG metadata or HTML `<meta>` tag; read it with the `provenance` skill.

### More examples
```bash
# CHIRPS and IMERG in two stacked panels, each with its own y-axis
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i chirps_area.zarr -i imerg_area.zarr -o panels.png \
  --spec '{"data": [{"uid": "0", "name": "CHIRPS"}, {"uid": "1", "name": "IMERG"}], "layout": {"grid": {"rows": 2, "columns": 1, "pattern": "coupled"}}}'
# Three OND seasons on one calendar
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i chirps_ond_2023.zarr -i chirps_ond_2024.zarr -i chirps_ond_2025.zarr -o ond.png \
  --spec '{"data": [{"uid": "0", "meta": {"align": "dayofyear"}}]}'
```
