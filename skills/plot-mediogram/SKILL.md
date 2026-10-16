---
name: plot-mediogram
description: "Draw an ECMWF-style mediogram at one place, saved as PNG, JPG, or interactive HTML: for each forecast lead, a box plot of the forecast ensemble next to a box plot of the model climate, plus the forecast mean. Use to show whether a forecast at a point is unusually wet, dry, warm, or cold compared with what the model normally predicts at that lead and time of year."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_mediogram.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot-mediogram

Draws a forecast ensemble against the model climate at one point, one pair of box plots per lead.

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_mediogram.py -i forecast.zarr -i mclimate.zarr -o mediogram.png \
  --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}'
```

The model climate (m-climate) is the same forecast system's reforecasts of past years for the same leads: what the model usually predicts. Each lead gets a blue forecast box and a red m-climate box, with a black line through the forecast mean. Each file uses its grid cell nearest the point.

### Arguments
- `--input`, `-i` — pass twice: the forecast Zarr, then the m-climate Zarr.
- `--spec` — Plotly figure JSON, inline or a file path. Must set the point, `layout.meta.geo.point`.
- `--theme-file` — house style: a Plotly `template` (fonts, background, colors) and named `palettes`.
- `--dump-spec` — print (`-`) or save (a path) the spec, without drawing.
- `--output`, `-o` — `.png`, `.jpg`, or `.html`.

### Inputs
Both files need ensemble members (`number`), leads (`step`), and latitude/longitude. The m-climate must hold individual reforecast members for the same leads; a climatology mean and standard deviation is not one. No fetcher here supplies reforecasts; a past init of the same system (same leads) is a rough stand-in. Say so in the title if you use one. Up to 15 leads are drawn, those both files have.

### Customizing with `--spec`
`--spec` takes [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`; write only the parts you want to change. The figure has three entries in `data`, chosen by `"uid"`: `"forecast"` and `"mclimate"` (Plotly `box` traces) and `"forecast-mean"` (a line).

| To | `--spec` |
| --- | --- |
| Set the point | `{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}` |
| Set the title | `{"layout": {"title": {"text": "Nairobi"}}}` (the grid cell and init date are added) |
| Recolor a box | `{"data": [{"uid": "mclimate", "fillcolor": "orange"}]}` |
| Pick leads | `{"data": [{"uid": "forecast", "meta": {"source": {"isel": {"step": [0, 2, 4, 6]}}}}, {"uid": "mclimate", "meta": {"source": {"isel": {"step": [0, 2, 4, 6]}}}}, {"uid": "forecast-mean", "meta": {"source": {"isel": {"step": [0, 2, 4, 6]}}}}]}` |
| Pick the variable | `{"data": [{"uid": "forecast", "meta": {"source": {"variable": "t2m"}}}, {"uid": "mclimate", "meta": {"source": {"variable": "t2m"}}}, {"uid": "forecast-mean", "meta": {"source": {"variable": "t2m"}}}]}` |

Leads and variable are set on each entry, so the two files may name the variable differently. `--help` lists every option; `--dump-spec -` shows the spec for your files.

### Output
The figure at `-o`. PNG/JPG also print `data: not null` or `data: NULL`; `NULL` means every value drawn is NaN.

### Notes
- Boxes pair up by lead, so an m-climate from another init date lines up by lead, not by date.
- For rainfall totals, run aggregate-temporal then convert-to-totals on both files first.

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_mediogram.py -i ecmwf_fc.zarr -i ecmwf_mclimate.zarr -o mediogram_nairobi.png \
  --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}, "title": {"text": "Nairobi"}}}'
```
ECMWF daily rainfall for the 15 days from the 12 Oct 2026 init at Nairobi, each day's 51 members next to the m-climate.

## Details

### Reading the boxes
A box spans the 25th to 75th percentile of the members, with a line at the median. Whiskers reach the furthest member within 1.5 × the box height; members beyond are dots.

### Axes and title
When the forecast has its init `time`, the x-axis shows each lead's valid date and the title the init date; otherwise it shows the lead. The default title names the variable and the grid cell used. A rainfall axis does not go below zero. Keep a custom title to a few words, such as the place name.

### Provenance
The file's history (`weather_skills_history`) is embedded in the PNG metadata or HTML `<meta>` tag; read it with the `provenance` skill.
